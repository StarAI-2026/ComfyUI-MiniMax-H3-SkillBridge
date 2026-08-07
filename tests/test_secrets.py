import importlib.util
import os
import sys
from pathlib import Path


def load_secrets():
    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location(
        "starai_skillbridge_secrets_test", root / "secrets.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["starai_skillbridge_secrets_test"] = module
    spec.loader.exec_module(module)
    return module


def test_get_api_key_from_env(monkeypatch):
    secrets = load_secrets()
    monkeypatch.setenv("SKILLBRIDGE_API_KEY", "sk-test-123")
    assert secrets.get_api_key() == "sk-test-123"


def test_get_api_key_empty_when_unset(monkeypatch):
    secrets = load_secrets()
    monkeypatch.delenv("SKILLBRIDGE_API_KEY", raising=False)
    assert secrets.get_api_key() == ""