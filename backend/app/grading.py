"""Grading. Default is self-check (no AI, no cost): the user ticks the key points they covered.
Optional AI mode sends the recording to Google Gemini, which transcribes and grades in one call."""
import base64
import json
import logging
import re

import httpx

from .services import round_half

log = logging.getLogger("uvicorn.error")


def self_check_score(key_points: list[tuple[int, float]], covered_ids: set[int]) -> float:
    """Weighted share of covered key points, scaled to 0-5 in steps of 0.5."""
    total = sum(max(w, 0) for _, w in key_points)
    if total <= 0:
        return 0.0
    got = sum(max(w, 0) for kp_id, w in key_points if kp_id in covered_ids)
    return round_half(5 * got / total)


PROMPT = """You are a strict but fair examiner for an oral qualification exam for nurses.
The audio is the candidate's spoken answer (usually Uzbek, sometimes Russian).

Question:
{question}

Model answer:
{model_answer}

Key points (id: weight: text):
{key_points}

{rules}

Tasks:
1. Transcribe the answer exactly as spoken, in the language spoken.
2. Decide which key points the answer covers (meaning matters, not exact words).
3. List medically wrong statements, if any.
4. Score 0-5 in steps of 0.5: weighted share of covered key points times 5, minus 0.5-1.5 for
   each medically dangerous or wrong statement. Silence or an unrelated answer scores 0.
5. Write a 2-4 sentence comment and a short "what to add", in the language of the question.

Reply with JSON only:
{{"transcript": str, "covered": [key point ids], "wrong": [str], "score": number,
  "comment": str, "what_to_add": str}}"""


class AIError(RuntimeError):
    pass


def parse_ai_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise AIError("no JSON in model reply")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise AIError(f"bad JSON: {exc}")
    if not isinstance(data, dict):
        raise AIError("reply is not an object")
    return data


async def gemini_grade(*, api_key: str, model: str, audio: bytes, content_type: str, question: str,
                       model_answer: str, key_points: list[tuple[int, float, str]], rules: str) -> dict:
    if not api_key:
        raise AIError("Gemini API key is not set")
    kp_text = "\n".join(f"{i}: {w}: {t}" for i, w, t in key_points) or "(none: compare with the model answer)"
    prompt = PROMPT.format(question=question, model_answer=model_answer, key_points=kp_text,
                           rules=f"Extra rules:\n{rules}" if rules else "")
    mime = content_type if content_type.startswith("audio/") else "audio/webm"
    body = {
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(audio).decode()}},
        ]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(url, params={"key": api_key}, json=body)
    except httpx.HTTPError as exc:
        raise AIError(f"network error: {exc}")
    if r.status_code != 200:
        raise AIError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    payload = r.json()
    try:
        text = "".join(p.get("text", "") for p in payload["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError, TypeError):
        raise AIError(f"unexpected Gemini reply: {str(payload)[:300]}")
    data = parse_ai_json(text)
    valid_ids = {i for i, _, _ in key_points}
    covered = [int(x) for x in data.get("covered", []) if str(x).lstrip("-").isdigit() and int(x) in valid_ids]
    try:
        score = round_half(float(data.get("score", 0)))
    except (TypeError, ValueError):
        score = 0.0
    usage = payload.get("usageMetadata") or {}
    return {
        "transcript": str(data.get("transcript", ""))[:20000],
        "covered": covered,
        "wrong": [str(x)[:500] for x in data.get("wrong", []) if x][:20],
        "score": score,
        "comment": str(data.get("comment", ""))[:3000],
        "what_to_add": str(data.get("what_to_add", ""))[:3000],
        "tokens": int(usage.get("totalTokenCount") or 0),
    }
