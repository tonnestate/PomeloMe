<p align="center">
  <img src="docs/assets/pomelome-banner.png" alt="PomeloMe" width="100%">
</p>

# PomeloMe v0.1.0

**Decision-sparse execution runtime for governed, durable agentic work.**

PomeloMe is deliberately not another multi-agent framework. Its core hypothesis is that most
execution transitions do not require inference. PomeloMe therefore spends model intelligence only
at explicit semantic decision boundaries and executes everything else as bounded, analyzable,
deterministic runtime work.

> **Model proposes. PomeloMe admits, executes and reconciles. MangoMe may establish meaning.**
>
> **PomeloMe spends intelligence only where determinism ends.**

MangoMe and BlueberryMe are integrations, not dependencies. The PomeloMe core imports neither.

## Proposed zero-cost media gate (feature branch only)

This branch contains an **opt-in, host-injected** ZeroCostGuard at plan admission,
READ and EFFECT dispatch; generic REQUEST_JUDGMENT model calls are prohibited.
Only explicitly audited LOCAL tool names may run. Unknown/free-tier/cloud
routes, billed credentials and automatic paid fallbacks are denied.

**Not accepted or deployed production truth.** The calling host must inject the
same guard into the runtime and EffectGateway and require
BudgetEnvelope(max_cost_usd=0). A zero budget without a guard is not safe.
See docs/ZERO_COST_MEDIA.md for the threat model, tests and host requirements.

## v0.1 proof target

The first release proves one thing before it attempts orchestration breadth:

> If an irreversible external effect is dispatched and the PomeloMe process dies before the
> outcome is durably recorded, recovery must not dispatch the effect a second time. PomeloMe probes
> or suspends for approval and emits exactly one semantic effect receipt.

`tests/test_release_gate_0.py` is the executable acceptance gate for that invariant.

## What v0.1 contains

- A **non-Turing-complete ExecutionIR** represented by JSON Schema and Pydantic models.
- **Static plan admission** before execution.
- **Dynamic authorization** for every concrete external effect before dispatch.
- Separate **Run FSM** and **Effect FSM**.
- Hierarchical execution budgets.
- A small deny-by-default semantic `PolicyKernel`.
- Decision-sparse runtime execution: deterministic nodes do not call a model.
- `REQUEST_JUDGMENT` as the explicit model boundary.
- `PARALLEL_BOUNDED` with explicit branch limits.
- Stable effect identities, effect classes, probe/reconciliation, and a transactional receipt outbox.
- Optional adapter boundaries for DBOS and NVIDIA OpenShell.
- Generic ports for authority, receipts, references, tools, models, and sandboxes.

## What v0.1 intentionally does not contain

- No LangGraph, CrewAI, AutoGen/Microsoft Agent Framework, or OpenAI Agents adapter.
- No swarm/supervisor abstraction.
- No learned model router.
- No Cedar/OPA dependency in the semantic core.
- No generic programming language inside the IR.
- No claim that MCP is a security boundary.
- No direct write path into MangoMe.
- No direct dependency on BlueberryMe handles.
- No replacement for DBOS durable workflows or OpenShell physical isolation.

## Architecture

```text
Caller / Planner
      |
      v
ExecutionPlan (JSON / Structured Output)
      |
      v
Static Plan Admission
      |
      v
PomeloMe Run Kernel
  |       |        |
  |       |        +--> REQUEST_JUDGMENT --> ModelRuntime
  |       |
  |       +--> deterministic IR operators
  |
  +--> EffectIntent
          |
          v
   Dynamic Effect Authorization
          |
          v
      Effect Gateway
          |
      Sandbox / MCP / API
          |
          v
   Observation / Probe
          |
          v
   Receipt Projection
          |
     optional sinks
   (MangoMe / other)
```

Two authorization phases are mandatory:

1. **Plan admission:** inspect the entire bounded plan before execution and reject structurally
   unauthorized capabilities, irreversible effects, excessive model calls, or excessive parallelism.
2. **Effect authorization:** immediately before dispatch, validate the concrete target, arguments,
   current authority, and remaining budget. Static admission never replaces runtime authorization.

## ExecutionIR v0.1

The IR is intentionally small:

- `READ`
- `EFFECT`
- `SELECT`
- `FILTER`
- `ASSERT`
- `IF_TYPED`
- `PARALLEL_BOUNDED`
- `REQUEST_JUDGMENT`
- `RETURN`

The canonical JSON Schema is generated from the runtime model at
`schemas/execution_ir.schema.json` and is regression-tested.

## Effect classes

```text
READ             repeatable read path; represented as READ, not EFFECT
IDEMPOTENT_WRITE retry only with stable idempotency semantics
COMPENSATABLE    recovery requires an explicit compensation/probe policy
IRREVERSIBLE     never blindly redispatch after an uncertain outcome
```

A crash after `DISPATCHED` leaves a durable ambiguity. On restart PomeloMe probes the external
system. If a reliable probe is unavailable, the effect moves to `WAITING_APPROVAL`; it is not
silently retried.

## DBOS and OpenShell

PomeloMe does not reimplement a durable workflow engine or a sandbox security platform.

- **DBOS** is the intended durable-workflow backend for production composition. The optional
  `pomelome[durable]` extra targets DBOS 3.x. The core exposes narrow wrappers rather than owning
  DBOS semantics.
- **NVIDIA OpenShell** is an optional `SandboxBackend`. OpenShell supplies physical isolation and
  egress/filesystem/process enforcement. PomeloMe still owns semantic action authorization.

The local SQLite ledger in `store.py` exists only to make the effect protocol and Release Gate 0
runnable without external infrastructure. It is not a workflow engine.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
python examples/demo_decision_sparse.py
```

Optional backends:

```bash
pip install -e ".[durable]"   # DBOS 3.x
pip install -e ".[sandbox]"   # NVIDIA OpenShell SDK
```

## Current acceptance status

The repository is considered v0.1-ready only when all tests pass, especially:

```text
IRREVERSIBLE effect
  -> AUTHORIZED
  -> DISPATCHED
  -> simulated hard crash
  -> restart
  -> probe
  -> no second dispatch
  -> exactly one durable semantic receipt
```

See `docs/CORE_CONTRACT.md`, `docs/ARCHITECTURE.md`, `docs/EVAL.md`, and
`docs/RELEASE_GATE_0.md`.

---

## AI Transparency

This repository contains material created with or materially assisted by generative AI systems. This may include source code, documentation, examples, tests, specifications, project artwork, and other visual assets.

AI-generated or AI-assisted material should not be treated as independently verified solely because it appears in this repository. Visual assets may include AI-generated imagery used for illustrative or branding purposes unless explicitly stated otherwise.

This repository-level disclosure is provided for transparency, including with regard to applicable transparency requirements under the EU AI Act. It does not imply that every file or contribution was generated by AI, nor that every item is subject to a specific statutory labeling obligation.
