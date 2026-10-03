from __future__ import annotations

from .ports import ReceiptSink
from .store import SqliteEffectStore


class ReceiptProjector:
    """Publishes low-frequency semantic receipts from the internal outbox."""

    def __init__(self, store: SqliteEffectStore, sink: ReceiptSink) -> None:
        self.store = store
        self.sink = sink

    def flush(self) -> int:
        published = 0
        for receipt in self.store.pending_receipts():
            receipt_id = receipt["receipt_id"]
            self.sink.publish(receipt)
            self.store.mark_published(receipt_id)
            published += 1
        return published
