from __future__ import annotations

"""NVIDIA OpenShell adapter: physical sandboxing, not semantic authorization.

Donor: https://github.com/NVIDIA/OpenShell (Apache-2.0).
Use the installed upstream SDK; no forked container or security runtime.
"""

import hashlib
from urllib.parse import urlsplit


def _loopback_endpoint(endpoint: str) -> bool:
    """Explicit endpoints are plaintext in this adapter: allow local only.

    Remote clusters must use the authenticated active-cluster SDK profile.
    """
    if not endpoint or "://" in endpoint or "/" in endpoint or "@" in endpoint:
        return False
    try:
        parsed = urlsplit("//" + endpoint)
        return parsed.hostname in {"localhost", "127.0.0.1", "::1"} and (
            parsed.port is not None and 0 < parsed.port <= 65535
        )
    except ValueError:
        return False


class OpenShellBackend:
    """Thin host-selected adapter to NVIDIA OpenShell's Python SDK.

    Caller supplies the trusted workspace/cluster configuration, never an
    agent instruction. OpenShell protects the OS boundary. PomeloMe still
    authorizes business effects through its PolicyKernel.
    """

    def __init__(self, workspace: str = "default", endpoint: str | None = None) -> None:
        if not workspace or not workspace.strip() or len(workspace) > 128:
            raise ValueError("workspace must be a non-empty host-selected name")
        if endpoint is not None and not _loopback_endpoint(endpoint):
            raise ValueError("remote or malformed plaintext OpenShell endpoint is forbidden")
        try:
            from openshell import SandboxClient
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("install pomelome[sandbox] to use OpenShellBackend") from exc
        self.workspace = workspace
        # The adapter must not operate on arbitrary peer sandboxes sharing a workspace.
        self._owned_sandboxes: set[str] = set()
        self._client = (
            SandboxClient(endpoint) if endpoint else SandboxClient.from_active_cluster()
        )
        self._client.__enter__()

    def create(self, run_id: str) -> str:
        if not isinstance(run_id, str) or not run_id or len(run_id) > 512:
            raise ValueError("run_id must be a bounded non-empty string")
        # OpenShell sandbox names have strict character constraints; never
        # inject raw task/work identities into the resource name.
        stable_name = "pomelome-" + hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:24]
        sandbox = self._client.create(workspace=self.workspace, name=stable_name)
        if not sandbox.name:
            raise RuntimeError("OpenShell returned an empty sandbox name")
        self._owned_sandboxes.add(sandbox.name)
        try:
            self._client.wait_ready(sandbox.name, workspace=self.workspace, timeout_seconds=120)
        except Exception:
            # Best effort cleanup, but preserve the original readiness failure.
            try:
                self.terminate(sandbox.name)
            except Exception:
                pass
            raise
        return sandbox.name

    def exec(self, sandbox_ref: str, command: list[str]) -> tuple[int, str, str]:
        if not sandbox_ref or not command or not all(isinstance(x, str) and x for x in command):
            raise ValueError("sandbox_ref and nonempty argv are required")
        if sandbox_ref not in self._owned_sandboxes:
            raise PermissionError("sandbox was not created by this adapter instance")
        result = self._client.exec(sandbox_ref, command, workspace=self.workspace)
        return int(result.exit_code), result.stdout, result.stderr

    def terminate(self, sandbox_ref: str) -> None:
        if not sandbox_ref:
            raise ValueError("sandbox_ref is required")
        if sandbox_ref not in self._owned_sandboxes:
            raise PermissionError("sandbox was not created by this adapter instance")
        deletion = self._client.delete(sandbox_ref, workspace=self.workspace, allow_missing=True)
        self._client.wait_deleted(
            sandbox_ref,
            workspace=self.workspace,
            expected_sandbox_id=deletion.sandbox_id,
        )
        self._owned_sandboxes.remove(sandbox_ref)

    def close(self) -> None:
        self._client.__exit__(None, None, None)
