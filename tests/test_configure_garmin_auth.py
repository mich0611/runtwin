import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "configure_garmin_auth.py"


def load_script():
    spec = importlib.util.spec_from_file_location("configure_garmin_auth", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_garminconnect(monkeypatch, *, fail=False, write_tokens=True):
    calls = {}

    class FakeGarmin:
        def __init__(self, email, password, is_cn=False, prompt_mfa=None):
            calls.update(email=email, password=password, is_cn=is_cn, prompt_mfa=prompt_mfa)

        def login(self, tokenstore):
            calls["tokenstore"] = tokenstore
            if fail:
                raise RuntimeError("bad credentials")
            if write_tokens:
                Path(tokenstore, "garmin_tokens.json").write_text("{}", encoding="utf-8")

    module = ModuleType("garminconnect")
    module.Garmin = FakeGarmin
    monkeypatch.setitem(sys.modules, "garminconnect", module)
    return calls


def run(monkeypatch, tmp_path, *extra):
    env_file = tmp_path / ".env"
    env_file.write_text("DJANGO_DEBUG=0\nRUNTWIN_GARMIN_ENABLED=0\n# RUNTWIN_GARMIN_TOKEN_DIR=keep-comment\n", encoding="utf-8")
    token_dir = tmp_path / "tokens"
    monkeypatch.setattr("sys.argv", ["x", "--email", "runner@example.com", "--token-dir", str(token_dir), "--env-file", str(env_file), *extra])
    monkeypatch.setattr("getpass.getpass", lambda prompt: "secret-password")
    return load_script().main(), env_file, token_dir


def test_saves_tokens_and_enables_garmin_in_env(monkeypatch, tmp_path):
    calls = fake_garminconnect(monkeypatch)

    code, env_file, token_dir = run(monkeypatch, tmp_path)

    assert code == 0
    assert calls["email"] == "runner@example.com"
    assert calls["tokenstore"] == str(token_dir.resolve())
    assert callable(calls["prompt_mfa"])
    env = env_file.read_text(encoding="utf-8")
    assert "RUNTWIN_GARMIN_ENABLED=1" in env
    assert f"RUNTWIN_GARMIN_TOKEN_DIR={token_dir}" in env
    assert "# RUNTWIN_GARMIN_TOKEN_DIR=keep-comment" in env
    assert "secret-password" not in env


def test_no_env_flag_leaves_env_untouched(monkeypatch, tmp_path):
    fake_garminconnect(monkeypatch)

    code, env_file, _ = run(monkeypatch, tmp_path, "--no-env")

    assert code == 0
    assert "RUNTWIN_GARMIN_ENABLED=0" in env_file.read_text(encoding="utf-8")


@pytest.mark.parametrize(("kwargs", "expected"), [({"fail": True}, 1), ({"write_tokens": False}, 1)])
def test_login_failure_or_missing_tokens_does_not_enable_garmin(monkeypatch, tmp_path, kwargs, expected):
    fake_garminconnect(monkeypatch, **kwargs)

    code, env_file, _ = run(monkeypatch, tmp_path)

    assert code == expected
    assert "RUNTWIN_GARMIN_ENABLED=0" in env_file.read_text(encoding="utf-8")
