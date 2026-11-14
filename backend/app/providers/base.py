"""Swappable AI provider interfaces (STT / LLM grader / TTS). Chosen by config."""
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class GradeResult:
    score: float  # 0-5, step 0.5
    covered: list[str] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)
    wrong: list[str] = field(default_factory=list)
    comment: str = ""
    what_to_add: str = ""
    cost: float = 0.0


class STTProvider(Protocol):
    async def transcribe(self, audio: bytes, language: str) -> str: ...


class GraderProvider(Protocol):
    async def grade(self, *, question: str, model_answer: str,
                    key_points: list[tuple[str, float]], transcript: str,
                    rules: str) -> GradeResult: ...


class TTSProvider(Protocol):
    async def synthesize(self, text: str, language: str) -> bytes: ...
