"""Focused KOTZE adapter contract tests; no privileged execution or model calls."""
from pathlib import Path
import sqlite3
import subprocess

import pytest

from pomelome import AuthorityEnvelope, EffectClass, EffectGateway
from pomelome.effects import EffectIntent
from pomelome.errors import SimulatedCrash
from pomelome.fsm import EffectState
from pomelome.kotze import KOTZE_TOOL, KotzeBinding, KotzeRepairAdapter
from pomelome.store import SqliteEffectStore


def harness(tmp_path, runner):
    db = tmp_path / "kotze.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE works(id TEXT, state TEXT, verification_state TEXT, candidate_sha TEXT)")
        conn.execute("CREATE TABLE events(work_id TEXT, name TEXT, actor INTEGER, candidate_sha TEXT,"
                     " evidence_ref TEXT, resulting_revision INTEGER)")
        conn.execute("INSERT INTO works VALUES('k-work', 'REPAIRING', 'UNKNOWN', '')")
    config = tmp_path / "host-config.json"
    config.write_text("{}")
    pipeline = tmp_path / "repair_pipeline.py"
    pipeline.write_text("not executed by test")
    binding = KotzeBinding(session_id="session-1", work_ref="fruit:work-1",
                           work_id="k-work", config_path=config, db_path=db)
    adapter = KotzeRepairAdapter({"fruit:work-1": binding}, pipeline, runner=runner)
    intent = EffectIntent(
        run_id="session-1", effect_id="effect-1", tool=KOTZE_TOOL,
        effect_class=EffectClass.IRREVERSIBLE,
        args={"work_ref": "fruit:work-1"},
        required_capabilities=frozenset({"kotze.repair"}),
    )
    auth = AuthorityEnvelope(
        authority_id="mango:authority-1", principal="peachme",
        capabilities=frozenset({"tool:kotze.repair", "effect:irreversible", "kotze.repair"}),
    )
    store = SqliteEffectStore(tmp_path / "effects.sqlite")
    return db, adapter, intent, auth, store


def verify(db, *, actor=3, match=True):
    candidate = "a" * 64
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE works SET state='COMPLETED', verification_state='PASS',"
                     " candidate_sha=? WHERE id='k-work'", (candidate,))
        conn.execute("INSERT INTO events VALUES(?,?,?,?,?,?)",
                     ("k-work", "VERIFY_PASS", actor, candidate if match else "b" * 64,
                      "sha256:host-verifier-receipt", 4))


def test_authorized_dispatch_uses_pinned_pipeline_and_independent_proof(tmp_path):
    calls = []
    db = tmp_path / "kotze.sqlite"

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        verify(db)
        return subprocess.CompletedProcess(argv, 0, stdout="model says pass")

    _, adapter, intent, auth, store = harness(tmp_path, runner)
    result = EffectGateway(store, {KOTZE_TOOL: adapter}).execute(intent, auth)
    assert result.state is EffectState.RECONCILED
    assert result.observation.success is True
    assert result.observation.data["verifier_evidence_ref"] == "sha256:host-verifier-receipt"
    assert len(calls) == 1
    assert calls[0][0][1:3] == ["-I", "-B"]
    assert calls[0][0][-2:] == ["--config", str(adapter.registrations["fruit:work-1"].config_path)]
    assert store.get_effect("effect-1")["dispatch_count"] == 1
    repeated = EffectGateway(store, {KOTZE_TOOL: adapter}).execute(intent, auth)
    assert not repeated.dispatched and repeated.observation.success is True
    assert len(calls) == 1


def test_missing_or_forged_verifier_event_never_counts_as_success(tmp_path):
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"status":"PASS"}')

    db, adapter, intent, auth, store = harness(tmp_path, runner)
    verify(db, actor=2)
    result = EffectGateway(store, {KOTZE_TOOL: adapter}).execute(intent, auth)
    assert result.state is EffectState.UNKNOWN and result.observation.success is None
    assert EffectGateway(store, {KOTZE_TOOL: adapter}).recover(intent).state is EffectState.WAITING_APPROVAL
    assert len(calls) == 1


def test_recover_after_crash_probes_without_second_dispatch(tmp_path):
    db = tmp_path / "kotze.sqlite"
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        verify(db)
        return subprocess.CompletedProcess(argv, 0)

    _, adapter, intent, auth, store = harness(tmp_path, runner)
    with pytest.raises(SimulatedCrash):
        EffectGateway(store, {KOTZE_TOOL: adapter}).execute(
            intent, auth, crash_after_dispatch=True,
        )
    assert store.get_effect("effect-1")["state"] == EffectState.DISPATCHED
    observation = EffectGateway(store, {KOTZE_TOOL: adapter}).recover(intent)
    assert observation.state is EffectState.RECONCILED
    assert observation.observation.success is True
    assert observation.dispatched is False
    assert len(calls) == 1


def test_unknown_timeout_does_not_retry(tmp_path):
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        raise subprocess.TimeoutExpired(argv, 1)

    db, adapter, intent, auth, store = harness(tmp_path, runner)
    result = EffectGateway(store, {KOTZE_TOOL: adapter}).execute(intent, auth)
    assert result.state is EffectState.UNKNOWN
    assert result.observation.success is None
    waiting = EffectGateway(store, {KOTZE_TOOL: adapter}).recover(intent)
    assert waiting.state is EffectState.WAITING_APPROVAL
    assert len(calls) == 1


def test_work_scope_and_arguments_are_not_model_controlled(tmp_path):
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    db, adapter, intent, auth, store = harness(tmp_path, runner)
    with pytest.raises(ValueError, match="NOT_HOST_REGISTERED"):
        adapter.dispatch(intent.model_copy(update={"run_id": "another-session"}))
    with pytest.raises(ValueError, match="CONTRACT_INVALID"):
        adapter.dispatch(intent.model_copy(update={"args": {"work_ref": "fruit:work-1",
                                                             "command": "rm -rf /"}}))
    assert calls == []


def test_missing_capability_denied_before_kotze_execution(tmp_path):
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    _, adapter, intent, auth, store = harness(tmp_path, runner)
    revoked = auth.model_copy(update={"capabilities": frozenset()})
    with pytest.raises(Exception, match="missing capabilities"):
        EffectGateway(store, {KOTZE_TOOL: adapter}).execute(intent, revoked)
    assert calls == []
