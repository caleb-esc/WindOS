import tempfile
from pathlib import Path
from windos.core import engine
from windos.core.auth import authenticate


def test_password_authentication_round_trip(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        engine.set_root(tmp)
        salt, digest = engine.hash_pw("correct horse battery staple")
        engine.jsave(engine.USERS_F, {
            "tester": {"salt": salt, "hash": digest, "groups": ["users"], "home": "/home/tester"}
        })
        assert authenticate("tester", "correct horse battery staple")["name"] == "tester"
        assert authenticate("tester", "wrong") is None
        assert authenticate("missing", "anything") is None
