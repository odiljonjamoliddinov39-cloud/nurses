import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.security import InitDataError, verify_init_data

TOKEN = "123:TEST"


def make_init_data(token=TOKEN, auth_date=None, user=None):
    fields = {"auth_date": str(auth_date or int(time.time())),
              "user": json.dumps(user or {"id": 42, "first_name": "Ana"})}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_valid():
    data = verify_init_data(make_init_data(), TOKEN)
    assert data["user"]["id"] == 42


def test_bad_signature():
    with pytest.raises(InitDataError):
        verify_init_data(make_init_data(token="other:TOKEN"), TOKEN)


def test_expired():
    with pytest.raises(InitDataError):
        verify_init_data(make_init_data(auth_date=1000), TOKEN, max_age=60)


def test_missing_hash():
    with pytest.raises(InitDataError):
        verify_init_data("auth_date=1", TOKEN)


def test_empty_bot_token_rejected():
    with pytest.raises(InitDataError):
        verify_init_data(make_init_data(token=""), "")


# --- Telegram Login Widget (browser admin sign-in) and admin sessions ---
from app.security import make_admin_session, read_admin_session, verify_login_widget  # noqa: E402


def make_widget(token=TOKEN, auth_date=None, **extra):
    fields = {"id": 42, "first_name": "Ana", "auth_date": auth_date or int(time.time()), **extra}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    fields["hash"] = hmac.new(hashlib.sha256(token.encode()).digest(), check.encode(), hashlib.sha256).hexdigest()
    return fields


def test_widget_valid():
    assert verify_login_widget(make_widget(username="ana"), TOKEN)["id"] == "42"


def test_widget_bad_signature():
    with pytest.raises(InitDataError):
        verify_login_widget(make_widget(token="other:TOKEN"), TOKEN)


def test_widget_tampered_id():
    fields = make_widget()
    fields["id"] = 43
    with pytest.raises(InitDataError):
        verify_login_widget(fields, TOKEN)


def test_widget_expired():
    with pytest.raises(InitDataError):
        verify_login_widget(make_widget(auth_date=1000), TOKEN, max_age=60)


def test_widget_initdata_key_not_accepted():
    # A Mini App initData hash (different key derivation) must not pass as a widget login.
    fields = {"id": 42, "auth_date": int(time.time())}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    with pytest.raises(InitDataError):
        verify_login_widget(fields, TOKEN)


def test_session_roundtrip():
    token, _ = make_admin_session(42, TOKEN, ttl=60)
    assert read_admin_session(token, TOKEN) == 42


def test_session_expired():
    token, _ = make_admin_session(42, TOKEN, ttl=60, now=1000)
    with pytest.raises(InitDataError):
        read_admin_session(token, TOKEN, now=2000)


def test_session_forged():
    token, _ = make_admin_session(42, TOKEN, ttl=60)
    _, exp, sig = token.split(".")
    with pytest.raises(InitDataError):
        read_admin_session(f"43.{exp}.{sig}", TOKEN)
    with pytest.raises(InitDataError):
        read_admin_session(token, "other:TOKEN")
    with pytest.raises(InitDataError):
        read_admin_session("garbage", TOKEN)


# --- grading helpers ---
from app.grading import AIError, parse_ai_json, self_check_score  # noqa: E402


def test_self_check_score_weighted():
    kps = [(1, 1.0), (2, 2.0), (3, 2.0)]
    assert self_check_score(kps, {2, 3}) == 4.0
    assert self_check_score(kps, set()) == 0.0
    assert self_check_score(kps, {1, 2, 3}) == 5.0
    assert self_check_score([], {1}) == 0.0


def test_parse_ai_json():
    assert parse_ai_json('```json\n{"score": 4}\n```')["score"] == 4
    with pytest.raises(AIError):
        parse_ai_json("no json here")
