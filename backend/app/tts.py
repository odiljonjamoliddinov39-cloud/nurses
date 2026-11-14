"""Text-to-speech through Azure Speech (REST). Returns MP3 bytes; raises TTSError with a message an admin can act on."""
import re
from xml.sax.saxutils import escape

import httpx

MAX_CHARS = 8000  # keeps one clip well under Azure's 10-minute limit
VOICE_RE = re.compile(r"^[a-z]{2,3}-[A-Z]{2}-[A-Za-z0-9]+$")
REGION_RE = re.compile(r"^[a-z0-9-]{3,30}$")
OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
LANGS = ("uz", "ru")


class TTSError(Exception):
    """`fatal` = every further request would fail the same way (bad key/region), so a batch should stop."""

    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


def build_ssml(text: str, voice: str) -> str:
    lang = voice[: voice.rindex("-")]  # "uz-UZ-MadinaNeural" -> "uz-UZ"
    return (f"<speak version='1.0' xml:lang='{lang}' xmlns='http://www.w3.org/2001/10/synthesis'>"
            f"<voice name='{voice}'>{escape(text)}</voice></speak>")


async def synthesize(text: str, *, key: str, region: str, voice: str,
                     transport: httpx.AsyncBaseTransport | None = None) -> bytes:
    text = (text or "").strip()
    if not text:
        raise TTSError("there is no text to read")
    if len(text) > MAX_CHARS:
        raise TTSError(f"the text is too long ({len(text)} characters, the limit is {MAX_CHARS})")
    if not key or not region:
        raise TTSError("set the Azure Speech key and region in Settings first", fatal=True)
    if not REGION_RE.match(region):
        raise TTSError("the Azure region looks wrong (use e.g. westeurope)", fatal=True)
    if not VOICE_RE.match(voice or ""):
        raise TTSError(f"the voice name {voice!r} looks wrong (e.g. uz-UZ-MadinaNeural)", fatal=True)
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    headers = {"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
               "X-Microsoft-OutputFormat": OUTPUT_FORMAT, "User-Agent": "oral-exam-trainer"}
    try:
        async with httpx.AsyncClient(timeout=60, transport=transport) as client:
            r = await client.post(url, headers=headers, content=build_ssml(text, voice).encode("utf-8"))
    except httpx.HTTPError as exc:
        raise TTSError(f"could not reach Azure Speech ({type(exc).__name__})")
    if r.status_code in (401, 403):
        raise TTSError("Azure rejected the key or region: check both in Settings", fatal=True)
    if r.status_code == 429:
        raise TTSError("Azure is rate-limiting requests: wait a minute and try again")
    if r.status_code == 400:
        raise TTSError(f"Azure refused the request (is the voice {voice} available in region {region}?)")
    if r.status_code != 200 or not r.content:
        raise TTSError(f"Azure Speech returned HTTP {r.status_code}")
    return r.content
