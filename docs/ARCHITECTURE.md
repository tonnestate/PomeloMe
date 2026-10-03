# Architecture

## 1. Scientific hypothesis

PomeloMe tests the hypothesis that agentic work does not require continuous inference:

> Most execution transitions can be compiled into deterministic, bounded, statically analyzable
> operations; expensive inference is required only at explicit semantic decision boundaries.

The runtime therefore treats intelligence as a scarce scheduled resource rather than as the default
control loop.

## 2. Three different kinds of state

PomeloMe deliberately separates three state domains:

```text
organizational state     -> external system such as MangoMe
execution state          -> PomeloMe / durable workflow backend
workspace/process state  -> SandboxBackend such as OpenShell
```

No state domain is allowed to silently become canonical for another.

## 3. Execution flow

```text
Task / caller
    |
    v
Planner or prebuilt ExecutionPlan
    |
    v
PlanAdmitter
    | rejects: unbounded / unauthorized / over-budget plan
    v
Run Kernel
    |
    +--> deterministic nodes -------------------------+
    |                                                 |
    +--> REQUEST_JUDGMENT -> ModelRuntime             |
    |                                                 |
    +--> EFFECT -> concrete EffectIntent              |
                      |                                |
                      v                                |
                PolicyKernel                          |
                      |                                |
                      v                                |
                EffectGateway -> external world ------+
                      |
                      v
                probe / reconcile
                      |
                      v
                transactional outbox
                      |
                      v
                ReceiptProjector -> ReceiptSink
```

## 4. Static admission vs dynamic authorization

Static admission can prove structural facts about a bounded plan: possible tools, possible effect
classes, explicit judgment nodes, maximum parallel branches, and required capabilities.

It cannot generally prove the concrete runtime values of effect arguments produced by earlier reads.
Therefore PomeloMe performs a second authorization check on the materialized `EffectIntent`
immediately before dispatch.

## 5. Decision boundaries

In v0.1, a model call occurs only at an explicit `REQUEST_JUDGMENT` node. Deterministic operations do
not silently escalate to a model.

`ASSERT` failures currently suspend by raising `ReplanRequired`; automatic delta replanning is
intentionally deferred until its checkpoint semantics are specified and tested. This avoids hiding a
ReAct loop inside v0.1.

## 6. Durability

Production composition is intended to use DBOS workflows/steps/queues. PomeloMe does not copy DBOS.
The local SQLite store is intentionally limited to effect identity, state, and a transactional
receipt outbox so the core failure semantics can be tested offline.

## 7. Sandboxing

`OpenShellBackend` is an optional adapter. OpenShell handles physical isolation and low-level
network/filesystem/process controls. PomeloMe's `PolicyKernel` remains necessary because OS/resource
policy cannot decide whether a business-semantic action is authorized for a specific execution.

## 8. Why the IR is intentionally weaker than code execution

Programmatic tool-calling systems can execute richer code. PomeloMe's IR chooses less expressive
power to gain pre-execution analyzability. The runtime can reject a whole plan before spending model
calls or touching external systems.

The v0.1 IR has no loops, recursion, dynamic imports, eval, or arbitrary code nodes.
