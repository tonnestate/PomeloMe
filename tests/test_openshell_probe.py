from __future__ import annotations

import pytest

from pomelome.adapters.openshell_backend import OpenShellBackend
from pomelome.adapters.openshell_probe import probe_backend, main


class FakeBackend:
    def __init__(self, *, positive_code=0, negative_code=7, create_fails=False,
                 delete_fails=False, close_fails=False):
        self.positive_code = positive_code
        self.negative_code = negative_code
        self.create_fails = create_fails
        self.delete_fails = delete_fails
        self.close_fails = close_fails
        self.events = []

    def create(self, run_id):
        self.events.append(("create", run_id))
        if self.create_fails:
            raise RuntimeError("create failed secret")
        return "sandbox-1"

    def exec(self, sandbox_ref, command):
        self.events.append(("exec", sandbox_ref, tuple(command)))
        if "printf" in command[-1]:
            return self.positive_code, "POMELO_OPENSHELL_HOST_OK", ""
        return self.negative_code, "", ""

    def terminate(self, sandbox_ref):
        self.events.append(("delete", sandbox_ref))
        if self.delete_fails:
            raise RuntimeError("delete failed secret")

    def close(self):
        self.events.append(("close",))
        if self.close_fails:
            raise RuntimeError("close failed secret")


def test_two_command_host_probe_and_cleanup():
    backend = FakeBackend()
    receipt = probe_backend(backend, run_id="user-host-1")
    assert receipt["status"] == "COMMAND_CHECKS_PASSED"
    assert receipt["sdk_lifecycle"] is True
    assert receipt["cleanup"] == "DELETED"
    assert receipt["os_network_filesystem_isolation_verified"] is False
    assert receipt["business_effect_authority_verified"] is False
    assert backend.events[0] == ("create", "user-host-1")
    assert len([x for x in backend.events if x[0] == "exec"]) == 2
    assert backend.events[-2:] == [("delete", "sandbox-1"), ("close",)]


@pytest.mark.parametrize("positive,negative", [(1, 7), (0, 0)])
def test_incorrect_positive_or_negative_command_never_passes(positive, negative):
    backend = FakeBackend(positive_code=positive, negative_code=negative)
    receipt = probe_backend(backend, run_id="run")
    assert receipt["status"] == "INCONCLUSIVE"
    assert receipt["cleanup"] == "DELETED"


def test_failure_to_create_or_delete_is_not_a_pass():
    backend = FakeBackend(create_fails=True)
    receipt = probe_backend(backend, run_id="run")
    assert receipt["status"] == "INCONCLUSIVE"
    assert receipt["cleanup"] == "NO_SANDBOX_REFERENCE"
    assert backend.events[-1] == ("close",)

    backend = FakeBackend(delete_fails=True)
    receipt = probe_backend(backend, run_id="run")
    assert receipt["status"] == "INCONCLUSIVE"
    assert receipt["sdk_lifecycle"] is False
    assert receipt["cleanup"] == "FAILED_REQUIRES_OPERATOR_INSPECTION"


def test_client_close_failure_never_passes():
    backend = FakeBackend(close_fails=True)
    receipt = probe_backend(backend, run_id="run")
    assert receipt["status"] == "INCONCLUSIVE"
    assert receipt["cleanup"] == "CLIENT_CLOSE_FAILED_REQUIRES_OPERATOR_INSPECTION"


def test_without_explicit_acknowledgement_no_sandbox_can_be_created(capsys):
    with pytest.raises(SystemExit):
        main([])
    stderr = capsys.readouterr().err
    assert "acknowledge" in stderr
