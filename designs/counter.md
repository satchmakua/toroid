# Spec — `counter`

A 4-bit **saturating** up-counter.

- **Reset** (`rst`, synchronous, active-high): forces `count` to 0 on the next clock.
- **Enable** (`en`): when high and not at the maximum, `count` increments by 1 each
  clock; when high and already at the maximum (15), `count` stays at 15 (it
  **saturates** — it must never wrap to 0).
- **Hold**: when `en` is low (and not in reset), `count` retains its value.

**Properties a verification engineer would expect to hold:**

1. `count` never exceeds 15 (no overflow).
2. `count` never wraps from 15 back to 0 while enabled (saturation).
3. When `en` is low and out of reset, `count` is unchanged cycle-to-cycle.
4. After reset, `count` is 0.

**Reachability (anti-vacuity):** the counter can actually reach 15.
