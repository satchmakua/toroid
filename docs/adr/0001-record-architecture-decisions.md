# 1. Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-06-28

## Context

Significant, hard-to-reverse decisions (a framework, a data model, a boundary, a
protocol) need a durable record of *why*, so a future contributor
doesn't relitigate them or undo them blindly. `DESIGN.md` holds the current state;
ADRs hold the reasoning behind individual choices over time.

## Decision

We record architecture decisions as short Markdown files in `docs/adr/`, numbered
sequentially. Each captures the **context** (what forces were at play), the
**decision** (what we chose), and the **consequences** (what it makes easy and what
it makes hard, including the trade-offs accepted).

Keep them short. Add one when a decision is weighty enough that "why did we do it
this way?" will be asked later. Don't write one for routine, easily-reversed calls.

## Consequences

- Decisions have a paper trail; onboarding is faster.
- A small amount of discipline is required to write them.
- Superseded decisions stay in the log (mark them `Superseded by ADR-NNNN`) rather
  than being deleted — the history is the point.

---

_Copy this file to `NNNN-short-title.md` for the next decision. Template: Context →
Decision → Consequences._
