"""Azure TTS client: request format and error mapping (no network: httpx MockTransport)."""
import httpx
import pytest

from app import tts


def transport(status=200, body=b"ID3\x03fakemp3", seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, content=body)
    return httpx.MockTransport(handler)


async def test_request_format():
    seen = []
    audio = await tts.synthesize("Salom <dunyo> & hamma", key="K3Y", region="westeurope", voice="uz-UZ-MadinaNeural",
                                 transport=transport(seen=seen))
    assert audio.startswith(b"ID3")
    req = seen[0]
    assert str(req.url) == "https://westeurope.tts.speech.microsoft.com/cognitiveservices/v1"
    assert req.headers["Ocp-Apim-Subscription-Key"] == "K3Y"
    assert req.headers["Content-Type"] == "application/ssml+xml"
    assert req.headers["X-Microsoft-OutputFormat"] == "audio-24khz-48kbitrate-mono-mp3"
    body = req.content.decode()
    assert "xml:lang='uz-UZ'" in body and "<voice name='uz-UZ-MadinaNeural'>" in body
    assert "Salom &lt;dunyo&gt; &amp; hamma" in body            # text is escaped, SSML cannot be injected


def test_ssml_language_comes_from_voice():
    assert "xml:lang='ru-RU'" in tts.build_ssml("Привет", "ru-RU-SvetlanaNeural")


@pytest.mark.parametrize("status,fatal,needle", [(401, True, "rejected the key"), (403, True, "rejected the key"),
                                                 (429, False, "rate-limiting"), (400, False, "refused"), (500, False, "HTTP 500")])
async def test_error_mapping(status, fatal, needle):
    with pytest.raises(tts.TTSError) as e:
        await tts.synthesize("x", key="k", region="westeurope", voice="uz-UZ-MadinaNeural", transport=transport(status))
    assert needle in str(e.value) and e.value.fatal is fatal


async def test_input_validation_never_reaches_the_network():
    seen = []
    t = transport(seen=seen)
    kw = dict(key="k", region="westeurope", voice="uz-UZ-MadinaNeural", transport=t)
    for text, patch, needle in (("", {}, "no text"), ("x" * 8001, {}, "too long"),
                                ("x", {"key": ""}, "Settings"), ("x", {"region": "bad region!"}, "region"),
                                ("x", {"voice": "'; DROP"}, "voice name")):
        with pytest.raises(tts.TTSError) as e:
            await tts.synthesize(text, **{**kw, **patch})
        assert needle in str(e.value)
    assert seen == []


async def test_empty_audio_is_an_error():
    with pytest.raises(tts.TTSError):
        await tts.synthesize("x", key="k", region="westeurope", voice="uz-UZ-MadinaNeural", transport=transport(200, b""))
