from __future__ import annotations


class OpenShellBackend:
    """Thin adapter to NVIDIA OpenShell's Python SDK.

    OpenShell is a physical isolation backend, not PomeloMe's semantic policy engine.
    Import is intentionally lazy so the PomeloMe core remains dependency-free.
    """

    def __init__(self, workspace: str = "default", endpoint: str | None = None) -> None:
        try:
            from openshell import SandboxClient
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("install pomelome[sandbox] to use OpenShellBackend") from exc
        self.workspace = workspace
        self._client = (
            SandboxClient(endpoint) if endpoint else SandboxClient.from_active_cluster()
        )
        self._client.__enter__()

    def create(self, run_id: str) -> str:
        sandbox = self._client.create(workspace=self.workspace, name=f"pomelome-{run_id}")
        self._client.wait_ready(sandbox.name, workspace=self.workspace, timeout_seconds=120)
        return sandbox.name

    def exec(self, sandbox_ref: str, command: list[str]) -> tuple[int, str, str]:
        result = self._client.exec(sandbox_ref, command, workspace=self.workspace)
        return int(result.exit_code), result.stdout, result.stderr

    def terminate(self, sandbox_ref: str) -> None:
        deletion = self._client.delete(sandbox_ref, workspace=self.workspace, allow_missing=True)
        self._client.wait_deleted(
            sandbox_ref,
            workspace=self.workspace,
            expected_sandbox_id=deletion.sandbox_id,
        )

    def close(self) -> None:
        self._client.__exit__(None, None, None)
