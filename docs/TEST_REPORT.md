# v0.1 Test Report

Date: 2026-10-03

## Executed locally

```text
PYTHONPATH=src pytest -q
13 passed
```

The executed suite covers:

- Run and Effect FSM legality;
- static plan admission;
- irreversible-effect capability enforcement;
- globally unique IR node identities;
- hierarchical child-budget reservation;
- zero-model-call deterministic execution;
- receipt projection idempotency after ACK;
- core dependency boundary (no MangoMe / BlueberryMe imports);
- generated JSON Schema consistency;
- Release Gate 0: crash after irreversible dispatch, restart, probe, no duplicate dispatch;
- effect identity collision fail-closed behavior.

## Additional smoke check

`examples/demo_decision_sparse.py` executed successfully with one explicit model judgment and multiple
deterministic operations.

## Not executed in this environment

The optional `dbos` and `openshell` packages were not installed in the build environment. Their
adapters were checked against the current public APIs/documentation but were not integration-tested
against a live Postgres DBOS deployment or OpenShell gateway. They remain optional boundaries, not
part of the v0.1 Release Gate 0 proof.
