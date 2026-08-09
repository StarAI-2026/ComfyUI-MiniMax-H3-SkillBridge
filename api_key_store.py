from __future__ import annotations

import os
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent
_DOTENV = PLUGIN_DIR / ".env"
_ENV_KEY = "SKILLBRIDGE_API_KEY"


def _load_dotenv() -> None:
    """Load SKILLBRIDGE_API_KEY from the plugin-local .env file if present.

    This keeps the API key out of the workflow JSON entirely. The .env file is
    git-ignored so it is never committed or shared.
    """
    if not _DOTENV.is_file():
        return
    try:
        lines = _DOTENV.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == _ENV_KEY:
            # Preserve the whole value after the first '=', already stripped.
            os.environ.setdefault(_ENV_KEY, value.strip().strip('"').strip("'"))


def get_api_key() -> str:
    """Return the API key from env var or plugin-local .env. Empty if unset."""
    _load_dotenv()
    return os.getenv(_ENV_KEY, "").strip()