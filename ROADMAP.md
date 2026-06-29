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

- [ ] **M3 — Counterexample loop.** Trace parsing (`yosys_sat.parse_sat_model` →
  per-step `domain.trace.Trace`; `domain.trace.summarize_trace` for deterministic
  narration), `adapters/llm.classify_cex` (structured output: rtl-bug / over-strong /
  missing-assumption + patch), and `pipeline/refine.py` — the guarded refine loop
  (terminates at `--max-refine`, RTL-bug terminal, anti-vacuity guard). Wired into
  `verify` (LLM path; `--no-refine` to skip). _(= DESIGN M2.)_
  **Test:** real bug → narrates the failing cycle and classifies the cause;
  over-strong property → refines and the cover stays reachable; the loop always
  terminates.
  _Status: trace parsing + **deterministic cycle-by-cycle narration verified live**
  (FALSIFIED reports show the real `count` trajectory). The refine loop's guarantees
  (resolves / rtl-bug-terminal / vacuity-guard / termination) are **unit-tested
  offline with fakes** (`test_refine.py`). The LLM `classify_cex` + the live refine
  loop are code-complete but **gated on `ANTHROPIC_API_KEY`** — set a key and run
  `inductor verify … --spec …` on a buggy design, confirm, then tick._

## Phase 4 — Make it land

- [x] **M4 — Demo gallery + benchmarks.** `designs/fifo.v` + `fifo_buggy.v`
  (off-by-one `full`), with structural flag/occupancy invariants; `benchmarks/`
  (`bugcatch.py`, `depth_vs_time.py`) emitting Markdown/CSV + matplotlib charts.
  _(= DESIGN M3 — public ship.)_
  **Test:** the buggy-FIFO run produces a screenshot-worthy proven-or-waveform
  report; the benchmark scripts emit charts. ✅ **Confirmed live** (yosys-sat,
  Windows): clean FIFO → F1/F2 PROVEN, buggy FIFO → F1 FALSIFIED with a
  counterexample trace + F2 PROVEN; both charts generate.
  _Scope note: the off-by-one is caught with an **assumption-free structural
  invariant** (`full ⟺ count==DEPTH`) because the yosys-sat backend can't honor
  reset/`assume` cells (legacy `sat` limitation — see ADR-0004). Temporal overflow
  safety (needs reset) and an arbiter/FSM gallery are deferred to the sby backend._

- [ ] **M5 (stretch) — Equivalence + protocols.** RTL-to-RTL equivalence (miter +
  Yosys `equiv`/`miter`) and an AXI-lite handshake property suite. _(= DESIGN M4.)_
  **Test:** two equivalent counters prove equivalent; a deliberately divergent pair
  produces a distinguishing trace.

---

**North star:** one screenshot of *proven-or-waveform on real RTL* — every claim
tied to a solver verdict — that a senior verification engineer would trust at a
glance.

---

## Review-driven hardening — from *built* to *proven* (added 2026-06-28)

> Added after an external code review (captured in `../ai-docs/project_eval/`). The
> feature milestones above are sound and several are already done — these items raise
> the bar from "the machinery works" to a **complete, proven, stress-tested** product.
> **Standing rule:** a milestone is checked only when it has produced **one real,
> captured, reproducible artifact**, not merely passing unit tests.

**Definition of Done — the "Sparkle Bar"** (applies to every milestone):
1. **Real artifact captured** — produced against reality (real model/solver/data), pinned at the top of the README with the exact reproduce command.
2. **Flagship demo in one screen** — the named demo shipped as a screenshot/gif.
3. **Stress-tested** — property-based + failure-path + one scale test on the invariant-critical core, not just happy-path units.
4. **Honest numbers** — bounds/CIs, a named baseline, an explicit "can't do" list.
5. **Cold-clone reproducible** — pinned deps, fixed seeds, one `make demo`, CI runs the real-or-recorded path.
6. **Polished** — no stray files, consistent docs, README opens with the artifact.
7. **Positioned** — one paragraph: who it's for, what it beats, why this not the obvious alternative.

**Hardening items (Inductor-specific):**
- [ ] **H1 — Live LLM proof + offline fixture.** Run M2 synthesis and the M3 `classify_cex`/refine loop **live once** with a key; commit the transcript + the generated SVA, and **record the Anthropic exchange as a fixture** so `pytest` exercises the LLM path offline (no key) in CI. *Accept:* a committed example shows real Claude-synthesized properties that compile + discharge, and a buggy design where the live loop narrates → classifies → refines to a clean result; an offline replay covers it.
- [ ] **H2 — Full `sby` + Bitwuzla in CI (vacuity + temporal).** Stand up the OSS CAD Suite on Linux/WSL2 CI so the `sby` backend runs — lifting the ADR-0004 "assumption-free structural invariant" limit so **vacuity checking** and **reset-dependent** properties (e.g. temporal overflow safety) are proven on the real path. *Accept:* a CI job proves a reset-dependent overflow-safety property and catches a vacuous pass on the `sby` backend.
- [ ] **H3 — Property-test the verdict policy.** Fuzz `decide_verdict` over randomized `RawOutcome`s to prove the honesty ordering (FALSIFIED > VACUOUS > PROVEN-only-via-unbounded > BOUNDED_PASS) holds for *all* inputs — the safety-critical core deserves property tests, not just examples. *Accept:* a Hypothesis suite over the policy passes.
- [ ] **H4 — Artifact-first README.** Lead with the FIFO proven-or-waveform screenshot + the benchmark charts (bug-catch rate, depth-vs-time).
