# 3. Add a Yosys-`sat` discharge backend alongside SymbiYosys

- **Status:** Accepted
- **Date:** 2026-06-28

## Context

DESIGN.md §3 specifies SymbiYosys + Bitwuzla as the discharge engine. That stack is
Linux-native (it ships in the OSS CAD Suite) and was not installable on the dev
machine (Windows) without WSL2 + admin + a large download — so M1 could be *written*
but not *run* there. Accumulating unverified solver-integration code is exactly the
failure mode this project warns about.

Investigation found a lightweight, cross-platform path:

- **`yowasp-yosys`** — Yosys compiled to WebAssembly, `pip install`-able, runs on
  Windows (verified: Yosys 0.66).
- **Yosys's built-in `sat` command** — uses an internal minisat, so it needs **no
  external SMT solver and no SymbiYosys** to do BMC and temporal (k-)induction.

## Decision

Add a **second discharge backend**, `adapters/yosys_sat.py` (`YosysSatCli`),
implementing the same `SbyJobRunner` contract as the sby backend. The pipeline
(`pipeline/discharge.py`) is backend-agnostic; the CLI selects via
`--backend {auto,sby,yosys-sat}` (auto prefers sby when present). The sby + Bitwuzla
backend remains the primary/spec'd engine; yosys-sat is the zero-dependency fallback
that makes the full proof-or-counterexample flow runnable anywhere Yosys is — and is
what let M1 be **verified live**.

The verified Yosys flow: `prep -top X -flatten; async2sync; chformal -lower; sat …`
(BMC: `sat -seq N -prove-asserts -dump_vcd`; induction: `sat -tempinduct
-prove-asserts`). Result strings: `… no model found: SUCCESS!` / `… model found:
FAIL!`.

## Consequences

- **The flow is demonstrable everywhere** — `pip install yowasp-yosys` and a proof
  runs, including in CI and on Windows. The project's north star (proven-or-waveform
  on real RTL) is reachable without the OSS CAD Suite.
- **Backend asymmetry, documented:** yosys-sat does **not** implement the `cover`
  reachability run, so verdicts from it carry no vacuity guard (`cover_reachable` is
  left unchecked → never a false VACUOUS). Full vacuity checking needs the sby
  backend. The verdict taxonomy is unchanged; only the vacuity column differs.
- **Two engines to keep working.** The `SbyJobRunner` abstraction keeps the
  composition (`discharge`) shared; only the per-run shell + output parser differ.
- **WASM sandbox constraint:** yowasp-yosys mounts only the CWD, so paths must be
  CWD-relative and `inductor` is run from the project root. Native Yosys is unaffected.
- The two backends should not diverge in verdict semantics — both feed the same
  `decide_verdict`. If they ever disagree on a property, that's a bug to chase.
