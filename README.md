# Inductor

> **AI that writes and proves correctness properties for chips.**

Inductor reads a spec and a small RTL module, synthesizes formal properties with an
LLM, runs an open-source model checker (Yosys + SymbiYosys), and iterates on
counterexamples — automating the hardware-verification engineer's inner loop. The
LLM proposes; the solver disposes, so **hallucination cannot pass verification**.
Every reported result is a bounded proof to depth *k*, an unbounded proof, or a
concrete counterexample waveform — never the model's unverified say-so.

The demo: point it at a FIFO with an injected off-by-one in its full/empty logic.
Inductor synthesizes "never overflow / never underflow," gets a counterexample
waveform, narrates the exact failing cycle, pinpoints the bug — then proves the
property holds on the fixed version.

**Status:** M1–M4 built — verifies real RTL end-to-end and catches an injected FIFO
bug, live. See [ROADMAP.md](ROADMAP.md) for the plan.

---

## Run it

**Prerequisites:** **Python ≥ 3.11** (check: `python --version`). For the actual
verification you need a model checker — pick one:

- **Lightweight (works on Windows, no admin):** `pip install yowasp-yosys` — Yosys as
  WebAssembly. Drives the built-in `sat` backend (internal minisat, no external
  solver). This is what the dev install (`.[dev]`) pulls in.
- **Full stack:** the **OSS CAD Suite** (Yosys + SymbiYosys + Bitwuzla) on PATH —
  https://github.com/YosysHQ/oss-cad-suite-build — for the `sby` backend. Linux-native;
  **on Windows use WSL2**.

The offline `demo` and the unit tests need neither.

```bash
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
                                                        # (Linux/macOS: .venv/bin/activate)
pip install -e ".[dev]"     # once (includes yowasp-yosys)

inductor demo               # offline showcase: render a wrapper + a sample report
# Verify real RTL (run from the repo root; yowasp-yosys is sandboxed to the CWD):
inductor verify designs/counter.v --spec designs/counter.md --top counter --no-llm
# → P1, P2 ✅ PROVEN.  Try the over-strong property to see a counterexample:
inductor verify designs/counter.v --top counter --no-llm --props designs/counter_bad.props.json
# → PB ❌ FALSIFIED, with a waveform written under designs/_build/.

pytest                      # unit tests (fast, offline)
pytest -m integration       # runs a real proof via Yosys (needs a Yosys on PATH)
```

### The demo that lands

```bash
# Clean FIFO: the flag/occupancy invariants hold.
inductor verify designs/fifo.v --top fifo --no-llm --props designs/fifo.props.json
#   → F1 (full ⟺ count==4), F2 (empty ⟺ count==0)  ✅ PROVEN

# Buggy FIFO (off-by-one `full`): the bug is caught with a counterexample.
inductor verify designs/fifo_buggy.v --top fifo --no-llm --props designs/fifo.props.json
#   → F1 ❌ FALSIFIED (waveform shows full=0 at count==4); F2 ✅ PROVEN

# Benchmarks (charts need the `bench` extra: pip install -e ".[bench]"):
python -m benchmarks.bugcatch          # per-design verdicts + bug-catch chart
python -m benchmarks.depth_vs_time     # bounded-proof time vs BMC depth
```

### Commands

| Command | What it does |
|---|---|
| `inductor demo` | Offline: render the formal wrapper + a sample verdict report. |
| `inductor verify <rtl…> --top <name> --no-llm` | Discharge a hand-written property file against the RTL. |
| `inductor verify … --backend {auto,sby,yosys-sat}` | Pick the engine (auto: sby if present, else yosys-sat). |
| `inductor extract <rtl…> --top <name>` | Print the extracted interface model (debug). |
| `pytest` / `pytest -m integration` | Unit tests / live end-to-end tests. |
| `ruff check . && mypy` | Lint + typecheck. |

---

## Project docs

| Doc | What's in it |
|---|---|
| [DESIGN.md](DESIGN.md) | The full design and rationale — the single source of truth. |
| [ROADMAP.md](ROADMAP.md) | The milestone checklist (the plan + what's done). |
| [`docs/`](docs/) | Architecture decision records (ADRs) and long-form notes. |

## Tech stack

Python 3.11 · Yosys + SymbiYosys + Bitwuzla (open formal stack, ISC/MIT) ·
Anthropic SDK (`claude-opus-4-8`) · pytest / ruff / mypy. Pairs with **Congruent**
(software equivalence) as the formal-methods-meets-AI portfolio spine.

## License

MIT — see [LICENSE](LICENSE).
