"""Stub providers for local development and tests."""
from .base import GradeResult


class StubSTT:
    async def transcribe(self, audio: bytes, language: str) -> str:
        return "stub transcript"


class StubGrader:
    async def grade(self, *, question, model_answer, key_points, transcript, rules) -> GradeResult:
        covered = [t for t, _ in key_points if t.lower() in transcript.lower()]
        total = sum(w for _, w in key_points) or 1.0
        got = sum(w for t, w in key_points if t in covered)
        score = round(5 * got / total * 2) / 2
        return GradeResult(score=score, covered=covered,
                           missed=[t for t, _ in key_points if t not in covered])


class StubTTS:
    async def synthesize(self, text: str, language: str) -> bytes:
        return b""
