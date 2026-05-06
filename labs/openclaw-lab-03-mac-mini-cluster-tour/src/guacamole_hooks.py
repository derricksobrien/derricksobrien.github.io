"""
guacamole_hooks.py
------------------
Extension points for Apache Guacamole remote-access integration.

Every function here is intentionally a STUB. Replace the bodies with
your real Guacamole REST calls once you have your environment wired up.
"""

from __future__ import annotations

import os


def check_session_ready() -> tuple[bool, str]:
    base_url = os.getenv("GUACAMOLE_BASE_URL", "").strip()
    connection_id = os.getenv("GUACAMOLE_CONNECTION_ID", "").strip()

    if not base_url:
        return True, "stub_no_url_configured"

    return True, f"stub_url_present id={connection_id or 'unset'}"


def open_lab_session(participant_name: str = "") -> tuple[bool, str]:
    _ = participant_name
    return True, "stub_session_opened"


def close_lab_session(session_token: str = "") -> None:
    _ = session_token
    return


def _get_auth_token(base_url: str) -> str:
    import requests

    username = os.getenv("GUACAMOLE_USERNAME", "guacadmin")
    password = os.getenv("GUACAMOLE_PASSWORD", "")

    resp = requests.post(
        f"{base_url}/api/tokens",
        data={"username": username, "password": password},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["authToken"]