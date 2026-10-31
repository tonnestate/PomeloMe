"""Explicit, short-lived host acceptance probe for the EXISTING OpenShellBackend.

This is not a network/filesystem isolation certification or a Pomelo runtime
integration. It creates exactly one sandbox, executes two bounded shell
commands, and attempts deletion even after a failure. No configuration or
persistent logs are written by this module.
"""
from __future__ import annotations

import argparse
import json
import uuid

from .openshell_backend import OpenShellBackend


def probe_backend(backend: OpenShellBackend, *, run_id: str) -> dict[str, object]:
    sandbox_ref: str | None = None
    result: dict[str, object] = {
        "status": "INCONCLUSIVE",
        "sdk_lifecycle": False,
        "os_network_filesystem_isolation_verified": False,
        "business_effect_authority_verified": False,
        "cleanup": "NOT_STARTED",
    }
    try:
        sandbox_ref = backend.create(run_id)
        code, output, _stderr = backend.exec(
            sandbox_ref, ["/bin/sh", "-c", "printf POMELO_OPENSHELL_HOST_OK"]
        )
        if code != 0 or output != "POMELO_OPENSHELL_HOST_OK":
            result["reason"] = "POSITIVE_COMMAND_FAILED"
            return result
        code, _output, _stderr = backend.exec(
            sandbox_ref, ["/bin/sh", "-c", "exit 7"]
        )
        if code != 7:
            result["reason"] = "NEGATIVE_EXIT_NOT_PRESERVED"
            return result
        result["sdk_lifecycle"] = True
        result["status"] = "COMMAND_CHECKS_PASSED"
        return result
    except Exception:
        result["reason"] = "SDK_LIFECYCLE_ERROR"
        return result
    finally:
        try:
            if sandbox_ref is not None:
                backend.terminate(sandbox_ref)
                result["cleanup"] = "DELETED"
            else:
                result["cleanup"] = "NO_SANDBOX_REFERENCE"
        except Exception:
            result["cleanup"] = "FAILED_REQUIRES_OPERATOR_INSPECTION"
            result["status"] = "INCONCLUSIVE"
            result["sdk_lifecycle"] = False
        finally:
            try:
                backend.close()
            except Exception:
                result["cleanup"] = "CLIENT_CLOSE_FAILED_REQUIRES_OPERATOR_INSPECTION"
                result["status"] = "INCONCLUSIVE"
                result["sdk_lifecycle"] = False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit one-sandbox NVIDIA OpenShell host probe")
    parser.add_argument("--acknowledge-create-and-delete", action="store_true")
    parser.add_argument("--workspace", default="default")
    parser.add_argument("--endpoint", default=None, help="Optional loopback-only SDK gateway")
    args = parser.parse_args(argv)
    if not args.acknowledge_create_and_delete:
        parser.error("must explicitly acknowledge one sandbox creation and deletion")
    # The stable owner passes the workspace; never accept a model-authored endpoint.
    try:
        backend = OpenShellBackend(workspace=args.workspace, endpoint=args.endpoint)
    except Exception:
        print(json.dumps({"status": "INCONCLUSIVE", "reason": "BACKEND_UNAVAILABLE",
                          "sdk_lifecycle": False, "os_network_filesystem_isolation_verified": False}))
        return 2
    report = probe_backend(backend, run_id="host-probe-" + uuid.uuid4().hex)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "COMMAND_CHECKS_PASSED" and report["cleanup"] == "DELETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
