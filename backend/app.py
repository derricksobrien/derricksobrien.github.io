from __future__ import annotations

import os
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, session
from flask_cors import CORS


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bookings.db"

ACCESS_CHECK_WINDOW_SECONDS = int(os.getenv("ACCESS_CHECK_WINDOW_SECONDS", "60"))
ACCESS_CHECK_MAX_PER_WINDOW = int(os.getenv("ACCESS_CHECK_MAX_PER_WINDOW", "20"))

_ACCESS_ATTEMPTS: dict[str, list[datetime]] = {}
_ATTEMPTS_LOCK = threading.Lock()

LAB_ACCESS_MAP = {
    "claude api in action": {
        "labTitle": "Claude API in Action",
        "repoUrl": "https://github.com/derricksobrien/nexetra-lab-01-claude-api-tour",
        "catalogPath": "../catalog.html?track=anthropic",
        "catalogLabel": "Open Anthropic track catalog",
        "instructions": [
            "Clone the Lab 01 repository and run scripts/setup.ps1.",
            "Use scripts/run-lab.ps1 -Stage all for a dry run.",
            "Add ANTHROPIC_API_KEY in .env before live mode."
        ],
    },
    "gpu inference live": {
        "labTitle": "GPU Inference Live",
        "repoUrl": "https://github.com/derricksobrien/nvidia-lab-02-blackwell-inference-tour",
        "catalogPath": "../catalog.html?track=nvidia",
        "catalogLabel": "Open NVIDIA track catalog",
        "instructions": [
            "Clone the Lab 02 repository and run scripts/setup.ps1.",
            "Run scripts/run-lab.ps1 -Stage all for a dry run.",
            "Set NVIDIA_API_KEY in .env before live inference."
        ],
    },
    "inside the openclaw cluster": {
        "labTitle": "Inside the OpenClaw Cluster",
        "repoUrl": "https://github.com/derricksobrien/openclaw-lab-03-mac-mini-cluster-tour",
        "catalogPath": "../catalog.html?track=openclaw",
        "catalogLabel": "Open OpenClaw track catalog",
        "instructions": [
            "Clone the Lab 03 repository and run scripts/setup.ps1.",
            "Run scripts/run-lab.ps1 -Stage all for a dry run.",
            "Set OPENCLAW_ACCESS_TOKEN in .env before live mode."
        ],
    },
}


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "change-this-in-production")
    app.config["SESSION_COOKIE_NAME"] = "nexetra_session"
    app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"

    allowed_origins = [
        origin.strip()
        for origin in os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:8000,http://127.0.0.1:8000,https://derricksobrien.github.io",
        ).split(",")
        if origin.strip()
    ]
    CORS(app, supports_credentials=True, origins=allowed_origins)

    init_db()

    @app.get("/api/health")
    def health() -> Any:
        return jsonify({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})

    @app.get("/api/session")
    def get_session() -> Any:
        session_id = get_or_create_session_id()
        return jsonify({"sessionId": session_id})

    @app.post("/api/bookings")
    def create_booking() -> Any:
        session_id = get_or_create_session_id()
        payload = request.get_json(silent=True) or {}

        validation_error = validate_payload(payload)
        if validation_error:
            return jsonify({"error": validation_error}), 400

        booking_id = uuid.uuid4().hex[:12]
        access_token = secrets.token_urlsafe(24)
        now_utc = datetime.now(timezone.utc)
        expires_at_utc = now_utc + timedelta(hours=int(os.getenv("ACCESS_TOKEN_TTL_HOURS", "72")))

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO bookings (
                    booking_id, session_id, created_at_utc,
                    name, email, lab, user_timezone, slot, goal, source_page, user_agent,
                    access_token, access_expires_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    booking_id,
                    session_id,
                    now_utc.isoformat(),
                    payload["name"].strip(),
                    payload["email"].strip().lower(),
                    payload["lab"].strip(),
                    payload.get("timezone", "").strip(),
                    payload["slot"].strip(),
                    payload.get("goal", "").strip(),
                    payload.get("sourcePage", "").strip(),
                    request.headers.get("User-Agent", "")[:255],
                    access_token,
                    expires_at_utc.isoformat(),
                ),
            )
            conn.commit()

        return (
            jsonify(
                {
                    "status": "stored",
                    "bookingId": booking_id,
                    "sessionId": session_id,
                    "accessToken": access_token,
                    "accessPath": f"/api/access/{access_token}",
                    "expiresAtUtc": expires_at_utc.isoformat(),
                }
            ),
            201,
        )

    @app.get("/api/access/<access_token>")
    def get_access(access_token: str) -> Any:
        session_id = get_or_create_session_id()

        throttle_error = check_rate_limit(session_id)
        if throttle_error:
            return jsonify({"error": throttle_error}), 429

        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT booking_id, lab, slot, access_token, access_expires_at_utc
                FROM bookings
                WHERE access_token = ?
                """,
                (access_token,),
            ).fetchone()

        if not row:
            return jsonify({"error": "Invalid access token"}), 404

        expires_at = parse_utc(row["access_expires_at_utc"])
        if expires_at <= datetime.now(timezone.utc):
            return jsonify({"error": "Access token expired. Request a new booking token."}), 410

        lab_key = normalize_lab_key(row["lab"])
        lab_access = LAB_ACCESS_MAP.get(lab_key)
        if not lab_access:
            return jsonify({"error": "Lab mapping not found for this booking."}), 422

        return jsonify(
            {
                "bookingId": row["booking_id"],
                "labTitle": lab_access["labTitle"],
                "slot": row["slot"],
                "expiresAtUtc": row["access_expires_at_utc"],
                "repoUrl": lab_access["repoUrl"],
                "catalogPath": lab_access["catalogPath"],
                "catalogLabel": lab_access["catalogLabel"],
                "instructions": lab_access["instructions"],
            }
        )

    @app.get("/api/my-bookings")
    def get_my_bookings() -> Any:
        session_id = get_or_create_session_id()
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT
                    booking_id, created_at_utc, name, email, lab, user_timezone, slot, goal,
                    access_token, access_expires_at_utc
                FROM bookings
                WHERE session_id = ?
                ORDER BY created_at_utc DESC
                """,
                (session_id,),
            ).fetchall()

        return jsonify({"sessionId": session_id, "bookings": [dict(row) for row in rows]})

    return app


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id TEXT NOT NULL UNIQUE,
                session_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                lab TEXT NOT NULL,
                user_timezone TEXT,
                slot TEXT NOT NULL,
                goal TEXT,
                source_page TEXT,
                user_agent TEXT,
                access_token TEXT,
                access_expires_at_utc TEXT
            )
            """
        )

        columns = {row[1] for row in conn.execute("PRAGMA table_info(bookings)").fetchall()}
        if "access_token" not in columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN access_token TEXT")
        if "access_expires_at_utc" not in columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN access_expires_at_utc TEXT")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_bookings_session_id ON bookings(session_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bookings_access_token ON bookings(access_token)")
        conn.commit()


def get_or_create_session_id() -> str:
    session_id = session.get("session_id")
    if session_id:
        return session_id
    session_id = uuid.uuid4().hex
    session["session_id"] = session_id
    return session_id


def validate_payload(payload: dict[str, Any]) -> str | None:
    required_fields = ["name", "email", "lab", "slot"]
    for field in required_fields:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"Missing required field: {field}"

    email = payload["email"].strip()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        return "Enter a valid email address"

    return None


def normalize_lab_key(lab_label: str) -> str:
    return " ".join((lab_label or "").strip().lower().split())


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def check_rate_limit(session_id: str) -> str | None:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=ACCESS_CHECK_WINDOW_SECONDS)

    with _ATTEMPTS_LOCK:
        attempts = _ACCESS_ATTEMPTS.setdefault(session_id, [])
        attempts[:] = [attempt for attempt in attempts if attempt >= cutoff]
        if len(attempts) >= ACCESS_CHECK_MAX_PER_WINDOW:
            return "Too many access checks. Please wait a minute and retry."
        attempts.append(now)

    return None


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5050"))
    app.run(host="0.0.0.0", port=port, debug=False)