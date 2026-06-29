# Spec — `fifo`

A synchronous FIFO, depth 4, width 8. Synchronous active-high `rst` clears it.
`wr_en` pushes `wdata` unless `full`; `rd_en` pops to `rdata` unless `empty`. `count`
reports the current occupancy (0–4).

**Structural invariants (hold in every state — no reset needed):**

1. `full` is asserted **exactly** when `count == 4` (the depth).
2. `empty` is asserted **exactly** when `count == 0`.

**Temporal safety (needs reset — sby backend):**

3. `count` never exceeds 4 (no overflow); a write is dropped when `full`.
4. `count` never underflows below 0; a read is dropped when `empty`.

**Reachability:** the FIFO can actually become full (`count == 4`).

The off-by-one bug (`fifo_buggy.v`) asserts `full` at `count == 3`, which violates
invariant 1 — caught structurally, with no reset assumption required.
