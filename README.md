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

**Status:** _scaffolded — walking skeleton runs offline._ See [ROADMAP.md](ROADMAP.md)
for the plan.

---

## Run it

**Prerequisites:**

- **Python ≥ 3.11** (check: `python --version`).
- **OSS CAD Suite** (Yosys + SymbiYosys + Bitwuzla) on PATH for the *real*
  verification flow — https://github.com/YosysHQ/oss-cad-suite-build. The stack is
  Linux-native; **on Windows, run inside WSL2**. The offline `demo` and the test
  suite need none of this.

```bash
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
                                                        # (Linux/macOS: .venv/bin/activate)
pip install -e ".[dev]"     # once
inductor demo               # offline showcase: render a wrapper + a sample report
pytest                      # tests (all green offline)
```

Once the toolchain is installed:

```bash
inductor verify designs/counter.v --spec designs/counter.md --top counter --depth 20
```

### Commands

| Command | What it does |
|---|---|
| `inductor demo` | Offline: render the formal wrapper + a sample verdict report. |
| `inductor verify <rtl…> --top <name>` | Synthesize + discharge properties (needs the toolchain). |
| `inductor extract <rtl…> --top <name>` | Print the extracted interface model (debug). |
| `pytest` | Run the test suite. |
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
