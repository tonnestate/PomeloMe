# Release Gate 0 — Irreversible Crash Recovery

## Purpose

Prove the most important v0.1 safety property before adding multi-agent or provider breadth.

## Scenario

1. Create an `IRREVERSIBLE` `EffectIntent` with valid authority.
2. Persist the intent.
3. Persist `AUTHORIZED`.
4. Persist `DISPATCHED`.
5. Dispatch to the external system.
6. Kill the runtime before the returned observation is committed.
7. Restart PomeloMe with the same durable effect ledger.
8. Recover the effect by probe.
9. Confirm that the external dispatch count remains exactly one.
10. Confirm that exactly one semantic `EFFECT_OBSERVATION` receipt exists.

## Required outcome

```text
external dispatches = 1
final effect state   = RECONCILED
semantic receipts    = 1
```

A second dispatch is an unconditional gate failure.

## Implemented test

`tests/test_release_gate_0.py`

The test uses a fresh `EffectGateway` instance after the fault to model process restart. The external
system keeps its own state and supports `probe(effect_id)`. The durable local ledger intentionally
remains in `DISPATCHED` across the crash window.

## Next fault-injection matrix

Future releases should extend this with fixed kill points:

```text
T0 before authorization
T1 after authorization, before dispatch
T2 after dispatch, before response
T3 after response, before durable observation commit
T4 after durable observation commit, before receipt projection
T5 after sink delivery, before outbox ACK
```

These points must be defined before evaluation tasks are run.
