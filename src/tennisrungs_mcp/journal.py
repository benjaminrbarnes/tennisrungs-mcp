"""SQLite attempt ledger. Stored outside repository; no cookies or payloads."""
import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import SafetyError


class Journal:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.execute("CREATE TABLE IF NOT EXISTS operations (key TEXT PRIMARY KEY, fingerprint TEXT UNIQUE, kind TEXT, state TEXT, challenge_id INTEGER, updated_at TEXT)")
        self.db.commit()

    def close(self):
        self.db.close()

    def begin(self, key, kind, payload):
        if not key or len(key) > 128:
            raise SafetyError("A bounded nonempty operation key is required")
        obj = asdict(payload) if is_dataclass(payload) else payload
        if kind == "propose":
            # One intent per season team/start, even if a caller edits the note or venue.
            scope = ["proposal", {k: obj[k] for k in ["team_id", "match_date", "hour", "minute", "am_or_pm"]}]
        else:
            scope = ["challenge", obj.get("challenge_id")]
        fingerprint = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()
        try:
            self.db.execute("INSERT INTO operations VALUES (?,?,?,'ATTEMPTED',NULL,?)",
                            (key, fingerprint, kind, self.now()))
            self.db.commit()  # Durable BEFORE the irreversible request.
        except sqlite3.IntegrityError:
            raise SafetyError("Operation key or identical intent already journaled; inspect/reconcile, never retry blindly") from None

    def finish(self, key, state, challenge_id=None):
        self.db.execute("UPDATE operations SET state=?, challenge_id=?, updated_at=? WHERE key=?",
                        (state, challenge_id, self.now(), key))
        self.db.commit()

    def get(self, key):
        r = self.db.execute("SELECT key,kind,state,challenge_id,updated_at FROM operations WHERE key=?", (key,)).fetchone()
        return dict(zip(["key", "kind", "state", "challenge_id", "updated_at"], r)) if r else None

    @staticmethod
    def inspect_existing(path, key):
        """Read an existing ledger without creating, clearing or altering state."""
        try:
            db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
            try:
                r = db.execute("SELECT key,kind,state,challenge_id,updated_at FROM operations WHERE key=?", (key,)).fetchone()
                return dict(zip(["key", "kind", "state", "challenge_id", "updated_at"], r)) if r else None
            finally:
                db.close()
        except sqlite3.Error:
            raise SafetyError("Existing journal could not be read; no state was created or changed") from None

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()
