from pathlib import Path

from pomelome.adapters.local import MemoryReceiptSink
from pomelome.receipts import ReceiptProjector
from pomelome.store import SqliteEffectStore


def test_receipt_projector_is_idempotent_after_ack(tmp_path: Path) -> None:
    store = SqliteEffectStore(tmp_path / "db.sqlite")
    store.put_intent("r", "e", "tool", "READ", {"effect_id": "e"})
    store.commit_observation_and_receipt(
        "e", "KNOWN_SUCCESS", {"success": True}, "receipt:e", {"kind": "EFFECT_OBSERVATION"}
    )
    sink = MemoryReceiptSink()
    projector = ReceiptProjector(store, sink)
    assert projector.flush() == 1
    assert projector.flush() == 0
    assert len(sink.receipts) == 1
    assert sink.receipts[0]["receipt_id"] == "receipt:e"
