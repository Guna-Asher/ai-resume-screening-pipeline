import re
from pathlib import Path

from src.pipeline import screen_batch
from src.screening import check_eligibility, score_resume

from .factories import PLATFORM_JOB, STRONG_PROJECT, WRAPPER_PROJECT, make_resume


def test_same_resume_always_gives_identical_output():
    r = make_resume(projects=[STRONG_PROJECT, WRAPPER_PROJECT], experience=[PLATFORM_JOB])
    runs = [(check_eligibility(r), score_resume(r)) for _ in range(5)]
    assert all(run == runs[0] for run in runs)
    elig, score = runs[0]
    assert elig.eligible and score.total == score.model_dump()["total"]


def test_ranking_depends_only_on_inputs_not_input_order():
    batch = [make_resume("a", projects=[STRONG_PROJECT], experience=[PLATFORM_JOB]),
             make_resume("b", projects=[STRONG_PROJECT]),
             make_resume("c", projects=[WRAPPER_PROJECT]),
             make_resume("d", projects=[STRONG_PROJECT])]  # ties with b -> broken by file name
    order = lambda rs: [r.source_file for r in screen_batch(rs) if r.rank]  # noqa: E731
    assert order(batch) == order(list(reversed(batch))) == ["a.pdf", "b.pdf", "d.pdf", "c.pdf"]


def test_screening_code_has_no_randomness_time_or_network():
    banned = re.compile(r"^\s*(?:import|from)\s+(random|time|datetime|httpx|requests|urllib|socket|openai)\b", re.M)
    for f in Path("src/screening").glob("*.py"):
        assert not banned.search(f.read_text()), f
