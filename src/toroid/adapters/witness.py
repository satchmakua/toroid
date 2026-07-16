"""Witness parsing for the SymbiYosys backend (VCD → `Trace`). See DESIGN.md §6.4.

The structured `Trace` type lives in `domain/trace.py`. The two backends reach it by
different routes:

* **yosys-sat** parses Yosys's `sat` model table (`yosys_sat.parse_sat_model`).
* **sby** writes a VCD counterexample per engine run; `parse_vcd` below turns it into
  the same `Trace`, so a FALSIFIED verdict discharged via sby gets the same inline
  cycle-by-cycle narration as the lightweight backend.

Format notes, pinned to real SymbiYosys/`yosys-smtbmc` output (OSS CAD Suite 20260714 —
see `tests/fixtures/fifo_f1.trace.vcd`, captured from a live run):

    $var integer 32 t smt_step $end     <- the solver step index, carried explicitly
    $var event 1 ! smt_clock $end
    $scope module fifo_fv $end          <- the formal wrapper is the top scope
    $var wire 3 n1 count $end           <- interface ports live at depth 1
    $scope module dut $end
    $var wire 3 n8 count $end           <- the DUT's own copy, depth 2 (NOT what we want)

Two details make this robust: `smt_step` means we never have to guess a timestamp →
step mapping (smtbmc emits sub-steps for the clock edges), and resolving each name to
its **shallowest** scope picks the wrapper's port rather than a same-named internal.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from toroid.domain.trace import Trace, _Builder

__all__ = ["Trace", "WitnessParser", "parse_vcd", "parse_vcd_text"]

_VAR_RE = re.compile(r"^\$var\s+\S+\s+\d+\s+(\S+)\s+(.+?)\s*\$end")
_SCOPE_RE = re.compile(r"^\$scope\b")
_UPSCOPE_RE = re.compile(r"^\$upscope\b")
_ENDDEFS_RE = re.compile(r"^\$enddefinitions\b")


class WitnessParser(Protocol):
    def parse(self, path: Path, signal_names: Sequence[str]) -> Trace: ...


def _to_int(token: str) -> int | None:
    """Binary token -> int. `x`/`z`/`-` (unknown) yield None rather than a fake 0."""
    if not token or any(c in "xzXZ-" for c in token):
        return None
    try:
        return int(token, 2)
    except ValueError:
        return None


def parse_vcd_text(text: str, signal_names: Sequence[str]) -> Trace:
    """Pure VCD → Trace (the testable core; `parse_vcd` is the thin file wrapper)."""
    wanted = list(dict.fromkeys(signal_names))
    wanted_set = set(wanted)

    # --- header: id -> name, resolved to the shallowest scope that declares it ---
    ids: dict[str, str] = {}  # vcd id -> signal name
    best_depth: dict[str, int] = {}  # signal name -> depth it was taken from
    step_id: str | None = None
    depth = 0
    body_start = 0

    lines = text.splitlines()
    for i, raw in enumerate(lines):
        line = raw.strip()
        if _ENDDEFS_RE.match(line):
            body_start = i + 1
            break
        if _SCOPE_RE.match(line):
            depth += 1
            continue
        if _UPSCOPE_RE.match(line):
            depth -= 1
            continue
        m = _VAR_RE.match(line)
        if not m:
            continue
        vid, name = m.group(1), m.group(2).strip()
        if name == "smt_step":
            step_id = vid
            continue
        if name in wanted_set and best_depth.get(name, 1 << 30) > depth:
            # A shallower declaration wins: the wrapper's port beats `dut.<same name>`.
            ids = {k: v for k, v in ids.items() if v != name}
            ids[vid] = name
            best_depth[name] = depth

    # --- body: accumulate current values, snapshot once per smt_step ---
    builder = _Builder()
    current: dict[str, int] = {}  # vcd id -> value
    step: int | None = None
    seen: set[str] = set()

    def commit() -> None:
        if step is None:
            return
        for vid, name in ids.items():
            val = current.get(vid)
            if val is not None:
                builder.set(step, name, val)
                seen.add(name)

    for raw in lines[body_start:]:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            # A timestamp closes the previous block; values persist, so re-committing
            # the same step is idempotent (last write wins with the settled values).
            commit()
            continue
        if line[0] in "bB":
            parts = line.split()
            if len(parts) != 2:
                continue
            token, vid = parts[0][1:], parts[1]
            val = _to_int(token)
            if vid == step_id:
                step = val if val is not None else step
            elif val is not None:
                current[vid] = val
            elif vid in ids:
                current.pop(vid, None)  # went unknown — drop rather than report a stale 0
        elif line[0] in "01xzXZ":
            vid = line[1:].strip()
            if not vid:
                continue
            val = _to_int(line[0])
            if vid == step_id:
                step = val if val is not None else step
            elif val is not None:
                current[vid] = val
            elif vid in ids:
                current.pop(vid, None)
        # 'r'/real, '$dumpvars', '$end' and friends are irrelevant to a bit-vector CEX.
    commit()

    signals = tuple(s for s in wanted if s in seen)
    return builder.build(signals)


def parse_vcd(path: Path, signal_names: Sequence[str]) -> Trace:
    """Parse a SymbiYosys/`yosys-smtbmc` VCD counterexample into a `Trace`.

    Only `signal_names` are kept (the interface ports), each resolved to the formal
    wrapper's top scope. Returns an empty trace if the file yields no usable steps.
    """
    return parse_vcd_text(Path(path).read_text(encoding="utf-8", errors="replace"), signal_names)
