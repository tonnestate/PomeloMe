from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .fsm import EffectState


class SqliteEffectStore:
    """Small local effect ledger + transactional outbox.

    This is NOT a workflow engine and does not replace DBOS. It exists so the semantic
    effect protocol can be tested without external infrastructure.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _init(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS effects (
                    effect_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    effect_class TEXT NOT NULL,
                    state TEXT NOT NULL,
                    intent_json TEXT NOT NULL,
                    observation_json TEXT,
                    dispatch_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS outbox (
                    receipt_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    published INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def get_effect(self, effect_id: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM effects WHERE effect_id = ?", (effect_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["intent"] = json.loads(result.pop("intent_json"))
        obs = result.pop("observation_json")
        result["observation"] = json.loads(obs) if obs else None
        return result

    def put_intent(self, run_id: str, effect_id: str, tool: str, effect_class: str, intent: dict[str, Any]) -> None:
        intent_json = json.dumps(intent, sort_keys=True)
        with self.transaction() as con:
            con.execute(
                """
                INSERT OR IGNORE INTO effects(effect_id, run_id, tool, effect_class, state, intent_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (effect_id, run_id, tool, effect_class, EffectState.INTENDED, intent_json),
            )
            row = con.execute(
                "SELECT run_id, tool, effect_class, intent_json FROM effects WHERE effect_id = ?",
                (effect_id,),
            ).fetchone()
            assert row is not None
            if (
                row["run_id"] != run_id
                or row["tool"] != tool
                or row["effect_class"] != effect_class
                or row["intent_json"] != intent_json
            ):
                raise ValueError(f"effect identity collision for {effect_id}")

    def set_state(self, effect_id: str, state: EffectState, *, increment_dispatch: bool = False) -> None:
        with self.transaction() as con:
            if increment_dispatch:
                con.execute(
                    "UPDATE effects SET state = ?, dispatch_count = dispatch_count + 1 WHERE effect_id = ?",
                    (state, effect_id),
                )
            else:
                con.execute("UPDATE effects SET state = ? WHERE effect_id = ?", (state, effect_id))

    def commit_observation_and_receipt(
        self,
        effect_id: str,
        state: EffectState,
        observation: dict[str, Any],
        receipt_id: str,
        receipt: dict[str, Any],
    ) -> None:
        with self.transaction() as con:
            con.execute(
                "UPDATE effects SET state = ?, observation_json = ? WHERE effect_id = ?",
                (state, json.dumps(observation, sort_keys=True), effect_id),
            )
            con.execute(
                "INSERT OR IGNORE INTO outbox(receipt_id, payload_json) VALUES (?, ?)",
                (receipt_id, json.dumps(receipt, sort_keys=True)),
            )

    def reconcile(self, effect_id: str) -> None:
        self.set_state(effect_id, EffectState.RECONCILED)

    def pending_receipts(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT receipt_id, payload_json FROM outbox WHERE published = 0 ORDER BY receipt_id"
            ).fetchall()
        return [{"receipt_id": row["receipt_id"], **json.loads(row["payload_json"])} for row in rows]

    def mark_published(self, receipt_id: str) -> None:
        with self.transaction() as con:
            con.execute("UPDATE outbox SET published = 1 WHERE receipt_id = ?", (receipt_id,))

    def count_receipts(self) -> int:
        with self._connect() as con:
            row = con.execute("SELECT COUNT(*) AS n FROM outbox").fetchone()
            assert row is not None
            return int(row["n"])
