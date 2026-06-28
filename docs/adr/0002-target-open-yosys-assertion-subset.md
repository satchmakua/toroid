# 2. Target the open Yosys assertion subset, not full SVA / Verific

- **Status:** Accepted
- **Date:** 2026-06-28

## Context

Inductor model-checks Verilog with the open formal stack (Yosys + SymbiYosys). The
synthesized properties have to be expressed in a language Yosys can actually
elaborate. There are two paths:

1. **Full SystemVerilog Assertions (SVA)** — concurrent assertions, sequences,
   `|->`/`|=>` temporal layers. The open Yosys Verilog frontend supports only
   *immediate* assertions; full SVA requires the **commercial Verific** frontend
   (Tabby CAD Suite) — a paid dependency.
2. **The supported open subset** — immediate `assert`/`assume`/`cover` inside a
   clocked `always` block, plus Yosys formal helpers (`$past`, `$rose`, `$fell`,
   `$stable`, `$anyseq`, `$anyconst`, `$initstate`). This is the idiom used by the
   SymbiYosys/ZipCPU tutorials and is fully free. (Verified against YosysHQ docs,
   2026-06-28.)

This is the single most load-bearing technical decision in the project (DESIGN.md §4.1).

## Decision

**v1 targets the supported open subset, exclusively.** The LLM is constrained to emit
only this subset; properties are bound to the DUT via a generated formal wrapper
(`<top>_fv`) using `$anyseq` stimulus, rather than relying on SystemVerilog `bind`
(which the open frontend supports inconsistently). A Yosys compile gate
(`read_verilog -formal`) rejects anything outside the subset before it can reach a
solver. Full SVA via Verific is a documented roadmap upgrade, never a v1 dependency.

## Consequences

- **Free and reproducible.** No commercial license; anyone can run the whole flow
  from the OSS CAD Suite. Inductor's own license (MIT) stays unencumbered.
- **Honest scope.** Multi-cycle behavior is expressed with `$past`/`$rose`/etc. —
  expressive enough for the v1 property classes (no-overflow, FSM invariants,
  handshake correctness) but not arbitrary temporal SVA. Stated plainly as a non-goal.
- **The compile gate is mandatory.** Because the LLM will sometimes emit
  unsupported SVA, the gate + repair loop is not optional polish — it is core to M2.
- **Reversible-ish.** If Verific is ever adopted, the renderer gains a second target;
  the domain model (properties, verdicts) is unchanged. Mark this ADR superseded then.
