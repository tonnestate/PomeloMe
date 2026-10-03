# PomeloMe v0.1 Core Contract

This document is normative for v0.1.

## Invariants

1. **Decision sparsity** — deterministic transitions MUST NOT invoke a model.
2. **Plan admission** — every ExecutionPlan MUST be statically admitted before execution.
3. **Concrete effect authorization** — every external effect MUST be dynamically authorized again
   immediately before dispatch. Plan admission never substitutes for this check.
4. **Intent before effect** — an effect identity and `DISPATCHED` state MUST be durably recorded
   before the runtime crosses the external side-effect boundary.
5. **No blind replay** — an effect left in an uncertain post-dispatch state MUST NOT be blindly
   redispatched. The runtime MUST probe, reconcile, or suspend for approval.
6. **Run state is not effect state** — `LOST` belongs to the Run FSM. `UNKNOWN` belongs to the Effect FSM.
7. **Hierarchical budgets** — child execution capacity MUST come from the parent budget; fan-out
   MUST NOT multiply aggregate authority or cost limits.
8. **Bounded IR** — v0.1 IR MUST remain non-Turing-complete and statically inspectable. No unbounded
   loops, recursion, eval, dynamic code loading, or arbitrary embedded programs are allowed.
9. **Core independence** — the core MUST NOT import MangoMe or BlueberryMe.
10. **Receipts are not organizational truth** — PomeloMe emits low-frequency execution receipts.
    A downstream system decides what those receipts mean organizationally.

## Product boundary

PomeloMe owns:

- execution admission;
- execution state machines;
- deterministic scheduling;
- effect identity and reconciliation;
- runtime budgets;
- semantic authorization hooks;
- model decision boundaries;
- receipt projection.

PomeloMe does not own:

- organizational truth, assurance, or verification policy;
- confidential-data tokenization/materialization semantics;
- OS/kernel isolation implementation;
- a durable workflow engine implementation;
- arbitrary model-provider SDK behavior.

## Compatibility ports

The stable conceptual ports for v0.1 are:

- `AuthorityProvider`
- `ReceiptSink`
- `ReferenceResolver`
- `ToolRuntime`
- `ModelRuntime`
- `SandboxBackend`

Adapters MAY bind these ports to MangoMe, BlueberryMe, DBOS, OpenShell, MCP, or other systems.
Those products are not part of the PomeloMe core model.
