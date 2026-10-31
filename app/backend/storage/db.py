"""SQLite persistence: settings, glossaries, translation memory and history."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import threading
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS glossaries (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    src_lang TEXT NOT NULL,
    tgt_lang TEXT NOT NULL,
    bidirectional INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    glossary_id TEXT NOT NULL REFERENCES glossaries(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    case_sensitive INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    UNIQUE(glossary_id, source)
);

CREATE TABLE IF NOT EXISTS tm (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    src_lang TEXT NOT NULL,
    tgt_lang TEXT NOT NULL,
    profile TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    glossary_hash TEXT NOT NULL,
    source_key TEXT NOT NULL,
    target_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(src_lang, tgt_lang, profile, prompt_version, glossary_hash, source_key)
);

CREATE TABLE IF NOT EXISTS history (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'text',
    src_lang TEXT,
    detected_lang TEXT,
    tgt_lang TEXT,
    profile TEXT,
    device TEXT,
    source_text TEXT,
    result_text TEXT,
    status TEXT NOT NULL,
    duration_ms INTEGER,
    gen_tokens INTEGER,
    warnings_json TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_terms_glossary ON terms(glossary_id);
CREATE INDEX IF NOT EXISTS idx_tm_lookup
    ON tm(src_lang, tgt_lang, profile, prompt_version, glossary_hash, source_key);
CREATE INDEX IF NOT EXISTS idx_history_created ON history(created_at DESC);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._init_schema()

    # ------------------------------------------------------------------ schema
    def _init_schema(self) -> None:
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            self._conn.executescript(SCHEMA_V1)
            self._conn.execute("PRAGMA user_version = 1")
            self._conn.commit()

    def backup(self, target: str | Path) -> Path:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            dest = sqlite3.connect(str(target))
            try:
                self._conn.backup(dest)
            finally:
                dest.close()
        return target

    def integrity_check(self) -> str:
        with self._lock:
            return str(self._conn.execute("PRAGMA integrity_check").fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------------------------------------------------------------- settings
    def stored_settings(self) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM settings").fetchall()
        result: dict[str, Any] = {}
        for row in rows:
            try:
                result[row["key"]] = json.loads(row["value"])
            except json.JSONDecodeError:
                result[row["key"]] = row["value"]
        return result

    def set_settings(self, values: dict[str, Any]) -> None:
        with self._lock:
            self._conn.executemany(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                [(key, json.dumps(value, ensure_ascii=False)) for key, value in values.items()],
            )
            self._conn.commit()

    # --------------------------------------------------------------- glossaries
    def list_glossaries(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT g.*, (SELECT COUNT(*) FROM terms t WHERE t.glossary_id = g.id) AS term_count
                FROM glossaries g ORDER BY g.created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_glossary(self, glossary_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM glossaries WHERE id = ?", (glossary_id,)).fetchone()
        return dict(row) if row else None

    def create_glossary(self, name: str, src_lang: str, tgt_lang: str,
                        bidirectional: bool = False) -> dict[str, Any]:
        glossary_id = uuid.uuid4().hex[:16]
        created = utc_now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO glossaries(id, name, src_lang, tgt_lang, bidirectional, created_at) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (glossary_id, name.strip(), src_lang, tgt_lang, int(bidirectional), created),
            )
            self._conn.commit()
        return self.get_glossary(glossary_id) or {}

    def update_glossary(self, glossary_id: str, *, name: str | None = None,
                        bidirectional: bool | None = None) -> dict[str, Any] | None:
        fields: list[str] = []
        params: list[Any] = []
        if name is not None:
            fields.append("name = ?")
            params.append(name.strip())
        if bidirectional is not None:
            fields.append("bidirectional = ?")
            params.append(int(bidirectional))
        if fields:
            params.append(glossary_id)
            with self._lock:
                self._conn.execute(f"UPDATE glossaries SET {', '.join(fields)} WHERE id = ?", params)
                self._conn.commit()
        return self.get_glossary(glossary_id)

    def delete_glossary(self, glossary_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM glossaries WHERE id = ?", (glossary_id,))
            self._conn.commit()

    def list_terms(self, glossary_id: str, query: str = "") -> list[dict[str, Any]]:
        sql = "SELECT * FROM terms WHERE glossary_id = ?"
        params: list[Any] = [glossary_id]
        if query:
            sql += " AND (source LIKE ? OR target LIKE ? OR note LIKE ?)"
            like = f"%{query}%"
            params.extend([like, like, like])
        sql += " ORDER BY id DESC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def upsert_term(self, glossary_id: str, source: str, target: str,
                    case_sensitive: bool = False, note: str = "") -> dict[str, Any]:
        source = source.strip()
        target = target.strip()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO terms(glossary_id, source, target, case_sensitive, note)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(glossary_id, source) DO UPDATE SET
                    target=excluded.target, case_sensitive=excluded.case_sensitive, note=excluded.note
                """,
                (glossary_id, source, target, int(case_sensitive), note.strip()),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM terms WHERE glossary_id = ? AND source = ?", (glossary_id, source)
            ).fetchone()
        return dict(row) if row else {}

    def delete_term(self, glossary_id: str, term_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM terms WHERE id = ? AND glossary_id = ?",
                               (term_id, glossary_id))
            self._conn.commit()

    def update_term(self, glossary_id: str, term_id: int, *,
                    source: str | None = None, target: str | None = None,
                    case_sensitive: bool | None = None,
                    note: str | None = None) -> dict[str, Any] | None:
        fields: list[str] = []
        params: list[Any] = []
        if source is not None:
            fields.append("source = ?")
            params.append(source.strip())
        if target is not None:
            fields.append("target = ?")
            params.append(target.strip())
        if case_sensitive is not None:
            fields.append("case_sensitive = ?")
            params.append(int(case_sensitive))
        if note is not None:
            fields.append("note = ?")
            params.append(note.strip())
        if not fields:
            return self._get_term(glossary_id, term_id)
        params.extend([term_id, glossary_id])
        with self._lock:
            self._conn.execute(
                f"UPDATE terms SET {', '.join(fields)} WHERE id = ? AND glossary_id = ?",
                params,
            )
            self._conn.commit()
        return self._get_term(glossary_id, term_id)

    def _get_term(self, glossary_id: str, term_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM terms WHERE id = ? AND glossary_id = ?", (term_id, glossary_id)
            ).fetchone()
        return dict(row) if row else None

    def import_terms(self, glossary_id: str, csv_text: str,
                     replace: bool = False) -> dict[str, int]:
        rows = list(csv.reader(io.StringIO(csv_text.lstrip("\ufeff"))))
        added = updated = skipped = 0
        with self._lock:
            if replace:
                self._conn.execute("DELETE FROM terms WHERE glossary_id = ?", (glossary_id,))
            for row in rows:
                if not row or not any(cell.strip() for cell in row):
                    continue
                first = row[0].strip().lower()
                if first in {"source", "原文", "src"}:
                    continue
                if len(row) < 2 or not row[0].strip() or not row[1].strip():
                    skipped += 1
                    continue
                source, target = row[0].strip(), row[1].strip()
                case_sensitive = False
                note = ""
                if len(row) >= 3:
                    case_sensitive = row[2].strip().lower() in {"1", "true", "yes", "y", "是"}
                if len(row) >= 4:
                    note = row[3].strip()
                existing = self._conn.execute(
                    "SELECT id FROM terms WHERE glossary_id = ? AND source = ?",
                    (glossary_id, source),
                ).fetchone()
                self._conn.execute(
                    """
                    INSERT INTO terms(glossary_id, source, target, case_sensitive, note)
                    VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(glossary_id, source) DO UPDATE SET
                        target=excluded.target, case_sensitive=excluded.case_sensitive, note=excluded.note
                    """,
                    (glossary_id, source, target, int(case_sensitive), note),
                )
                if existing:
                    updated += 1
                else:
                    added += 1
            self._conn.commit()
        return {"added": added, "updated": updated, "skipped": skipped}

    def export_terms_csv(self, glossary_id: str) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["source", "target", "case_sensitive", "note"])
        for term in reversed(self.list_terms(glossary_id)):
            writer.writerow([term["source"], term["target"],
                             int(bool(term["case_sensitive"])), term["note"]])
        return "\ufeff" + buffer.getvalue()

    # ---------------------------------------------------------------- memory
    def get_tm(self, src_lang: str, tgt_lang: str, profile: str, prompt_version: str,
               glossary_hash: str, source_key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM tm WHERE src_lang=? AND tgt_lang=? AND profile=?
                  AND prompt_version=? AND glossary_hash=? AND source_key=?
                """,
                (src_lang, tgt_lang, profile, prompt_version, glossary_hash, source_key),
            ).fetchone()
            if row:
                self._conn.execute("UPDATE tm SET hit_count = hit_count + 1 WHERE id = ?", (row["id"],))
                self._conn.commit()
        return dict(row) if row else None

    def put_tm(self, src_lang: str, tgt_lang: str, profile: str, prompt_version: str,
               glossary_hash: str, source_key: str, target_text: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO tm(src_lang, tgt_lang, profile, prompt_version, glossary_hash,
                               source_key, target_text, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(src_lang, tgt_lang, profile, prompt_version, glossary_hash, source_key)
                DO UPDATE SET target_text=excluded.target_text, created_at=excluded.created_at
                """,
                (src_lang, tgt_lang, profile, prompt_version, glossary_hash,
                 source_key, target_text, utc_now()),
            )
            self._conn.commit()

    def clear_tm(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM tm")
            self._conn.commit()

    def tm_stats(self) -> dict[str, int]:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) FROM tm").fetchone()[0]
            hits = self._conn.execute("SELECT COALESCE(SUM(hit_count), 0) FROM tm").fetchone()[0]
        return {"entries": int(total), "hits": int(hits)}

    # --------------------------------------------------------------- history
    def add_history(
        self,
        *,
        kind: str,
        src_lang: str | None,
        detected_lang: str | None,
        tgt_lang: str,
        profile: str,
        device: str,
        source_text: str,
        result_text: str,
        status: str,
        duration_ms: int,
        gen_tokens: int = 0,
        warnings: Iterable[str] = (),
        error: str | None = None,
    ) -> str:
        history_id = uuid.uuid4().hex[:16]
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO history(id, created_at, kind, src_lang, detected_lang, tgt_lang,
                                    profile, device, source_text, result_text, status,
                                    duration_ms, gen_tokens, warnings_json, error)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (history_id, utc_now(), kind, src_lang, detected_lang, tgt_lang, profile,
                 device, source_text, result_text, status, duration_ms, gen_tokens,
                 json.dumps(list(warnings), ensure_ascii=False), error),
            )
            self._conn.commit()
        return history_id

    def update_history(self, history_id: str, **fields: Any) -> None:
        allowed = {"result_text", "status", "duration_ms", "gen_tokens", "warnings_json", "error"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with self._lock:
            self._conn.execute(f"UPDATE history SET {assignments} WHERE id = ?",
                               [*updates.values(), history_id])
            self._conn.commit()

    def list_history(self, query: str = "", limit: int = 20,
                     offset: int = 0) -> dict[str, Any]:
        where = ""
        params: list[Any] = []
        if query:
            where = "WHERE source_text LIKE ? OR result_text LIKE ?"
            like = f"%{query}%"
            params.extend([like, like])
        with self._lock:
            total = self._conn.execute(f"SELECT COUNT(*) FROM history {where}", params).fetchone()[0]
            rows = self._conn.execute(
                f"""
                SELECT id, created_at, kind, src_lang, detected_lang, tgt_lang, profile,
                       device, status, duration_ms, gen_tokens, warnings_json,
                       substr(source_text, 1, 200) AS excerpt
                FROM history {where}
                ORDER BY created_at DESC LIMIT ? OFFSET ?
                """,
                [*params, max(1, min(limit, 100)), max(0, offset)],
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["warning_count"] = len(json.loads(item.pop("warnings_json") or "[]"))
            except json.JSONDecodeError:
                item["warning_count"] = 0
            items.append(item)
        return {"total": int(total), "items": items}

    def get_history(self, history_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM history WHERE id = ?", (history_id,)).fetchone()
        return dict(row) if row else None

    def delete_history(self, history_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM history WHERE id = ?", (history_id,))
            self._conn.commit()

    def clear_history(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM history")
            self._conn.commit()
