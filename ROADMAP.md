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

- [x] **M1 — Verify real RTL with a hand-written property (`--no-llm`).** Wired
  `ingest → render → discharge → report` end-to-end on `designs/counter.v` with a
  checked-in property file. Two discharge backends: **`yosys-sat`** (Yosys built-in
  minisat — no external solver, runs via `pip install yowasp-yosys`) and **`sby`**
  (SymbiYosys + Bitwuzla, OSS CAD Suite). _(= DESIGN M0.)_
  **Test:** `inductor verify designs/counter.v --top counter --no-llm` reports the
  invariants as PROVEN; with `--props designs/counter_bad.props.json` it reports
  FALSIFIED with a `.vcd`. ✅ **Confirmed live** (yosys-sat via yowasp, Windows):
  `pytest -m integration` green; CLI reports P1/P2 PROVEN and the bad property
  FALSIFIED with a real waveform.
  _Caveat: the `sby` + Bitwuzla backend is code-complete and unit-tested but its
  live run still awaits an OSS CAD Suite install (its integration tests skip)._

## Phase 2 — Property synthesis (the credibility milestone)

- [ ] **M2 — LLM synthesizes properties from interface + spec.** `adapters/llm.py`
  synthesis (Claude, structured outputs / Pydantic) + `pipeline/synth.py` compile-gate
  + anti-vacuity **repair loop** (feeds Yosys diagnostics back to the model, up to
  `--max-repairs`). Wired into `verify` (drop `--no-llm`). _(= DESIGN M1.)_
  **Test:** `inductor verify designs/counter.v --spec designs/counter.md --top
  counter` synthesizes properties that compile and discharge; the report shows real
  verdicts with provenance.
  _Status: pipeline **built and verified live with a fake LLM** — synth →
  compile-gate (real Yosys) → discharge (real yosys-sat) → report all proven on the
  counter (`test_synth_pipeline`). The real Claude call is code-complete but
  **gated on `ANTHROPIC_API_KEY`** (none in the dev env) — set a key and run
  `pytest -m integration` (runs `test_synth_live_with_claude`) or
  `inductor verify … --spec …`, then tick this box._

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
