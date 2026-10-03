from __future__ import annotations

from enum import StrEnum

from .errors import InvalidTransition


class RunState(StrEnum):
    CREATED = "CREATED"
    AUTHORIZED = "AUTHORIZED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_CHILD = "WAITING_CHILD"
    SUSPENDED = "SUSPENDED"
    RECOVERING = "RECOVERING"
    LOST = "LOST"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class EffectState(StrEnum):
    INTENDED = "INTENDED"
    AUTHORIZED = "AUTHORIZED"
    DISPATCHED = "DISPATCHED"
    KNOWN_SUCCESS = "KNOWN_SUCCESS"
    KNOWN_FAILURE = "KNOWN_FAILURE"
    UNKNOWN = "UNKNOWN"
    PROBING = "PROBING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RECONCILED = "RECONCILED"


_RUN_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.CREATED: frozenset({RunState.AUTHORIZED, RunState.CANCELLED, RunState.FAILED}),
    RunState.AUTHORIZED: frozenset({RunState.QUEUED, RunState.CANCELLED, RunState.FAILED}),
    RunState.QUEUED: frozenset({RunState.RUNNING, RunState.CANCELLED, RunState.LOST}),
    RunState.RUNNING: frozenset(
        {
            RunState.WAITING_APPROVAL,
            RunState.WAITING_CHILD,
            RunState.SUSPENDED,
            RunState.RECOVERING,
            RunState.LOST,
            RunState.COMPLETED,
            RunState.FAILED,
            RunState.CANCELLED,
        }
    ),
    RunState.WAITING_APPROVAL: frozenset(
        {RunState.RUNNING, RunState.SUSPENDED, RunState.CANCELLED, RunState.FAILED}
    ),
    RunState.WAITING_CHILD: frozenset(
        {RunState.RUNNING, RunState.SUSPENDED, RunState.CANCELLED, RunState.FAILED}
    ),
    RunState.SUSPENDED: frozenset(
        {RunState.RUNNING, RunState.RECOVERING, RunState.CANCELLED, RunState.FAILED}
    ),
    RunState.RECOVERING: frozenset(
        {RunState.RUNNING, RunState.WAITING_APPROVAL, RunState.SUSPENDED, RunState.FAILED}
    ),
    RunState.LOST: frozenset({RunState.RECOVERING, RunState.CANCELLED, RunState.FAILED}),
    RunState.COMPLETED: frozenset(),
    RunState.FAILED: frozenset(),
    RunState.CANCELLED: frozenset(),
}

_EFFECT_TRANSITIONS: dict[EffectState, frozenset[EffectState]] = {
    EffectState.INTENDED: frozenset({EffectState.AUTHORIZED, EffectState.KNOWN_FAILURE}),
    EffectState.AUTHORIZED: frozenset({EffectState.DISPATCHED, EffectState.KNOWN_FAILURE}),
    EffectState.DISPATCHED: frozenset(
        {EffectState.KNOWN_SUCCESS, EffectState.KNOWN_FAILURE, EffectState.UNKNOWN, EffectState.PROBING}
    ),
    EffectState.UNKNOWN: frozenset({EffectState.PROBING, EffectState.WAITING_APPROVAL}),
    EffectState.PROBING: frozenset(
        {EffectState.KNOWN_SUCCESS, EffectState.KNOWN_FAILURE, EffectState.WAITING_APPROVAL}
    ),
    EffectState.KNOWN_SUCCESS: frozenset({EffectState.RECONCILED}),
    EffectState.KNOWN_FAILURE: frozenset({EffectState.RECONCILED}),
    EffectState.WAITING_APPROVAL: frozenset(
        {EffectState.PROBING, EffectState.KNOWN_FAILURE, EffectState.RECONCILED}
    ),
    EffectState.RECONCILED: frozenset(),
}


def transition_run(current: RunState, target: RunState) -> RunState:
    if target not in _RUN_TRANSITIONS[current]:
        raise InvalidTransition(f"run transition {current} -> {target} is not allowed")
    return target


def transition_effect(current: EffectState, target: EffectState) -> EffectState:
    if target not in _EFFECT_TRANSITIONS[current]:
        raise InvalidTransition(f"effect transition {current} -> {target} is not allowed")
    return target
