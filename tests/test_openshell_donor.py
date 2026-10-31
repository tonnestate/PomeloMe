from __future__ import annotations

import hashlib
import sys
from types import SimpleNamespace

import pytest

from pomelome.adapters.openshell_backend import OpenShellBackend


class FakeClient:
    def __init__(self, endpoint=None):
        self.endpoint = endpoint
        self.calls = []
        self.fail_ready = False

    @classmethod
    def from_active_cluster(cls):
        return cls(endpoint="ACTIVE_CLUSTER")

    def __enter__(self):
        self.calls.append("enter")
        return self

    def __exit__(self, *args):
        self.calls.append("exit")

    def create(self, *, workspace, name):
        self.calls.append(("create", workspace, name))
        return SimpleNamespace(name=name)

    def wait_ready(self, name, *, workspace, timeout_seconds):
        self.calls.append(("wait_ready", name, workspace, timeout_seconds))
        if self.fail_ready:
            raise TimeoutError("not ready")

    def exec(self, sandbox_ref, command, *, workspace):
        self.calls.append(("exec", sandbox_ref, command, workspace))
        return SimpleNamespace(exit_code=7, stdout="out", stderr="err")

    def delete(self, sandbox_ref, *, workspace, allow_missing):
        self.calls.append(("delete", sandbox_ref, workspace, allow_missing))
        return SimpleNamespace(sandbox_id="sandbox-123")

    def wait_deleted(self, sandbox_ref, *, workspace, expected_sandbox_id):
        self.calls.append(("wait_deleted", sandbox_ref, workspace, expected_sandbox_id))


def test_upstream_sdk_calls_and_sanitized_resource_name(monkeypatch):
    monkeypatch.setitem(sys.modules, "openshell", SimpleNamespace(SandboxClient=FakeClient))
    backend = OpenShellBackend(workspace="trusted")
    name = backend.create("../unsafe/USER:task")
    expected = "pomelome-" + hashlib.sha256("../unsafe/USER:task".encode()).hexdigest()[:24]
    assert name == expected
    assert backend.exec(name, ["python", "-V"]) == (7, "out", "err")
    backend.terminate(name)
    assert ("wait_deleted", name, "trusted", "sandbox-123") in backend._client.calls
    backend.close()
    assert backend._client.calls[-1] == "exit"


@pytest.mark.parametrize("endpoint", [
    "gateway.example.org:50051", "evil:50051", "http://127.0.0.1:50051",
    "localhost:0", "localhost:90000", "localhost:12/../", "foo@localhost:50051",
])
def test_plaintext_remote_endpoints_rejected_before_client_creation(endpoint):
    with pytest.raises(ValueError):
        OpenShellBackend(endpoint=endpoint)


def test_active_cluster_or_explicit_loopback(monkeypatch):
    monkeypatch.setitem(sys.modules, "openshell", SimpleNamespace(SandboxClient=FakeClient))
    for endpoint in ("127.0.0.1:50051", "localhost:50051", "[::1]:50051"):
        backend = OpenShellBackend(endpoint=endpoint)
        assert backend._client.endpoint == endpoint


def test_not_ready_cleans_up_and_never_returns_a_reference(monkeypatch):
    class NotReadyClient(FakeClient):
        def __init__(self, endpoint=None):
            super().__init__(endpoint)
            self.fail_ready = True
    monkeypatch.setitem(sys.modules, "openshell", SimpleNamespace(SandboxClient=NotReadyClient))
    backend = OpenShellBackend()
    with pytest.raises(TimeoutError):
        backend.create("run")
    assert any(c[0] == "delete" for c in backend._client.calls if isinstance(c, tuple))


def test_invalid_exec_command_does_not_cross_boundary(monkeypatch):
    monkeypatch.setitem(sys.modules, "openshell", SimpleNamespace(SandboxClient=FakeClient))
    backend = OpenShellBackend()
    with pytest.raises(ValueError):
        backend.exec("sb1", [])
    with pytest.raises(ValueError):
        backend.exec("", ["true"])
    assert not any(c[0] == "exec" for c in backend._client.calls if isinstance(c, tuple))


def test_unowned_sandbox_never_executes_or_deletes(monkeypatch):
    monkeypatch.setitem(sys.modules, "openshell", SimpleNamespace(SandboxClient=FakeClient))
    backend = OpenShellBackend(workspace="trusted")
    name = backend.create("owned")
    for operation in (
        lambda: backend.exec("another-peers-sandbox", ["true"]),
        lambda: backend.terminate("another-peers-sandbox"),
    ):
        with pytest.raises(PermissionError):
            operation()
    assert all(
        not (event[0] in {"exec", "delete"} and event[1] == "another-peers-sandbox")
        for event in backend._client.calls if isinstance(event, tuple)
    )
    assert name in backend._owned_sandboxes
    backend.terminate(name)
    assert name not in backend._owned_sandboxes


def test_deletion_timeout_does_not_forget_sandbox(monkeypatch):
    class DeleteFails(FakeClient):
        def wait_deleted(self, sandbox_ref, *, workspace, expected_sandbox_id):
            self.calls.append(("wait_deleted", sandbox_ref, workspace, expected_sandbox_id))
            raise TimeoutError("sandbox may still exist")

    monkeypatch.setitem(sys.modules, "openshell", SimpleNamespace(SandboxClient=DeleteFails))
    backend = OpenShellBackend()
    name = backend.create("run")
    with pytest.raises(TimeoutError):
        backend.terminate(name)
    assert name in backend._owned_sandboxes
