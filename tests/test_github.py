"""GitHub enrichment against a fake HTTP transport. No network, no token."""
from datetime import datetime, timedelta, timezone

import httpx

from src.enrichment import GitHubEnricher
from src.models import GitHubEnrichment, GitHubStatus, ScreeningStatus
from src.pipeline import screen_batch
from src.screening import github_points, score_resume

from .factories import STRONG_PROJECT, make_resume
from .llm_fakes import RAW_TEXT

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def iso(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def repo(name="proj", days=10, lang="Python", desc="", fork=False, archived=False, size=100, stars=0, topics=()):
    return {"name": name, "pushed_at": iso(days), "language": lang, "description": desc, "fork": fork,
            "archived": archived, "size": size, "stargazers_count": stars, "topics": list(topics)}


def enricher(handler, **kw):
    calls = []

    def wrapped(request):
        calls.append(request)
        return handler(request)
    e = GitHubEnricher(http=httpx.Client(transport=httpx.MockTransport(wrapped)), now=lambda: NOW, **kw)
    return e, calls


def ok(repos):
    return lambda request: httpx.Response(200, json=repos)


def test_successful_enrichment_counts_relevant_repos():
    e, _ = enricher(ok([
        repo("rag-bot", 5, "Python", "RAG chatbot with embeddings"),
        repo("scripts", 40, "Python"),
        repo("site", 20, "JavaScript"),
        repo("old-llm", 200, "Python", "LLM agent"),
        repo("forked", 1, "Python", fork=True),
        repo("dead", 1, "Python", archived=True),
        repo("empty", 1, "Python", size=0),
    ]))
    g = e("asha")
    assert g.status is GitHubStatus.OK and g.public_repos == 7 and g.relevant_repos == 4
    assert g.recently_active_repos == 3 and g.python_repos == 3 and g.ai_repos == 2
    assert g.maintained and g.top_languages[0] == "Python"


def test_recent_window_is_configurable():
    repos = [repo("a", 30), repo("b", 100)]
    assert enricher(ok(repos), recent_days=90)[0]("u").recently_active_repos == 1
    assert enricher(ok(repos), recent_days=365)[0]("u").recently_active_repos == 2
    assert GitHubEnricher.from_env({"GITHUB_RECENT_DAYS": "30"}).recent_days == 30
    assert GitHubEnricher.from_env({"GITHUB_RECENT_DAYS": "junk"}).recent_days == 90


def test_missing_github_is_not_an_error():
    e, calls = enricher(ok([]))
    for name in (None, "", "bad name!"):
        assert e(name).status is GitHubStatus.NOT_PROVIDED
    assert calls == []


def test_404_rate_limit_timeout_and_network_failures_become_statuses():
    cases = {
        GitHubStatus.NOT_FOUND: lambda r: httpx.Response(404, json={"message": "Not Found"}),
        GitHubStatus.RATE_LIMITED: lambda r: httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={}),
        "429": lambda r: httpx.Response(429, json={}),
        "msg": lambda r: httpx.Response(403, json={"message": "API rate limit exceeded for 1.2.3.4"}),
        GitHubStatus.ERROR: lambda r: httpx.Response(500, text="boom"),
        "non-list": lambda r: httpx.Response(200, json={"message": "hello"}),
    }
    assert enricher(cases[GitHubStatus.NOT_FOUND])[0]("u").status is GitHubStatus.NOT_FOUND
    assert enricher(cases[GitHubStatus.RATE_LIMITED])[0]("u").status is GitHubStatus.RATE_LIMITED
    assert enricher(cases["429"])[0]("u").status is GitHubStatus.RATE_LIMITED
    assert enricher(cases["msg"])[0]("u").status is GitHubStatus.RATE_LIMITED
    assert enricher(cases[GitHubStatus.ERROR])[0]("u").status is GitHubStatus.ERROR
    assert enricher(cases["non-list"])[0]("u").status is GitHubStatus.ERROR

    def timeout(request):
        raise httpx.ConnectTimeout("slow", request=request)

    def down(request):
        raise httpx.ConnectError("no route", request=request)
    t = enricher(timeout)[0]("u")
    assert t.status is GitHubStatus.ERROR and "timed out" in t.error
    assert enricher(down)[0]("u").status is GitHubStatus.ERROR


def test_username_is_fetched_once_per_run_even_for_failures():
    e, calls = enricher(ok([repo()]))
    first = e("Asha")
    assert e("asha") is first and e("ASHA") is first and len(calls) == 1
    e2, calls2 = enricher(lambda r: httpx.Response(404, json={}))
    e2("ghost"); e2("ghost")
    assert len(calls2) == 1


def test_token_is_sent_only_when_configured_and_never_exposed():
    e, calls = enricher(ok([]), token="ghp_SECRETTOKEN")
    e("u")
    assert calls[0].headers["authorization"] == "Bearer ghp_SECRETTOKEN"
    assert "ghp_SECRETTOKEN" not in repr(e)
    e2, calls2 = enricher(ok([]))
    e2("u")
    assert "authorization" not in calls2[0].headers


def test_github_points_stay_within_0_to_10_and_ignore_stars():
    best = GitHubEnrichment(status=GitHubStatus.OK, recently_active_repos=50, python_repos=50, ai_repos=50, maintained=True)
    assert github_points(best)[0] == 10
    assert github_points(GitHubEnrichment(status=GitHubStatus.OK))[0] == 0
    low = GitHubEnrichment(status=GitHubStatus.OK, recently_active_repos=1, python_repos=1)
    assert github_points(low)[0] == 2 + 1
    assert github_points(low.model_copy(update={"total_stars": 100000})) == github_points(low)
    for status in (GitHubStatus.NOT_FOUND, GitHubStatus.ERROR, GitHubStatus.RATE_LIMITED, GitHubStatus.NOT_PROVIDED):
        assert github_points(GitHubEnrichment(status=status, recently_active_repos=9, python_repos=9))[0] == 0
    assert github_points(None)[0] == 0


def eligible(name="cand", url="github.com/asha-verma"):
    r = make_resume(name, projects=[STRONG_PROJECT])
    return r.model_copy(update={"github_url": url, "raw_text": RAW_TEXT})


def test_github_points_enter_the_final_score_deterministically():
    e, _ = enricher(ok([repo("rag-agent", 5, "Python", "LLM agent")]))
    gh = e("asha-verma")
    base = score_resume(eligible())
    with_gh = score_resume(eligible(), gh)
    assert with_gh.github_activity == github_points(gh)[0] > 0
    assert with_gh.total == base.total + with_gh.github_activity <= 100
    assert with_gh == score_resume(eligible(), gh)


def test_github_failure_never_fails_the_candidate_or_batch():
    resumes = [eligible("a.pdf"), eligible("b.pdf", url=None), eligible("c.pdf")]
    for handler in (lambda r: httpx.Response(404, json={}), lambda r: httpx.Response(429, json={})):
        e, _ = enricher(handler)
        results = screen_batch(resumes, e)
        assert all(r.status is ScreeningStatus.RANKED for r in results)
        assert all(r.score.github_activity == 0 for r in results)
        assert any("GitHub not scored" in c for r in results for c in r.concerns)
        assert any("No GitHub profile" in c for r in results for c in r.concerns)


def test_enricher_that_raises_still_cannot_fail_a_candidate():
    def broken(username):
        raise RuntimeError("bug in enricher")
    r = screen_batch([eligible()], broken)[0]
    assert r.status is ScreeningStatus.RANKED and r.github.status is GitHubStatus.ERROR


def test_rejected_candidates_never_trigger_a_github_call():
    called = []
    rejected = make_resume("java", skills=["Java"]).model_copy(update={"github_url": "github.com/x", "raw_text": "java dev"})
    r = screen_batch([rejected], lambda u: called.append(u))[0]
    assert r.status is ScreeningStatus.REJECTED and called == [] and r.github is None
