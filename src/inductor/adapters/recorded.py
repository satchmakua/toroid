"""Recorded LLM outputs — the standing pattern for the LLM paths: run the real
model once with a key, commit the structured result as a fixture, and replay it in
CI with no key. `RecordedLLM` implements the same `synthesize` / `classify_cex`
surface as `ClaudeAdapter`, so the whole synth/refine pipeline runs offline against
real captured Claude output.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inductor.adapters.llm import CexCause, CexDiagnosis
from inductor.domain.interface import ModuleInterface
from inductor.domain.properties import Property, PropertySet
from inductor.domain.trace import Trace
from inductor.loaders import load_property_set, property_from_dict, property_to_dict


def diagnosis_to_dict(d: CexDiagnosis) -> dict[str, Any]:
    return {
        "cause": d.cause.value,
        "narration": d.narration,
        "patch": property_to_dict(d.proposed_patch) if d.proposed_patch else None,
    }


def diagnosis_from_dict(data: dict[str, Any]) -> CexDiagnosis:
    patch = property_from_dict(data["patch"]) if data.get("patch") else None
    return CexDiagnosis(
        cause=CexCause(data["cause"]), narration=data["narration"], proposed_patch=patch
    )


@dataclass(slots=True)
class RecordedLLM:
    """Replays a recorded synthesis and a sequence of recorded diagnoses."""

    synth: PropertySet
    diagnoses: list[CexDiagnosis]
    _idx: int = 0

    @classmethod
    def from_files(cls, synth_path: Path, classify_path: Path | None = None) -> RecordedLLM:
        synth = load_property_set(synth_path)
        diagnoses: list[CexDiagnosis] = []
        if classify_path is not None:
            # Fail loud on a provided-but-missing fixture: a typo'd path must not
            # silently degrade to an empty, no-op replay (which would surface far
            # away, if at all). read_text raises FileNotFoundError — matching
            # load_property_set's fail-loud contract on the synth side.
            raw = json.loads(classify_path.read_text(encoding="utf-8"))
            diagnoses = [diagnosis_from_dict(d) for d in raw.get("diagnoses", [])]
        return cls(synth=synth, diagnoses=diagnoses)

    def synthesize(
        self, interface: ModuleInterface, spec: str, *, feedback: str | None = None
    ) -> PropertySet:
        # The recorded set already passed the compile gate live, so no repair is
        # needed on replay (feedback is ignored).
        return self.synth

    def classify_cex(
        self, prop: Property, trace: Trace, interface: ModuleInterface
    ) -> CexDiagnosis:
        if not self.diagnoses:
            raise RuntimeError("no recorded diagnoses to replay")
        d = self.diagnoses[min(self._idx, len(self.diagnoses) - 1)]
        self._idx += 1
        return d


def write_classify_fixture(path: Path, diagnoses: Sequence[CexDiagnosis]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"diagnoses": [diagnosis_to_dict(d) for d in diagnoses]}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
