"""
guacamole_hooks.py
------------------
Extension points for Apache Guacamole remote-access integration.

Every function here is intentionally a STUB.  Replace the bodies with
your real Guacamole REST calls once you have your environment wired up.

Environment variables read by these hooks (set via .env or your CI env):
  GUACAMOLE_BASE_URL       e.g. https://lab.yourdomain.com/guacamole
  GUACAMOLE_CONNECTION_ID  numeric or named connection identifier
  GUACAMOLE_USERNAME       admin or lab-session user
  GUACAMOLE_PASSWORD       (keep out of version control)
  GUACAMOLE_LAB_NOTES      freeform text shown in the lab runner output

Guacamole REST API reference:
  https://guacamole.apache.org/doc/gug/guacamole-rest-api.html
"""

from __future__ import annotations

import os


# ---------------------------------------------------------------------------
# Stage 0 hook: called during preflight
# ---------------------------------------------------------------------------

def check_session_ready() -> tuple[bool, str]:
    """
    Return (ok, detail_string).

    Stub behaviour: passes unless GUACAMOLE_BASE_URL is set but unreachable.

    Replace with:
      - HTTP GET to {GUACAMOLE_BASE_URL}/api/session/data/default/connections
      - Validate that GUACAMOLE_CONNECTION_ID exists in the response
      - Return (False, "connection not found") if the lab is offline
    """
    base_url = os.getenv("GUACAMOLE_BASE_URL", "").strip()
    connection_id = os.getenv("GUACAMOLE_CONNECTION_ID", "").strip()

    if not base_url:
        return True, "stub_no_url_configured"

    # TODO: replace the block below with a real HTTP health check
    # Example:
    #   import requests
    #   token = _get_auth_token(base_url)
    #   resp = requests.get(
    #       f"{base_url}/api/session/data/default/connections/{connection_id}",
    #       headers={"Guacamole-Token": token},
    #       timeout=5,
    #   )
    #   if resp.status_code == 200:
    #       return True, f"connection_ready id={connection_id}"
    #   return False, f"connection_unavailable status={resp.status_code}"

    return True, f"stub_url_present id={connection_id or 'unset'}"


# ---------------------------------------------------------------------------
# Stage 1 hook: called after auth check, before first API call
# ---------------------------------------------------------------------------

def open_lab_session(participant_name: str = "") -> tuple[bool, str]:
    """
    Open or reserve a Guacamole session for this lab participant.

    Return (ok, session_token_or_error_detail).

    Replace with:
      - POST to {GUACAMOLE_BASE_URL}/api/tokens with username/password
      - Record the returned Guacamole-Token for subsequent calls
      - Optionally create a time-boxed connection (45 min)
    """
    # TODO: implement real session open
    # token = _get_auth_token(base_url)
    # connection_url = f"{base_url}/#/client/{_encode_connection_id(connection_id)}"
    # return True, connection_url

    _ = participant_name  # consume arg to avoid linter warning
    return True, "stub_session_opened"


# ---------------------------------------------------------------------------
# Stage 3 / post-run hook: called after the lab run completes
# ---------------------------------------------------------------------------

def close_lab_session(session_token: str = "") -> None:
    """
    Close and reset the Guacamole session.

    Replace with:
      - DELETE to {GUACAMOLE_BASE_URL}/api/session/data/default/activeConnections/{id}
      - Or POST reset to restore lab snapshot
    """
    # TODO: implement real session teardown
    # import requests
    # requests.delete(
    #     f"{os.getenv('GUACAMOLE_BASE_URL')}/api/tokens/{session_token}",
    #     timeout=5,
    # )
    _ = session_token
    return


# ---------------------------------------------------------------------------
# Utility: used internally by the stubs above when you wire up auth
# ---------------------------------------------------------------------------

def _get_auth_token(base_url: str) -> str:
    """
    Authenticate to Guacamole and return a session token.

    Called internally by check_session_ready and open_lab_session once
    you replace the stubs with real HTTP calls.

    Reads:
      GUACAMOLE_USERNAME (default: guacadmin)
      GUACAMOLE_PASSWORD
    """
    import requests  # noqa: PLC0415 — lazy import so stub remains dep-free

    username = os.getenv("GUACAMOLE_USERNAME", "guacadmin")
    password = os.getenv("GUACAMOLE_PASSWORD", "")

    resp = requests.post(
        f"{base_url}/api/tokens",
        data={"username": username, "password": password},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["authToken"]
