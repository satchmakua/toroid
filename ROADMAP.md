# ROADMAP — Inductor

The milestone checklist.

**Rules of the road:**
- Each milestone is an **independently runnable** slice, testable end-to-end.
- Every milestone ends with explicit **Test** steps (the acceptance criteria).
- Build **top-down**: a thin end-to-end slice first, then deepen.
- Check a box **only after its Test passes**.

> **Mapping to DESIGN.md §7:** M0 here is the offline walking skeleton; **M1–M5 here correspond to DESIGN's M0–M4.** The split exists because
> DESIGN's first milestone needs the OSS CAD Suite toolchain, which is Linux-native
> — so M0 here is everything that runs *without* it.
>
> **Toolchain note:** M1 onward require Yosys + SymbiYosys + Bitwuzla on PATH (OSS
> CAD Suite; WSL2 on Windows). Keep toolchain-dependent (`sby`-shelling) tests gated
> so they **skip** cleanly when the toolchain is absent — unit tests stay green
> everywhere.

---

## Phase 0 — Walking skeleton

- [x] **M0 — Skeleton & it runs (offline).** Pure domain core (interface, property,
  verdict, policy), the `PropertySet → *_fv.sv` renderer, the Markdown report, and a
  CLI (`demo` / `verify` / `extract` / `version`) — all running with no external
  toolchain. Lint, typecheck, and a real test suite are wired and green.
  **Test:** `pip install -e ".[dev]"` then `inductor demo` prints a rendered wrapper
  and a sample report; `pytest` is green; `ruff check . && mypy` clean.

## Phase 1 — The harness (ground truth)

- [ ] **M1 — Verify real RTL with a hand-written property (`--no-llm`).** Wire
  `ingest → render → sby → verdict → report` end-to-end on `designs/counter.v` with a
  checked-in property file (no LLM yet). Implement `adapters/yosys.py`
  (`write_json` interface extraction + `read_verilog -formal` compile gate) and
  `adapters/sby.py` (build `.sby`, run, parse PASS/FAIL/UNKNOWN + depth, collect
  `.yw`/`.vcd`). Map outcomes through `domain/policy.py`. _(= DESIGN M0.)_
  **Test (needs toolchain):** `inductor verify designs/counter.v --top counter
  --no-llm` reports the counter's invariants as PROVEN/BOUNDED-PASS; flip a property
  to something false and it reports FALSIFIED with a `.vcd`.

## Phase 2 — Property synthesis (the credibility milestone)

- [ ] **M2 — LLM synthesizes properties from interface + spec.** Implement
  `adapters/llm.py` synthesis (Claude, structured outputs) and the compile-gate
  repair loop; enforce the anti-vacuity invariant (every assert has a reachable
  cover). Discharge and report. _(= DESIGN M1.)_
  **Test:** `inductor verify designs/counter.v --spec designs/counter.md --top
  counter` synthesizes properties that compile and discharge; the report shows real
  verdicts with provenance.

## Phase 3 — Close the loop

- [ ] **M3 — Counterexample loop.** Implement `adapters/witness.py` (`.yw` parse →
  `Trace`) and `pipeline/refine.py`: narrate the failing cycle, classify
  (rtl-bug / over-strong / missing-assumption), refine (guarded against vacuity),
  re-run until stable, with the termination cap. _(= DESIGN M2.)_
  **Test:** point it at a design with a real bug → it narrates the failing cycle and
  classifies the cause; point it at an over-strong property → it refines and the
  cover stays reachable; the loop always terminates.

## Phase 4 — Make it land

- [ ] **M4 — Demo gallery + benchmarks.** Add `designs/fifo.v` + `fifo_buggy.v`
  (off-by-one full/empty), an arbiter, and an FSM; catch the injected FIFO bug with a
  narrated waveform, prove invariants on clean modules, and produce matplotlib charts
  (proof-depth-vs-time, bug-catch rate) in `benchmarks/`. _(= DESIGN M3 — public
  ship.)_
  **Test:** the buggy-FIFO run produces a screenshot-worthy proven-or-waveform
  report; the benchmark scripts emit charts.

- [ ] **M5 (stretch) — Equivalence + protocols.** RTL-to-RTL equivalence (miter +
  Yosys `equiv`/`miter`) and an AXI-lite handshake property suite. _(= DESIGN M4.)_
  **Test:** two equivalent counters prove equivalent; a deliberately divergent pair
  produces a distinguishing trace.

---

**North star:** one screenshot of *proven-or-waveform on real RTL* — every claim
tied to a solver verdict — that a senior verification engineer would trust at a
glance.
