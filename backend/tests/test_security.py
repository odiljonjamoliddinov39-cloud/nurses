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
