from __future__ import annotations

from typing import Any, Callable, TypeVar

T = TypeVar("T")


def dbos_step(fn: Callable[..., T]) -> Callable[..., T]:
    """Mark a nondeterministic boundary as a DBOS durable step when DBOS is installed.

    Keeping this adapter tiny is intentional: PomeloMe does not reimplement durable execution.
    Production applications can compose the core runtime inside their own DBOS workflows.
    """

    try:
        from dbos import DBOS
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("install pomelome[durable] to use DBOS") from exc
    return DBOS.step()(fn)  # type: ignore[no-any-return]


def dbos_workflow(fn: Callable[..., T]) -> Callable[..., T]:
    try:
        from dbos import DBOS
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("install pomelome[durable] to use DBOS") from exc
    return DBOS.workflow()(fn)  # type: ignore[no-any-return]
