"""Host-only KOTZE repair effect adapter for the existing PomeloMe EffectGateway.

PeachMe supplies a stable effect intent. PomeloMe alone handles dispatch identity,
authority and recovery. The only executable is a trusted, pinned KOTZE pipeline.
Never accept file paths, commands, credentials or verifier claims from an agent.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from typing import Callable, Mapping
from urllib.parse import quote

from .effects import EffectIntent, EffectObservation
from .models import EffectClass

KOTZE_TOOL = "kotze.repair"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$", re.ASCII)


@dataclass(frozen=True)
class KotzeBinding:
    """Trusted-host registration, never constructed from model arguments."""

    session_id: str
    work_ref: str
    work_id: str
    config_path: Path
    db_path: Path

    def __post_init__(self) -> None:
        for field in ("session_id", "work_ref", "work_id"):
            if not isinstance(getattr(self, field), str) or not _ID.fullmatch(getattr(self, field)):
                raise ValueError("INVALID_KOTZE_BINDING_ID")
        for field in ("config_path", "db_path"):
            path = getattr(self, field)
            if not isinstance(path, Path) or not path.is_absolute() or path.is_symlink():
                raise ValueError("KOTZE_HOST_PATH_MUST_BE_PINNED")


class KotzeRepairAdapter:
    """Concrete effect adapter, installed only in a trusted PomeloMe host.

    The host chooses every config and work mapping. Dispatch executes once via
    PomeloMe's durable effect claim. Probe is read-only and never starts KOTZE.
    A process exit code or model claim is NOT a verification receipt.
    """

    def __init__(
        self,
        registrations: Mapping[str, KotzeBinding],
        pipeline: Path,
        *,
        python: Path | None = None,
        timeout_seconds: int = 1800,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        if not isinstance(pipeline, Path) or not pipeline.is_absolute() or pipeline.is_symlink():
            raise ValueError("KOTZE_PIPELINE_MUST_BE_PINNED")
        executable = python or Path(sys.executable)
        if not executable.is_absolute() or executable.is_symlink():
            raise ValueError("KOTZE_PYTHON_MUST_BE_PINNED")
        if type(timeout_seconds) is not int or not 30 <= timeout_seconds <= 3600:
            raise ValueError("KOTZE_TIMEOUT_OUT_OF_RANGE")
        self.registrations = dict(registrations)
        if not all(isinstance(ref, str) and isinstance(b, KotzeBinding) and ref == b.work_ref
                   for ref, b in self.registrations.items()):
            raise ValueError("KOTZE_REGISTRATION_MISMATCH")
        self.pipeline = pipeline
        self.python = executable
        self.timeout_seconds = timeout_seconds
        self._runner = runner

    def _binding(self, intent: EffectIntent) -> KotzeBinding:
        if (intent.tool != KOTZE_TOOL or intent.effect_class != EffectClass.IRREVERSIBLE
                or type(intent.args) is not dict or set(intent.args) != {"work_ref"}
                or type(intent.args.get("work_ref")) is not str
                or "kotze.repair" not in intent.required_capabilities):
            raise ValueError("KOTZE_EFFECT_CONTRACT_INVALID")
        binding = self.registrations.get(intent.args["work_ref"])
        if binding is None or binding.session_id != intent.run_id:
            raise ValueError("KOTZE_WORK_NOT_HOST_REGISTERED")
        return binding

    def probe(self, intent: EffectIntent) -> EffectObservation | None:
        """Observe only host-persisted C11 proof, never rerun or complete work."""
        binding = self._binding(intent)
        db = binding.db_path
        if db.is_symlink() or not db.is_file():
            return None
        uri = "file:" + quote(str(db), safe="/") + "?mode=ro"
        try:
            with sqlite3.connect(uri, uri=True, timeout=5) as conn:
                conn.execute("PRAGMA query_only=ON")
                work = conn.execute(
                    "SELECT state, verification_state, candidate_sha FROM works WHERE id=?",
                    (binding.work_id,),
                ).fetchone()
                if work is None:
                    return None
                state, verification, candidate = work
                if state == "COMPLETED" and verification == "PASS" and candidate:
                    proof = conn.execute(
                        "SELECT evidence_ref FROM events WHERE work_id=? AND name='VERIFY_PASS'"
                        " AND actor=3 AND candidate_sha=? ORDER BY resulting_revision DESC LIMIT 1",
                        (binding.work_id, candidate),
                    ).fetchone()
                    if proof and isinstance(proof[0], str) and proof[0]:
                        return EffectObservation(
                            success=True,
                            external_ref=f"kotze:{binding.work_id}:{candidate}",
                            data={"work_id": binding.work_id, "candidate_sha": candidate,
                                  "verifier_evidence_ref": proof[0]},
                        )
                if verification == "FAIL" and state == "DIAGNOSING":
                    return EffectObservation(success=False, message="KOTZE_VERIFIER_REJECTED")
        except (sqlite3.Error, OSError):
            return None
        return None

    def dispatch(self, intent: EffectIntent) -> EffectObservation:
        """Run the pinned pipeline after PomeloMe has claimed dispatch durably."""
        binding = self._binding(intent)
        command = [
            str(self.python), "-I", "-B", str(self.pipeline),
            "--config", str(binding.config_path),
        ]
        try:
            finished = self._runner(
                command, check=False, capture_output=True, text=True,
                timeout=self.timeout_seconds, cwd="/",
                env={"PATH": "/usr/bin:/bin", "LANG": "C"},
            )
        except (OSError, subprocess.TimeoutExpired):
            return self.probe(intent) or EffectObservation(
                success=None, message="KOTZE_EXECUTION_OUTCOME_UNKNOWN"
            )
        # Exit status is never proof: only the independently accepted C11
        # VERIFY_PASS event bound to the sealed candidate establishes success.
        observed = self.probe(intent)
        if observed is not None:
            return observed
        return EffectObservation(
            success=None,
            message=("KOTZE_UNVERIFIED_AFTER_EXIT_" + str(finished.returncode))[:100],
        )
