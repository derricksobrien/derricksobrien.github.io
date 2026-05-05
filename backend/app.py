from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, session
from flask_cors import CORS


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bookings.db"


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
        now_utc = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO bookings (
                    booking_id, session_id, created_at_utc,
                    name, email, lab, user_timezone, slot, goal, source_page, user_agent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    booking_id,
                    session_id,
                    now_utc,
                    payload["name"].strip(),
                    payload["email"].strip().lower(),
                    payload["lab"].strip(),
                    payload.get("timezone", "").strip(),
                    payload["slot"].strip(),
                    payload.get("goal", "").strip(),
                    payload.get("sourcePage", "").strip(),
                    request.headers.get("User-Agent", "")[:255],
                ),
            )
            conn.commit()

        return jsonify({"status": "stored", "bookingId": booking_id, "sessionId": session_id}), 201

    @app.get("/api/my-bookings")
    def get_my_bookings() -> Any:
        session_id = get_or_create_session_id()
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT booking_id, created_at_utc, name, email, lab, user_timezone, slot, goal
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
                user_agent TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bookings_session_id ON bookings(session_id)")
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


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5050"))
    app.run(host="0.0.0.0", port=port, debug=False)