from ..config import get_settings
from .base import GraderProvider, STTProvider, TTSProvider
from .stub import StubGrader, StubSTT, StubTTS


def get_stt() -> STTProvider:
    name = get_settings().stt_provider
    if name == "stub":
        return StubSTT()
    raise NotImplementedError(f"STT provider {name!r}")  # TODO: choose after stage-2 test


def get_grader() -> GraderProvider:
    name = get_settings().llm_provider
    if name == "stub":
        return StubGrader()
    raise NotImplementedError(f"LLM provider {name!r}")


def get_tts() -> TTSProvider:
    name = get_settings().tts_provider
    if name == "stub":
        return StubTTS()
    raise NotImplementedError(f"TTS provider {name!r}")
