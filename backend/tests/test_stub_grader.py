import asyncio

from app.providers.stub import StubGrader


def test_stub_grader_scores_by_weight():
    r = asyncio.run(StubGrader().grade(
        question="q", model_answer="m", rules="",
        key_points=[("heart", 3.0), ("lung", 1.0)], transcript="the heart pumps"))
    assert r.covered == ["heart"]
    assert r.score == 4.0
