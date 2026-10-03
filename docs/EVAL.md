# Evaluation Design

PomeloMe should be evaluated against strong baselines, not only a naive ReAct loop.

## Arms

| Arm | Runtime |
| --- | --- |
| A | Direct/ReAct tool loop with eager tools and one strong model |
| B | PomeloMe ExecutionIR + one model at explicit judgment nodes |
| C | B + step-level model routing + bounded parallel judgment |
| D | Provider programmatic tool calling using the same model and tools |

Arm C is not part of v0.1 implementation; it is reserved for the first adaptive-cognitive-scheduling
experiment after the core correctness gates pass.

## Public task benchmarks

Use at least one API-heavy benchmark and one policy-sensitive tool benchmark. AppWorld and τ-bench
are suitable candidates because they exercise API state changes and policy constraints. Public
benchmarks are not sufficient for crash semantics, so PomeloMe also needs a predeclared fault-
injection suite.

## Primary metrics

- verified task success;
- total cost per successful task;
- model calls per successful task;
- input tokens per semantic decision;
- frontier-model tokens per task;
- tool-schema tokens per task;
- agent-to-agent tokens per task;
- P50/P95 latency;
- duplicate irreversible effects;
- authority bypasses;
- correct UNKNOWN/probe/reconciliation behavior;
- duplicate semantic receipts.

## Initial, provisional gates

These are hypotheses to validate, not product claims:

```text
quality >= 95% of best arm
model calls <= 50% of direct/ReAct baseline
input tokens <= 40% of direct/ReAct baseline
frontier-model tokens <= 30% of direct/ReAct baseline
0 duplicate irreversible effects
0 authority bypasses
```

Thresholds should be frozen only after a baseline run establishes variance and statistical power.
