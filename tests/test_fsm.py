import pytest

from pomelome.errors import InvalidTransition
from pomelome.fsm import EffectState, RunState, transition_effect, transition_run


def test_run_fsm_accepts_normal_path() -> None:
    state = RunState.CREATED
    for target in [RunState.AUTHORIZED, RunState.QUEUED, RunState.RUNNING, RunState.COMPLETED]:
        state = transition_run(state, target)
    assert state is RunState.COMPLETED


def test_run_fsm_rejects_completed_to_running() -> None:
    with pytest.raises(InvalidTransition):
        transition_run(RunState.COMPLETED, RunState.RUNNING)


def test_effect_fsm_keeps_unknown_separate_from_run_state() -> None:
    assert EffectState.UNKNOWN.value == "UNKNOWN"
    assert "UNKNOWN" not in {state.value for state in RunState}
    assert transition_effect(EffectState.DISPATCHED, EffectState.UNKNOWN) is EffectState.UNKNOWN
