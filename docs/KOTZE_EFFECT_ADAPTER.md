# KOTZE Coding-Repair Effect Adapter

`pomelome.kotze.KotzeRepairAdapter` exposes the existing KOTZE 4.2 repair pipeline as a single PomeloMe effect. It is **not** a second control plane, task scheduler, autonomous model, or verifier.

## Ownership and execution contract

- **MangoMe:** owns the authorized FruitStack work identity and issues current host authority.
- **PeachMe:** owns the session and uses its existing `PomeloEffectBridge`. That bridge requires an independently approved, matching one-effect plan.
- **PomeloMe:** owns the effect identity, static/dynamic admission, exactly-one dispatch claim and observation-only recovery.
- **KOTZE:** owns C11 repair state, native action reservations, isolated worker, private oracle, authenticated verifier, and its own host-written evidence. Only KOTZE verifies the patch.

The only admitted effect shape is:

```json
{
  "tool": "kotze.repair",
  "effect_class": "IRREVERSIBLE",
  "args": {"work_ref": "<existing-mangome-work-ref>"},
  "required_capabilities": ["kotze.repair"]
}
```

The host-created `KotzeBinding` maps that work ref and one PeachMe session ID to the registered KOTZE work ID, its already-private pipeline config and canonical C11 SQLite database. Tool inputs never include an executable path, repository path, oracle, credentials or verification claim.

The host must install:
- `EffectGateway(store, {"kotze.repair": KotzeRepairAdapter(...)})` in its **trusted, appropriately privileged execution process**. No `sudo` fallback or shell interpolation exists.
- A persistent PomeloMe `SqliteEffectStore` shared across restarts, with its own host-controlled directory.
- An existing, private KOTZE pipeline configuration with `schema="kotze.repair-pipeline.v1"`, `work_id` and `db` equal to the host binding. KOTZE itself checks all required paths, UID ownership, host-side isolation, pinned manifest and verifier service.
- Current MangoMe `AuthorityEnvelope` including `tool:kotze.repair`, `effect:irreversible` and `kotze.repair`.
- A separately approved PeachMe/PomeloMe single-`EffectNode` plan with the same stable effect ID, tool, class, arguments and capabilities. **Do not generate or approve this plan from a model's live request.**

## Invocation

```python
# In trusted PeachMe host code, after the registration, authority,
# approved plan and persistent Pomelo effect gateway have been installed:
handoff = bridge.repair_with_kotze(
    session_id, work_ref=canonical_mango_work_ref, effect_key=stable_repair_attempt_key,
)
```

Use a stable `effect_key` on retries. A deliberately new repair attempt requires a new accepted plan and effect identity. PeachMe uses its existing `effect_identity(session_id,effect_key)` and `PomeloEffectBridge.execute` path; it does not call KOTZE directly.

## What "success" means

The adapter's read-only `probe` checks the KOTZE C11 database for:
1. Exactly the registered `work_id`.
2. `works.state == COMPLETED` and `verification_state == PASS`.
3. An independently written `VERIFY_PASS` event with actor `KOTZE_VERIFIER (3)`, the same sealed candidate SHA and nonempty evidence reference.

Process exit 0, a passing public test, model text or a worker-written receipt do **not** satisfy these conditions. The adapter returns a reference to verified evidence but never exposes private oracle values.

If process execution times out or crashes, the adapter probes. If proof is missing, it returns `success=None` and PomeloMe keeps an UNKNOWN outcome; subsequent recovery **only probes**, never runs KOTZE again. An inconclusive recovery requires PomeloMe's existing host-authorized `WAITING_APPROVAL` resolution.

## Current evidence

- New adapter source and focused tests cover permission denial, scope mismatch, forged verifier, completed proof, timeout and simulated crash recovery.
- KOTZE's prior isolated scripted acceptance is independent evidence for KOTZE itself; it does **not** demonstrate a deployed FruitStack bridge.
- **Not yet verified:** live connection on the user's trusted host, MangoMe authority binding, actual privileged isolation service, full cross-repo regression suite or model-driven repair rate.
- No Kaggle evaluation is started by this integration. The competition submission remains a separate declarative artifact.
