# 4. Catch the FIFO bug with an assumption-free structural invariant

- **Status:** Accepted
- **Date:** 2026-06-28

## Context

M4's headline demo is the buggy FIFO. The natural property is temporal: "`count`
never exceeds DEPTH" (no overflow). But that only holds **from the reset state** —
from an arbitrary initial register state, `count` could already be > DEPTH. Enforcing
"start in reset" requires an **assumption** (`if ($initstate) assume(rst)`).

Investigation (M4) established that the lightweight **yosys-sat backend** — Yosys's
built-in `sat -prove-asserts` — **ignores `$assume` cells entirely**. A minimal
`assume(a); assert(a)` is reported FALSE (the solver picks `a=0`), with or without
`chformal -lower`. A validity-guard workaround (`assert(valid -> P)` with `valid`
tracking past assumptions) doesn't help: since `sat` won't *force* the assumed input,
it drives the guard false and the assertion passes **vacuously** — a false proof,
which is worse. So the yosys-sat backend cannot soundly verify any reset- or
protocol-dependent property. (The sby + Bitwuzla backend honors assumptions
correctly; it's the right tool for temporal safety, and is gated on the OSS CAD
Suite.)

## Decision

Demo the off-by-one with an **assumption-free structural invariant** that holds in
*every* state: `full == (count == DEPTH)` (and `empty == (count == 0)`). It needs no
reset, so the yosys-sat backend proves it on the clean FIFO and falsifies it on the
buggy one (whose `full` is `count == DEPTH-1`) — a real counterexample, fully
verifiable on Windows with just `pip install yowasp-yosys`. The temporal overflow
property and an arbiter/FSM gallery are documented as the sby-backend path.

Also required for FIFO designs: add `memory_map` to the yosys-sat prep flow so `sat`
can handle the `$mem` cell (it errors otherwise).

## Consequences

- **The demo lands live, soundly.** Clean → PROVEN, buggy → FALSIFIED + waveform, no
  external solver. The off-by-one *is* a flag/occupancy-consistency bug, so the
  structural invariant is the honest, natural property — not a contrivance.
- **A real backend asymmetry, documented.** yosys-sat = assumption-free invariants
  only; sby = full temporal/assumption-based verification. The CLI/report don't claim
  more than the backend can deliver; `--backend` selects.
- **Don't let the LLM (M2) lean on assumptions for the yosys-sat backend.** A
  synthesized property gated on a reset assumption will read as vacuous/over-strong
  there; on sby it's correct. A future refinement could make the synthesizer
  backend-aware.
- If/when sby lands, revisit: the temporal overflow property should PROVEN there, and
  this ADR's workaround becomes a yosys-sat-only note.
