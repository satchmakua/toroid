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

- [x] **M2 — LLM synthesizes properties from interface + spec.** `adapters/llm.py`
  synthesis (Claude, structured outputs / Pydantic) + `pipeline/synth.py` compile-gate
  + anti-vacuity **repair loop** (feeds Yosys diagnostics back to the model, up to
  `--max-repairs`). Wired into `verify` (drop `--no-llm`). _(= DESIGN M1.)_
  **Test:** `inductor verify designs/counter.v --spec designs/counter.md --top
  counter` synthesizes properties that compile and discharge; the report shows real
  verdicts with provenance. ✅ **Confirmed live** (2026-07-13, `claude-opus-4-8`):
  Claude synthesized a real, guarded property set (reset, saturation, hold, increment,
  no-overflow — with `$past`/`$initstate` guards) that compiled on the first attempt.
  The **recorded fixture has 9 properties — 5 safety asserts + 4 reachability covers**
  — and the solver **proves all 5 asserts** (covers are anti-vacuity witnesses;
  yosys-sat reports `unknown` for cover mode). `test_synth_live_with_claude` covers the
  live path; the recorded output replays offline in CI (`test_llm_replay`, no key) and
  reproduces the five PROVEN verdicts.

## Phase 3 — Close the loop

- [x] **M3 — Counterexample loop.** Trace parsing (`yosys_sat.parse_sat_model` →
  per-step `domain.trace.Trace`; `domain.trace.summarize_trace` for deterministic
  narration), `adapters/llm.classify_cex` (structured output: rtl-bug / over-strong /
  missing-assumption + patch), and `pipeline/refine.py` — the guarded refine loop
  (terminates at `--max-refine`, RTL-bug terminal, anti-vacuity guard). Wired into
  `verify` (LLM path; `--no-refine` to skip). _(= DESIGN M2.)_
  **Test:** real bug → narrates the failing cycle and classifies the cause;
  over-strong property → refines and the cover stays reachable; the loop always
  terminates. ✅ **Confirmed live** (2026-07-13): the buggy FIFO's falsified `F1`
  invariant was parsed to a trace and classified live by Claude — captured to
  `tests/fixtures/fifo_full.classify.json` (cause `over_strong`, with a concrete gating
  patch). The loop's four guarantees (refine resolves, rtl-bug terminal, vacuity guard,
  bounded termination) and the deterministic narration are unit-tested with fakes in
  `test_refine.py`. _Honest scope: only the single live classification is captured as a
  fixture; the multi-round end-to-end loop is exercised with fakes, not recorded live.
  And yosys-sat ignores the `assume` cells the LLM adds, so on this backend a
  reset-dependent counterexample surfaces at the unconstrained initial state and gets
  classified `over_strong` (as here) rather than resolved — real ADR-0004 fallout the
  sby backend would lift._

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

- [x] **M5 (stretch) — RTL-to-RTL equivalence.** `render/equiv.py` (a miter: shared
  symbolic inputs, both DUTs, assert outputs equal) + `pipeline/equiv.py`
  (`check_equivalence`, port-compatibility check) + `inductor equiv` CLI. Designs:
  `max2.v` (spec), `max2_alt.v` (equivalent), `max2_min_bug.v` (impostor). _(= DESIGN M4.)_
  **Test:** equivalent pair proves; divergent pair produces a distinguishing input.
  ✅ **Confirmed live** (yosys-sat): `max2 ≡ max2_alt` PROVEN; `max2` vs
  `max2_min_bug` FALSIFIED with a distinguishing input (a=4,b=2 → 4 vs 2). Unit +
  live integration green.
  _Scope note: combinational equivalence is assumption-free (shared inputs are
  structural), so it runs on yosys-sat. Sequential equivalence with differing reset
  states, and an AXI-lite handshake property suite, need the sby backend (assumes;
  ADR-0004) — deferred._

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
- [x] **H1 — Live LLM proof + offline fixture.** ✅ Done (2026-07-13). M2 synthesis ran
  **live** (`claude-opus-4-8`): Claude synthesized a guarded property set that compiled
  first-try — the recorded fixture holds 9 properties (5 asserts + 4 covers) and all 5
  asserts prove on the counter. On the buggy FIFO the falsified invariant was parsed to a
  trace and classified live (cause `over_strong`), captured as a fixture too. Both are
  recorded via `scripts/capture_fixtures.py` into `tests/fixtures/`; `RecordedLLM` replays
  the synthesis in CI with no key (`test_llm_replay`), and `test_synth_live_with_claude`
  covers the live path. The synthesis artifact is pinned at the top of the README.
- [ ] **H2 — Full `sby` + Bitwuzla in CI (vacuity + temporal).** Stand up the OSS CAD Suite
  so the `sby` backend runs — lifting the ADR-0004 limit so **vacuity checking** and
  **assume-dependent** properties are proven on the real path. *Accept:* a CI job proves an
  assume-dependent property and catches a vacuous pass.
  _Progress (2026-07-14): **the `sby` + Bitwuzla backend is now verified live** (OSS CAD
  Suite 20260714, native Windows). Running it surfaced and fixed **two real bugs in the
  previously-unrun path**: (1) the `.sby` `[files]` section used process-relative paths but
  sby resolves them against its own workdir → now absolute (`adapters/sby.py`); (2) a stale
  `discharge(sby=…)` kwarg in the integration test (the API is `runner=`). Both ADR-0004
  acceptance behaviors are demonstrated and captured as gated tests (`test_counter_flow.py`):
  `counter_assume.props.json` → `PA` **PROVEN on sby / FALSIFIED on yosys-sat** (assume
  honored), and `counter_vacuous.props.json` → `PV` **VACUOUS** (cover unreachable). With
  the suite present, `pytest -m integration` = **12 passed**; without it the 4 sby tests
  skip cleanly. **Remaining:** wire + observe the actual GitHub Actions job (Linux, via
  `YosysHQ/setup-oss-cad-suite`; scaffolded/commented in `ci.yml`) — the local run can't be
  observed in CI without a push. Note: the Windows nightly mis-names `yosys-smtbmc`/
  `yosys-witness` (double `.exe`), worked around locally with `.cmd` shims; Linux CI is
  unaffected._
- [x] **H3 — Property-test the verdict policy.** ✅ Done (2026-07-13).
  `test_policy_properties.py` fuzzes `decide_verdict` over every `RawOutcome` with
  Hypothesis: PROVEN only via an unbounded engine, error/CEX precedence, VACUOUS iff a
  pass has an unreachable cover, unchecked-cover never forces VACUOUS, total + deterministic.
- [x] **H4 — Artifact-first README.** ✅ Done (2026-07-13). The README opens with the live
  Claude-synthesized-and-proven result, the buggy-FIFO waveform, and the equivalence
  distinguishing input, with exact reproduce commands.
