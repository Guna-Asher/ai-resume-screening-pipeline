"""GitHub enrichment via the public REST API: one call per user, cached for the run, never raises."""
import os
import re
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone

import httpx

from src.models import GitHubEnrichment, GitHubStatus

API_URL = "https://api.github.com"
DEFAULT_RECENT_DAYS = 90
MAINTAINED_DAYS = 365
TIMEOUT_S = 10.0
_USERNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_AI_TERMS = re.compile(
    r"(?<![a-z0-9])(?:llms?|rag|agents?|agentic|langchain|langgraph|llama[-\s]?index|openai|gpt|gemini|"
    r"embeddings?|vector|retrieval|chatbot|generative|genai|mcp|prompt\w*)(?![a-z0-9])", re.I)


class GitHubEnricher:
    """Callable: username -> GitHubEnrichment. Failures become a status, not an exception."""

    def __init__(self, token: str | None = None, recent_days: int = DEFAULT_RECENT_DAYS,
                 timeout: float = TIMEOUT_S, http: httpx.Client | None = None,
                 now: Callable[[], datetime] | None = None):
        self._token = token or None
        self.recent_days = recent_days
        self.timeout = timeout
        self._http = http or httpx.Client()
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._cache: dict[str, GitHubEnrichment] = {}   # per run: a username is fetched once

    def __repr__(self) -> str:  # never expose the token
        return f"GitHubEnricher(recent_days={self.recent_days}, authenticated={bool(self._token)})"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "GitHubEnricher":
        env = os.environ if environ is None else environ
        try:
            days = int(env.get("GITHUB_RECENT_DAYS") or DEFAULT_RECENT_DAYS)
        except ValueError:
            days = DEFAULT_RECENT_DAYS
        return cls(token=(env.get("GITHUB_TOKEN") or "").strip() or None, recent_days=max(1, days))

    def __call__(self, username: str | None) -> GitHubEnrichment:
        if not username or not _USERNAME.match(username):
            return GitHubEnrichment(status=GitHubStatus.NOT_PROVIDED, recent_days=self.recent_days)
        key = username.lower()
        if key not in self._cache:
            self._cache[key] = self._fetch(username)
        return self._cache[key]

    def _fetch(self, username: str) -> GitHubEnrichment:
        def fail(status: GitHubStatus, error: str) -> GitHubEnrichment:
            return GitHubEnrichment(status=status, username=username, recent_days=self.recent_days, error=error)

        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            resp = self._http.get(f"{API_URL}/users/{username}/repos", headers=headers, timeout=self.timeout,
                                  params={"per_page": 100, "sort": "pushed", "type": "owner"})
        except httpx.TimeoutException:
            return fail(GitHubStatus.ERROR, "GitHub request timed out")
        except httpx.HTTPError as e:
            return fail(GitHubStatus.ERROR, f"GitHub network error: {type(e).__name__}")

        if resp.status_code == 404:
            return fail(GitHubStatus.NOT_FOUND, "GitHub user not found or not public")
        if resp.status_code == 429 or (resp.status_code == 403 and (
                resp.headers.get("x-ratelimit-remaining") == "0" or "rate limit" in resp.text.lower())):
            return fail(GitHubStatus.RATE_LIMITED, "GitHub API rate limit reached")
        if resp.status_code != 200:
            return fail(GitHubStatus.ERROR, f"GitHub HTTP {resp.status_code}")
        try:
            repos = resp.json()
        except ValueError:
            repos = None
        if not isinstance(repos, list):
            return fail(GitHubStatus.ERROR, "unexpected GitHub response")
        return self._summarise(username, [r for r in repos if isinstance(r, dict)])

    def _summarise(self, username: str, repos: list[dict]) -> GitHubEnrichment:
        now = self._now()
        recent_cutoff = now - timedelta(days=self.recent_days)
        maintained_cutoff = now - timedelta(days=MAINTAINED_DAYS)
        e = GitHubEnrichment(status=GitHubStatus.OK, username=username, recent_days=self.recent_days,
                             public_repos=len(repos))
        languages: Counter[str] = Counter()
        for r in repos:
            if r.get("fork") or r.get("archived") or not r.get("size"):
                continue  # not the user's own work, abandoned, or empty
            e.relevant_repos += 1
            e.total_stars += int(r.get("stargazers_count") or 0)
            lang = r.get("language")
            if lang:
                languages[lang] += 1
            pushed = _parse_time(r.get("pushed_at"))
            is_python = lang == "Python"
            text = " ".join([str(r.get("name") or ""), str(r.get("description") or ""),
                             *map(str, r.get("topics") or [])])
            is_ai = bool(_AI_TERMS.search(text))
            e.python_repos += is_python
            e.ai_repos += is_ai
            if pushed and pushed >= recent_cutoff:
                e.recently_active_repos += 1
            if (is_python or is_ai) and pushed and pushed >= maintained_cutoff:
                e.maintained = True
        e.top_languages = [name for name, _ in languages.most_common(3)]
        return e


def _parse_time(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
