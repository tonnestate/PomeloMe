# NVIDIA OpenShell donor — existing PomeloMe adapter

Donor: [NVIDIA/OpenShell](https://github.com/NVIDIA/OpenShell), Apache-2.0.

PomeloMe already had `src/pomelome/adapters/openshell_backend.py` and an optional `openshell` package extra. This change hardens that actual SDK boundary rather than creating a second sandbox runtime. `SandboxBackend` remains the same create/exec/terminate interface. PomeloMe's PolicyKernel, effect admission, ledgers and reconciliation remain the semantic authority.

## Correct execution boundary

- `SandboxClient.from_active_cluster()` is preferred; upstream handles that authenticated gateway profile. No second OpenShell daemon is started by PomeloMe.
- An explicit `endpoint` uses the upstream SDK's plaintext connection; only a loopback host and a specified valid port are permitted. Remote clusters must use the SDK active-cluster authentication profile, not an unverified plaintext endpoint.
- Names derive deterministically from a SHA256 digest of the run ID instead of passing arbitrary worker text to OpenShell.
- Invalid command lists are rejected before calling the SDK. Failed readiness triggers best-effort deletion; cleanup failure does not mask the primary failure.
- No claim that a sandbox's default spec denies all egress. Host operators must configure, inspect and independently test the upstream OpenShell filesystem/network/process policy; this adapter does not grant semantic effects.

## Operability and versions

The PomeloMe core is Python >=3.11. Current upstream OpenShell Python SDK requires Python >=3.12. Install the optional `pomelome[sandbox]` integration only in an isolated compatible host environment and confirm actual SDK version, cluster authentication and allowed execution resources. Do **not** reinstall FruitStack packages or expose a gateway on a public listener solely for this donor.

Unit tests use a fake upstream SDK: `tests/test_openshell_donor.py`. They verify API calls and fail-closed rejection but are not an OS isolation penetration test or production acceptance. A supervised host-level isolation, egress and recovery test is still needed before claiming a secure sandbox.
