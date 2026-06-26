"""SQLite store — durable persistence for bookings, record-change audit, and
agent traces. Stdlib sqlite3 only (no external dependency).

Every write the agent or staff makes is persisted here so history survives
restarts and forms an audit trail — the durability half of HIPAA-aligned design.
PHI is masked (via obs.logging) before trace payloads are stored.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from config.settings import get_settings
from hcasst.obs.logging import mask_obj

_SCHEMA = """
CREATE TABLE IF NOT EXISTS appointments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id    TEXT NOT NULL,
    patient_name  TEXT,
    specialty     TEXT,
    provider      TEXT,
    start         TEXT,
    "end"         TEXT,
    status        TEXT NOT NULL DEFAULT 'proposed',
    reason        TEXT,
    created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS record_audit (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id    TEXT NOT NULL,
    action        TEXT NOT NULL,
    evidence_id   TEXT,
    kind          TEXT,
    content       TEXT,
    author        TEXT,
    created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS traces (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    step        TEXT NOT NULL,
    name        TEXT,
    status      TEXT,
    payload     TEXT,
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS memory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id  TEXT NOT NULL,
    kind        TEXT NOT NULL,
    content     TEXT NOT NULL,
    scope       TEXT NOT NULL DEFAULT 'patient',
    status      TEXT NOT NULL DEFAULT 'active',
    importance  REAL NOT NULL DEFAULT 0.5,
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    module      TEXT NOT NULL,
    metric      TEXT NOT NULL,
    value       REAL,
    detail      TEXT,
    created_at  REAL NOT NULL
);


"""


class Store:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or get_settings().db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _insert(self, table: str, **cols: Any) -> int:
        cols.setdefault("created_at", time.time())
        keys = ", ".join(f'"{k}"' for k in cols)
        marks = ", ".join("?" for _ in cols)
        cur = self._conn.execute(
            f"INSERT INTO {table} ({keys}) VALUES ({marks})", tuple(cols.values())
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def _rows(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in self._conn.execute(sql, tuple(params)).fetchall()]

    # ── appointments ─────────────────────────────────────────────────────
    def add_appointment(self, **cols: Any) -> int:
        return self._insert("appointments", **cols)

    def update_appointment_status(self, appt_id: int, status: str) -> None:
        self._conn.execute(
            "UPDATE appointments SET status = ? WHERE id = ?", (status, appt_id)
        )
        self._conn.commit()

    def appointments(self, patient_id: str | None = None) -> list[dict[str, Any]]:
        if patient_id:
            return self._rows(
                "SELECT * FROM appointments WHERE patient_id = ? ORDER BY created_at DESC",
                (patient_id,),
            )
        return self._rows("SELECT * FROM appointments ORDER BY created_at DESC")

    def get_appointment(self, appt_id: int) -> dict[str, Any] | None:
        rows = self._rows("SELECT * FROM appointments WHERE id = ?", (appt_id,))
        return rows[0] if rows else None

    # ── record audit ─────────────────────────────────────────────────────
    def add_record_audit(self, patient_id: str, action: str, evidence_id: str,
                         kind: str, content: str, author: str) -> int:
        return self._insert(
            "record_audit", patient_id=patient_id, action=action,
            evidence_id=evidence_id, kind=str(kind), content=content, author=author,
        )

    def record_audit(self, patient_id: str | None = None) -> list[dict[str, Any]]:
        if patient_id:
            return self._rows(
                "SELECT * FROM record_audit WHERE patient_id = ? ORDER BY created_at DESC",
                (patient_id,),
            )
        return self._rows("SELECT * FROM record_audit ORDER BY created_at DESC")

    # ── memory ───────────────────────────────────────────────────────────
    def add_memory(self, patient_id: str, kind: str, content: str,
                   scope: str = "patient", importance: float = 0.5) -> int:
        return self._insert("memory", patient_id=patient_id, kind=kind,
                            content=content, scope=scope, status="active",
                            importance=importance)

    def memories(self, patient_id: str, scope: str | None = None,
                 status: str | None = "active") -> list[dict[str, Any]]:
        sql = "SELECT * FROM memory WHERE patient_id = ?"
        params: list[Any] = [patient_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        if scope is not None:
            sql += " AND scope = ?"
            params.append(scope)
        sql += " ORDER BY created_at DESC"
        return self._rows(sql, params)


    # ── traces (PHI-masked) ──────────────────────────────────────────────
    def add_trace(self, session_id: str, step: str, name: str, status: str, payload: Any) -> int:
        return self._insert(
            "traces", session_id=session_id, step=step, name=name, status=status,
            payload=json.dumps(mask_obj(payload), default=str),
        )

    def traces(self, session_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        if session_id:
            return self._rows(
                "SELECT * FROM traces WHERE session_id = ? ORDER BY id ASC LIMIT ?",
                (session_id, limit),
            )
        return self._rows("SELECT * FROM traces ORDER BY id DESC LIMIT ?", (limit,))


    def add_eval(self, run_id: str, module: str, metric: str, value: float, detail: Any = None) -> int:
        return self._insert("eval_runs", run_id=run_id, module=module, metric=metric,
                            value=value, detail=json.dumps(detail, default=str) if detail is not None else None)

    def eval_runs(self, run_id: str | None = None) -> list[dict[str, Any]]:
        if run_id:
            return self._rows("SELECT * FROM eval_runs WHERE run_id = ? ORDER BY id", (run_id,))
        return self._rows("SELECT * FROM eval_runs ORDER BY id DESC")

    def latest_run_id(self) -> str | None:
        r = self._rows("SELECT run_id FROM eval_runs ORDER BY id DESC LIMIT 1")
        return r[0]["run_id"] if r else None
    
    def close(self) -> None:
        self._conn.close()

