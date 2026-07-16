# Toroid — Design

> An agent that reads a spec and RTL, synthesizes formal properties, runs a model checker, and iterates on counterexamples — automating the hardware-verification engineer's loop. The LLM proposes; the solver disposes. **Hallucination cannot pass verification.**

**Status:** Implemented — M0–M5 and hardening H1–H4 shipped; see [ROADMAP.md](ROADMAP.md) for the acceptance tests · **Language:** Python 3.11+ · **Stack target:** CLI + library; the yosys-sat path runs anywhere (incl. Windows) via `yowasp-yosys`, the `sby` backend targets Linux/WSL2 · **LLM:** Claude Opus 4.8


> **Legal / licensing — clean for an open portfolio project (verified 2026-06-28).** Yosys and SymbiYosys are **ISC**; Bitwuzla is **MIT**; ABC is permissive (MIT-style). All ship together in the **OSS CAD Suite**. Yices is **GPLv3** — kept as an optional engine, never a default or a bundled dependency, so Toroid's own license stays unencumbered. Full SystemVerilog Assertion (SVA) parsing requires the commercial **Verific** frontend (Tabby CAD Suite); Toroid v1 deliberately targets the **free** open frontend and the assertion subset it supports (see §4). No vendor RTL or IP is redistributed — only original sample designs.

---

## 1. Concept

A hardware-verification engineer's inner loop looks like this: read the spec and the RTL, decide what *must always be true*, write those properties as assertions, run a model checker, stare at the counterexample waveform when it fails, decide whether the bug is in the design or the property, fix it, and re-run. It is slow, senior, scarce work — and almost untouched by modern AI tooling.

Toroid closes that loop. Point it at a small Verilog module and a natural-language spec:

```
$ toroid verify designs/fifo.v --spec designs/fifo.md --top fifo --depth 20
```

It extracts the module's true interface from Yosys, asks Claude to propose safety properties grounded in that interface and the spec, renders them into a Yosys-checkable formal wrapper, and discharges them with SymbiYosys. For each property it returns one of: **PROVEN** (unbounded, via k-induction or IC3/PDR), **BOUNDED-PASS** (no counterexample within depth *k*), or **FALSIFIED** with a concrete waveform. On a falsification it parses the trace, narrates the failing cycle, classifies the cause (RTL bug / over-strong property / missing assumption), patches, and re-runs until stable — then writes a report where **every claim is tied to a solver verdict, never to the model's say-so**.

The demo that lands: a FIFO with an injected off-by-one in its full/empty logic. Toroid synthesizes "never overflow / never underflow," gets a counterexample waveform, narrates the exact failing cycle, names the bug — then proves the property holds on the fixed version. One screenshot of *proven-or-waveform on real RTL* communicates the entire value.

### Engineering pillars (the three things that make or break this)

1. **The verification harness is ground truth — it must be airtight.** The entire credibility claim rests on every reported verdict coming from a real solver run, deterministically reproducible, with the verdict taxonomy parsed correctly from SymbiYosys output. If the harness ever reports PROVEN when the solver said something weaker, the project's thesis collapses. This layer is pure, deterministic, and the most heavily tested.

2. **Synthesized properties must compile, bind, and be non-vacuous.** The LLM has to emit assertions in the *exact* subset the open Yosys frontend accepts (§4), bound to the module's real ports and widths, that elaborate without error — and that aren't trivially true. A property that passes vacuously (unreachable antecedent, or an over-strong assumption that makes everything true) is worse than useless: it's a false "PROVEN." A **compile gate** and a **vacuity guard** sit between synthesis and any green checkmark.

3. **The counterexample loop must converge — and must not cheat.** Refinement has to terminate (bounded iterations, monotonic progress) and must distinguish *legitimately tightening* a property from *weakening it into vacuity* to make a red turn green. The loop's stopping conditions and anti-vacuity check are the hardest design problem here.

---

## 2. Goals / Non-goals

**Goals (v1 — each testable):**

- Verify small **synthesizable Verilog-2005 / light-SystemVerilog** modules: counter, FIFO, arbiter, simple FSM, ALU slice (≤ ~500 lines, single clock).
- Extract a faithful **interface model** (ports, directions, widths, clock, reset) directly from Yosys — never guessed by the LLM.
- **Synthesize safety properties** (assertions + assumptions + covers) from interface + spec, grounded and schema-constrained, that compile against `read_verilog -formal` on the first or repaired attempt.
- **Discharge** via SymbiYosys in BMC, k-induction (`prove`), and `cover` modes, plus IC3/PDR (`abc pdr`) for unbounded proofs.
- **Classify and refine** on counterexamples: parse the trace, narrate it, decide RTL-bug vs over-strong-property vs missing-assumption, patch, re-run, terminate.
- Emit a **report** (Markdown + JSON) where every property carries a verdict, the engine and depth that produced it, and — on failure — a waveform; plus a vacuity check on every pass.
- Ship a **demo gallery** catching an injected FIFO bug and proving invariants on clean modules, with **benchmark charts** (proof depth vs. time, bug-catch rate).

**Non-goals (v1) — deliberately out of scope; these protect the build:**

- **Full concurrent SVA** (sequences, `throughout`, complex `|->` temporal layers). Requires the commercial Verific frontend. *Roadmap; v1 uses the supported subset (§4).*
- **Full-chip / large industrial IP / multi-clock CDC.** v1 is single-clock, small modules.
- **Liveness / fairness at scale.** SymbiYosys supports liveness, but robust liveness verification is a separate hard problem. *Out of v1; safety only.*
- **Dynamic simulation / UVM / coverage closure on real designs.** Toroid is formal-only.
- **Security / side-channel / fault properties.** Roadmap.
- **Floating-point, analog, gate-level, timing.** Bit-vector + array (memory) logic only.
- **A GUI.** CLI + report artifacts only. (SymbiYosys has `sby-gui`; not our surface.)
- **Auto-fixing the RTL.** Toroid diagnoses and pinpoints; it does not rewrite the design under test. It *may* refine its own properties/assumptions.
- **Synthesizing the design.** Toroid verifies RTL it is given; it does not author DUTs.

---

## 3. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | **Python 3.11+** | Glue language for orchestrating external tools + the Anthropic SDK; `match`, `tomllib`, dataclasses, strong typing all native. |
| Packaging | **uv + pyproject.toml** | Fast, reproducible installs; lockfile for the demo. |
| RTL parse / synth | **Yosys** (ISC) | The open synthesis/formal workhorse. `read_verilog -formal` is both the **compile gate** and the source of the formal helper functions; `write_json` is the **interface model** source of truth. |
| Formal driver | **SymbiYosys (`sby`)** (ISC) | Standard front-end for Yosys formal flows: BMC, `prove` (k-induction), `cover`. Bundled engine config drives the solvers. |
| SMT solver (default) | **Bitwuzla** (MIT) | Boolector's successor; repeated SMT-COMP bit-vector winner. Best fit for hardware (QF_BV + arrays for memories). MIT keeps our license clean. |
| Unbounded engine | **ABC `pdr`** (permissive) | IC3/PDR — often proves unbounded safety where k-induction stalls. The escalation path past BMC. |
| Solver (alt) | **Z3** (MIT), **Yices** (GPLv3, opt-in) | Z3 for portability/debug; Yices fast on some queries but GPL, so never default/bundled. |
| Trace format | **Yosys witness `.yw`** (parse) + **VCD** (display) | `.yw` is structured JSONL — clean to parse via Yosys's `ywio` module. VCD is for the human screenshot. |
| Toolchain delivery | **OSS CAD Suite** | One nightly bundle: Yosys + sby + Bitwuzla + ABC + `yosys-witness`. Dev install = unpack + add to PATH. |
| LLM | **Anthropic Python SDK**, `claude-opus-4-8` | Adaptive thinking (`thinking={"type":"adaptive"}`), `effort:"high"`. Property synthesis and CEX classification use **structured outputs** (`messages.parse()` + Pydantic) so output is schema-valid by construction. (Verified against the Anthropic API docs, 2026-06-28.) |
| Trace/VCD reader (display) | **`vcdvcd`** | Lightweight, maintained VCD reader for rendering human-facing waveforms; primary trace parse is `.yw`. |
| Charts (benchmarks) | **matplotlib** | Proof-depth-vs-time and bug-catch-rate plots for the demo. |
| CI | **GitHub Actions** + `YosysHQ/setup-oss-cad-suite@v4` | One-line toolchain in CI; Linux runner. |
| Test | **pytest** | Domain layer unit-tested with the toolchain mocked; integration tests run real `sby` on sample designs. |

**Platform note (assumption, not a question):** the open formal stack is Linux-native and most reliable there. The author's machine is Windows 11, so the primary dev environment is **WSL2 (Ubuntu) + OSS CAD Suite**, and CI runs on Linux. The Python package itself is OS-agnostic — it shells out to the toolchain — but the toolchain is assumed to be on a Linux-like PATH. Native-Windows OSS CAD Suite builds exist as a fallback but are not the supported path.

---

## 4. The domain-critical core — get this exactly right

Everything hinges on four things being precise: **the supported assertion subset**, **the interface model**, **the property + binding contract**, and **the verdict taxonomy with its vacuity guard**. This is where a vague design would silently report false proofs.

### 4.1 The supported assertion subset (the hard constraint)

The free Yosys frontend (no Verific) supports, under `read_verilog -formal`:

- **Immediate** `assert(expr)`, `assume(expr)`, `cover(expr)`, `restrict(expr)` inside clocked `always @(posedge clk)` blocks.
- Formal helper functions: `$past(e, n)`, `$rose`, `$fell`, `$stable`, `$changed`, `$initstate`, `$anyconst`, `$anyseq`, `$allconst`, `$allseq`, `$global_clock`.
- A *limited* slice of concurrent `assert property (@(posedge clk) ...)` with simple `|->` / `|=>` — **not relied upon**.

**Decision:** Toroid's canonical render target is **immediate assertions inside a clocked `always` block** (the ZipCPU / SymbiYosys idiom), using `$past`/`$rose`/`$stable` for multi-cycle behavior and `$anyseq`/`$anyconst` for symbolic stimulus. This is the universally-supported, portable form. The LLM is constrained to emit *only* this subset; the compile gate (§6.1) rejects anything else before it can reach a solver. Full SVA is a documented Verific-only upgrade (roadmap), never a v1 dependency.

Properties are bound to the DUT via a generated **formal wrapper** `<top>_fv` that instantiates the DUT, drives free inputs with `$anyseq`, and holds the assertions — rather than relying on SystemVerilog `bind`, which the open frontend supports inconsistently.

```systemverilog
// RENDERED (illustrative): designs/_build/fifo_fv.sv  — supported subset only
module fifo_fv (input clk);
    // free, symbolic stimulus for DUT inputs
    wire        rst   = $anyseq;
    wire        wr_en = $anyseq;
    wire        rd_en = $anyseq;
    wire [7:0]  wdata = $anyseq;
    wire [7:0]  rdata;
    wire        full, empty;

    fifo dut (.clk(clk), .rst(rst), .wr_en(wr_en), .rd_en(rd_en),
              .wdata(wdata), .rdata(rdata), .full(full), .empty(empty));

    // assumption: hold reset for one cycle at start
    always @(posedge clk) if ($initstate) assume (rst);

    always @(posedge clk) begin
        // P1  no overflow: never write into a full FIFO (after reset)
        if (!$initstate && !$past(rst))
            assert (!($past(full) && $past(wr_en) && !$past(rd_en)
                      && dut.count == 8'd16 /* DEPTH overflow */));
        // P3  reachability cover: the FIFO can actually fill (anti-vacuity)
        cover (full);
    end
endmodule
```

### 4.2 Interface model (extracted, never guessed)

Produced by `yosys -p "read_verilog -formal <f>; hierarchy -top <top>; proc; write_json <out>"` and parsed from the JSON `ports`/`netnames` (direction + bit width). The LLM receives this object — it never reads widths off the raw source.

```python
@dataclass(frozen=True)
class Port:
    name: str
    direction: Literal["input", "output", "inout"]
    width: int                      # bit-width, derived from JSON "bits"
    is_clock: bool = False
    is_reset: bool = False

@dataclass(frozen=True)
class ModuleInterface:
    top: str
    ports: tuple[Port, ...]
    clock: str | None               # detected/declared clock port
    reset: str | None               # detected/declared reset port
    reset_active_high: bool = True
    internal_signals: tuple[str, ...] = ()   # hints from fsm/proc passes (e.g. state regs)
```

### 4.3 Property + binding contract

```python
class PropertyKind(StrEnum):
    ASSERT = "assert"     # must always hold
    ASSUME = "assume"     # constrains the environment
    COVER  = "cover"      # reachability / anti-vacuity witness

@dataclass(frozen=True)
class Property:
    pid: str                        # stable id, e.g. "P1"
    kind: PropertyKind
    summary: str                    # one-line human description
    expr: str                       # Yosys-subset SystemVerilog expression
    rationale: str                  # why this follows from spec/interface (provenance)
    clocked: bool = True            # rendered in always @(posedge clk)
    origin: Literal["llm", "human", "refined"] = "llm"

@dataclass(frozen=True)
class PropertySet:
    interface: ModuleInterface
    properties: tuple[Property, ...]
    # invariant: every ASSERT has at least one COVER establishing its antecedent is reachable
```

### 4.4 Verdict taxonomy + vacuity guard (the honesty layer)

```python
class Verdict(StrEnum):
    PROVEN       = "proven"        # unbounded: k-induction or pdr passed, no CEX
    BOUNDED_PASS = "bounded_pass"  # BMC to depth k, no CEX within k (NOT unbounded)
    FALSIFIED    = "falsified"     # CEX found — trace attached
    VACUOUS      = "vacuous"       # assert passed but its cover is UNREACHABLE
    INCONCLUSIVE = "inconclusive"  # timeout / resource limit / solver gave up
    ERROR        = "error"         # compile/elaboration failure — never reached a solver

@dataclass(frozen=True)
class PropertyResult:
    pid: str
    verdict: Verdict
    engine: str | None              # "smtbmc/bitwuzla", "abc/pdr", ...
    depth: int | None               # BMC/induction depth reached
    trace_yw: Path | None           # structured witness (falsified)
    trace_vcd: Path | None          # human waveform (falsified)
    wall_seconds: float
    detail: str = ""
```

**Bounding policy (pure, in `domain/policy.py`):** run `cover` first (reachability + anti-vacuity), then BMC to `--depth` (default **20**); for each surviving ASSERT attempt unbounded proof via `prove` (k-induction) and `abc pdr`. Report **PROVEN** only if an unbounded engine succeeds; otherwise **BOUNDED_PASS** at depth *k*. An ASSERT that passes while its companion COVER is unreachable is reported **VACUOUS**, not PROVEN. Honesty framing throughout: *"bounded proof to depth k, or a concrete counterexample waveform"* — never "unbounded correctness" unless an unbounded engine actually closed it.

---

## 5. Architecture

**Pattern: ports-and-adapters (hexagonal) around a pure domain core.** The domain (interface, property, verdict, policy) is pure Python with no I/O — fully unit-testable and the place "ground truth" lives. Every nondeterministic or external dependency (Yosys, SymbiYosys, the LLM, the filesystem) is wrapped behind an adapter interface, so the pipeline can be tested with all three external systems mocked. This is what lets pillar #1 (the airtight harness) be verified in CI without flakiness, and isolates the one stochastic component (the LLM) behind a single port.

```
                         ┌──────────────────────── pipeline ───────────────────────┐
  spec(NL) + module.v ──▶│ synth ──▶ render ──▶ discharge ──▶ refine ──▶ report     │──▶ report.md / .json
                         └────┬──────────┬──────────┬───────────┬──────────┬────────┘
                              │          │          │           │          │
                    ┌─────────▼──┐  ┌────▼─────┐ ┌──▼──────┐ ┌──▼───────┐  │
   adapters ───────▶│ llm (synth │  │ checker  │ │ sby     │ │ witness  │  │
   (impure I/O)     │  /classify)│  │ render   │ │ runner  │ │ (.yw)    │  │
                    └─────┬──────┘  └────┬─────┘ └──┬──────┘ └──┬───────┘  │
                          │   ┌──────────▼──────────▼───────────▼──┐       │
                          │   │ yosys (write_json + -formal gate)  │       │
                          │   └────────────────────────────────────┘       │
                          ▼                                                 ▼
                    ┌───────────────────────── domain (pure) ───────────────────────┐
                    │ ModuleInterface · Property/PropertySet · Verdict/PropertyResult │
                    │ policy: bounding + refinement decisions (no I/O)                │
                    └─────────────────────────────────────────────────────────────────┘
```

**Repo layout:**

```
toroid/
  pyproject.toml
  README.md  DESIGN.md  ROADMAP.md
  src/toroid/
    domain/      interface.py  properties.py  verdicts.py  policy.py   # pure, no I/O
    adapters/    yosys.py  sby.py  witness.py  llm.py                  # external systems
    render/      checker.py                                           # PropertySet → *_fv.sv
    pipeline/    synth.py  discharge.py  refine.py  report.py
    cli.py                                                            # `toroid verify ...`
  designs/       counter.v  fifo.v  fifo_buggy.v  arbiter.v  fsm.v + *.md specs
  prompts/       synth.system.md  classify.system.md  fewshot/*.sv
  tests/         unit/ (mocked) + integration/ (real sby on designs/)
  benchmarks/    depth_vs_time.py  bugcatch.py
```

---

## 6. Core systems

### 6.1 RTL ingest + compile gate (`adapters/yosys.py`)

Two jobs. **Extract** the interface model via `write_json`. **Gate** every candidate property set: render the `*_fv.sv` wrapper and run `read_verilog -formal` on DUT+wrapper; if elaboration fails, the verdict is `ERROR` and the synthesis loop is handed the compiler diagnostics to repair — *no malformed property ever reaches a solver*.

```python
class YosysAdapter(Protocol):
    def extract_interface(self, sources: list[Path], top: str) -> ModuleInterface: ...
    def compile_check(self, sources: list[Path], wrapper: Path, top: str) -> CompileResult:
        """read_verilog -formal; returns ok=True or structured errors for the repair loop."""
```

### 6.2 Property synthesis (`pipeline/synth.py` + `adapters/llm.py`)

The LLM receives the `ModuleInterface` and the spec and returns a `PropertySet` via **structured output** (Pydantic schema = the §4.3 types), so the response is schema-valid by construction. The system prompt hard-constrains it to the §4.1 subset with few-shot examples of correct immediate-assertion idioms. Output passes the **compile gate**; on failure, diagnostics + the offending expr go back for up to *N* repair rounds. Every ASSERT must come with a COVER that makes its antecedent reachable (enforced as a synthesis invariant, not a suggestion).

```python
class LLMAdapter(Protocol):
    def synthesize(self, iface: ModuleInterface, spec: str) -> PropertySet: ...
    def classify_cex(self, prop: Property, trace: Trace, iface: ModuleInterface) -> CexDiagnosis: ...
```
Model: `claude-opus-4-8`, `thinking={"type":"adaptive"}`, `output_config={"effort":"high"}`, `messages.parse(output_format=...)`. No assistant prefill (rejected on 4.8) — structure comes from the schema.

### 6.3 Discharge (`pipeline/discharge.py` + `adapters/sby.py`)

Builds a `.sby` job, runs SymbiYosys, parses status, collects traces. One job, three task modes per the bounding policy:

```ini
[options]
mode prove          ; k-induction (also: bmc, cover)
depth 20

[engines]
smtbmc bitwuzla     ; default SMT engine
; abc pdr           ; unbounded IC3/PDR escalation (separate task)

[script]
read -formal fifo.v
read -formal _build/fifo_fv.sv
prep -top fifo_fv

[files]
fifo.v
_build/fifo_fv.sv
```

```python
class SbyAdapter(Protocol):
    def run(self, job: SbyJob) -> list[PropertyResult]:
        """Parses PASS/FAIL + UNKNOWN, depth reached, and writes .yw + .vcd on failure."""
```

The adapter maps SymbiYosys outcomes onto the §4.4 taxonomy: `cover` reachable + `prove`/`pdr` PASS → `PROVEN`; `bmc` PASS only → `BOUNDED_PASS`; FAIL → `FALSIFIED` (+ traces); `cover` UNREACHABLE on a passing assert → `VACUOUS`; UNKNOWN/timeout → `INCONCLUSIVE`.

> **Two backends (see ADR-0003).** `discharge` is backend-agnostic (it drives a `SbyJobRunner`). Backend 1 is the spec'd **SymbiYosys + Bitwuzla** (`adapters/sby.py`, OSS CAD Suite). Backend 2 is **`adapters/yosys_sat.py`** — Yosys's built-in `sat` command (internal minisat), which runs BMC + k-induction with **no external solver and no SymbiYosys**, so the full proof-or-counterexample flow works anywhere Yosys is available (incl. Windows via `pip install yowasp-yosys`). Trade-off: yosys-sat doesn't run `cover`, so its verdicts carry no vacuity guard (`cover_reachable` stays `None`). Select with `--backend {auto,sby,yosys-sat}`.

### 6.4 Counterexample loop (`pipeline/refine.py` + `adapters/witness.py`)

Parse the `.yw` witness (Yosys `ywio`) into a structured per-cycle `Trace`; the LLM narrates it cycle-by-cycle and returns a `CexDiagnosis` classifying the cause and proposing a patch. The **policy layer decides whether to apply it** — and refuses patches that would weaken a property into vacuity.

```python
@dataclass(frozen=True)
class Trace:
    signals: tuple[str, ...]
    cycles: tuple[dict[str, int], ...]      # cycle → {signal: value}
    failing_cycle: int

class CexCause(StrEnum):
    RTL_BUG = "rtl_bug"                 # design violates a correct property → report, stop
    OVER_STRONG = "over_strong"         # property too strict → refine (guarded)
    MISSING_ASSUMPTION = "missing_assumption"   # need env constraint → add assume (guarded)

@dataclass(frozen=True)
class CexDiagnosis:
    cause: CexCause
    narration: str
    proposed_patch: Property | None
```

**Termination guarantee:** at most `--max-refine` rounds (default **5**); each round must change the property set; an RTL_BUG verdict is terminal (Toroid does not edit the DUT). **Anti-vacuity:** after any property/assumption refinement, the companion COVER must still be reachable, or the patch is rejected as cheating and the round is recorded as such.

### 6.5 Report (`pipeline/report.py`)

Aggregates `PropertyResult[]` into Markdown + JSON: a verdict table (property, verdict, engine, depth, time), embedded narration + waveform link for falsified properties, and an explicit vacuity column. The Markdown is the demo screenshot; the JSON feeds the benchmark scripts.

### 6.6 CLI (`cli.py`)

```
toroid verify <rtl...> --spec <md> --top <name> [--depth 20] [--max-refine 5]
                         [--engine bitwuzla|abc-pdr|z3] [--no-llm] [--report out.md]
toroid extract <rtl...> --top <name>          # just the interface model (debug)
```
`--no-llm` runs with a hand-written property file — the M0 path and the deterministic test path.

---

## 7. Milestones

Top-down, each independently runnable; counts are budgets, not promises.

- **M0 — Walking skeleton & it runs.** `toroid verify designs/counter.v --top counter --no-llm` wires ingest → render (a *hand-written* property) → sby → verdict → report end-to-end on a real module. Proves the harness + verdict parsing + `.yw`/VCD collection on real RTL. *Demonstrates:* the airtight ground-truth pipeline, no LLM yet.

- **M1 — Property synthesis (credibility milestone).** LLM generates a `PropertySet` from the interface model + spec; compile gate + repair loop; discharge; report PROVEN / BOUNDED-PASS / FALSIFIED with vacuity checks. *Demonstrates:* the differentiating claim — AI writes properties a solver then judges. **First public-ship point.**

- **M2 — Counterexample loop.** `.yw` narration → classify (RTL-bug / over-strong / missing-assumption) → guarded refine → re-run until stable, with termination + anti-vacuity guarantees. *Demonstrates:* the full HV inner loop, closed.

- **M3 — Demo gallery + benchmarks.** Buggy-FIFO catch (off-by-one full/empty) with narrated waveform, clean-module invariant proofs, and matplotlib charts (proof-depth-vs-time, bug-catch rate). *Demonstrates:* the one-screenshot value story. **Headline public ship.**

- **M4 (stretch) — Equivalence + protocols.** RTL-to-RTL equivalence (miter + Yosys `equiv`/`miter`) — the hardware sibling of software equivalence checking — and an AXI-lite handshake property suite. *Demonstrates:* depth beyond invariants.

---

## 8. Risks / open questions

- **LLM emits assertions the open frontend can't parse.** → Compile gate before any solver run; hard-constrain to the §4.1 subset with few-shot; structured output; bounded repair loop. This is the single highest-frequency failure mode — design assumes it and recovers.
- **Vacuous passes reported as PROVEN.** → Mandatory COVER per ASSERT; `VACUOUS` verdict; anti-vacuity re-check after every refinement. The honesty of the whole tool depends on this.
- **k-induction doesn't converge on loops without strengthening.** → Escalate to `abc pdr` (IC3); if neither closes it within timeout, report `BOUNDED_PASS` honestly. Never claim unbounded without an unbounded engine succeeding.
- **Solver nondeterminism / timeouts.** → Per-engine wall-clock caps, `INCONCLUSIVE` verdict, fixed depth defaults; integration tests assert verdicts, not timings.
- **Refinement loops forever or "cheats."** → Hard `--max-refine` cap, monotonic-change requirement, anti-vacuity gate, RTL_BUG as terminal.
- **Windows-native toolchain friction.** → Target WSL2 + OSS CAD Suite; CI on Linux via `setup-oss-cad-suite`. Native-Windows is a fallback, not supported.
- **LLM cost/latency in the loop.** → Cache the interface model + prompt prefix; cap refinement rounds; structured outputs keep round-trips minimal.
- **Open question:** default BMC depth (20) and `--max-refine` (5) are starting points — tune against the M3 benchmark suite once real designs are in hand.
- **Open question:** `bind`-based assertion attachment vs. the generated `*_fv` wrapper — wrapper is the v1 default for portability; revisit `bind` if Verific is ever adopted.

---

## 9. References

- **SymbiYosys docs** — flows, `.sby` reference, install. https://symbiyosys.readthedocs.io/ *(verified 2026-06-28; free OSS frontend supports immediate assertions only; full SVA needs Tabby CAD / Verific)*
- **Yosys docs** — `read_verilog -formal`, formal system functions (`$past`/`$anyconst`/…), `write_json` port/width export. https://yosyshq.readthedocs.io/projects/yosys/ *(verified 2026-06-28)*
- **OSS CAD Suite** — bundled Yosys + sby + Bitwuzla + ABC. https://github.com/YosysHQ/oss-cad-suite-build *(verified 2026-06-28)*
- **setup-oss-cad-suite** — CI action (`@v4`). https://github.com/YosysHQ/setup-oss-cad-suite *(verified 2026-06-28)*
- **Bitwuzla** (MIT) — bit-vector/array SMT solver, Boolector successor, SMT-COMP winner. https://bitwuzla.github.io/ *(verified 2026-06-28)*
- **Yosys `smtbmc.py` / `ywio`** — witness `.yw` read/write classes for trace parsing. https://github.com/YosysHQ/yosys/blob/main/backends/smt2/smtbmc.py *(verified 2026-06-28)*
- **Anthropic API docs** — `claude-opus-4-8`, adaptive thinking, structured outputs via `messages.parse()`. *(consulted 2026-06-28)*
- **Reuse / portfolio spine:** pairs with **Congruent** (software equivalence checking) as the formal-methods-meets-AI pair — *AI that proves correctness*, in software and in silicon. Share the report/verdict-model shape and CEX-narration patterns between the two.
