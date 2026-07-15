"""Bug-catch benchmark: run the demo gallery through the yosys-sat backend and report
per-design verdicts — proving invariants on clean modules and catching the injected
FIFO off-by-one. Emits a Markdown summary and (if matplotlib is installed) a chart.

    python -m benchmarks.bugcatch          # needs a Yosys (pip install yowasp-yosys)
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from toroid.adapters.yosys import YosysCli, find_yosys
from toroid.adapters.yosys_sat import YosysSatCli
from toroid.domain.verdicts import PropertyResult, Verdict
from toroid.loaders import load_property_set
from toroid.pipeline.discharge import discharge

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "benchmarks" / "out"

# (label, rtl, top, props, expectation)
GALLERY = [
    ("counter", "designs/counter.v", "counter", "designs/counter.props.json", "all proven"),
    ("FIFO (clean)", "designs/fifo.v", "fifo", "designs/fifo.props.json", "all proven"),
    ("FIFO (buggy)", "designs/fifo_buggy.v", "fifo", "designs/fifo.props.json", "F1 falsified"),
]


def run_gallery() -> list[tuple[str, str, list[PropertyResult]]]:
    exe = find_yosys()
    if exe is None:
        raise SystemExit("No Yosys found. `pip install yowasp-yosys` or install the OSS CAD Suite.")
    rows = []
    for label, rtl, top, props, expect in GALLERY:
        yosys = YosysCli(executable=exe)
        dut = REPO / rtl
        iface = yosys.extract_interface([dut], top)
        pset = load_property_set(REPO / props)
        workdir = OUT / "work" / label.replace(" ", "_").replace("(", "").replace(")", "")
        results = discharge(
            iface, pset, duts=[dut], yosys=yosys, runner=YosysSatCli(executable=exe),
            workdir=workdir, depth=20, run_pdr=False,
        )
        rows.append((label, expect, results))
    return rows


def to_markdown(rows: list[tuple[str, str, list[PropertyResult]]]) -> str:
    lines = ["# Bug-catch benchmark", "", "| Design | Expectation | Verdicts |", "|---|---|---|"]
    for label, expect, results in rows:
        tally = Counter(r.verdict.value for r in results)
        verdicts = ", ".join(f"{n}×{v}" for v, n in sorted(tally.items()))
        lines.append(f"| {label} | {expect} | {verdicts} |")
    return "\n".join(lines) + "\n"


def plot(rows: list[tuple[str, str, list[PropertyResult]]], path: Path) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    labels = [r[0] for r in rows]
    proven = [sum(x.verdict is Verdict.PROVEN for x in r[2]) for r in rows]
    falsified = [sum(x.verdict is Verdict.FALSIFIED for x in r[2]) for r in rows]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(labels, proven, label="proven", color="#2e7d32")
    ax.bar(labels, falsified, bottom=proven, label="falsified", color="#c62828")
    ax.set_ylabel("properties")
    ax.set_title("Toroid — proven vs falsified per design")
    ax.legend()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    return True


def main() -> None:
    rows = run_gallery()
    md = to_markdown(rows)
    print(md)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "bugcatch.md").write_text(md, encoding="utf-8")
    chart = OUT / "bugcatch.png"
    if plot(rows, chart):
        print(f"chart: {chart}")
    else:
        print("(install matplotlib for the chart: pip install -e '.[bench]')")


if __name__ == "__main__":
    main()
