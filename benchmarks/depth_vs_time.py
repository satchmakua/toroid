"""Proof-depth-vs-time benchmark: discharge a property at increasing BMC depths and
measure wall time. Shows how bounded proof cost scales with depth. Emits a CSV and
(if matplotlib is installed) a chart.

    python -m benchmarks.depth_vs_time      # needs a Yosys (pip install yowasp-yosys)
"""

from __future__ import annotations

import time
from pathlib import Path

from toroid.adapters.sby import SbyJob
from toroid.adapters.yosys import YosysCli, find_yosys
from toroid.adapters.yosys_sat import YosysSatCli
from toroid.domain.properties import Property, PropertyKind, PropertySet
from toroid.render.checker import render_wrapper

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "benchmarks" / "out"
DEPTHS = [2, 5, 10, 15, 20, 30, 40]


def measure() -> list[tuple[int, float]]:
    exe = find_yosys()
    if exe is None:
        raise SystemExit("No Yosys found. `pip install yowasp-yosys` or install the OSS CAD Suite.")
    yosys = YosysCli(executable=exe)
    runner = YosysSatCli(executable=exe)
    dut = REPO / "designs" / "counter.v"
    iface = yosys.extract_interface([dut], "counter")
    # A true bounded property: count stays within its 4-bit range.
    prop = Property("D1", PropertyKind.ASSERT, "in range", "count <= 4'd15")
    workdir = OUT / "work" / "depth"
    workdir.mkdir(parents=True, exist_ok=True)
    wrapper = workdir / "counter_fv.sv"
    wrapper.write_text(render_wrapper(iface, PropertySet((prop,))), encoding="utf-8")

    rows: list[tuple[int, float]] = []
    for depth in DEPTHS:
        job = SbyJob(
            name=f"d{depth}", workdir=workdir / f"d{depth}",
            script_files=(dut.name, wrapper.name), file_paths=(dut, wrapper),
            top="counter_fv", mode="bmc", depth=depth, engine="yosys-sat",
        )
        t0 = time.monotonic()
        runner.run_job(job)
        rows.append((depth, time.monotonic() - t0))
    return rows


def plot(rows: list[tuple[int, float]], path: Path) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    xs = [d for d, _ in rows]
    ys = [t for _, t in rows]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(xs, ys, marker="o", color="#1565c0")
    ax.set_xlabel("BMC depth (cycles)")
    ax.set_ylabel("wall time (s)")
    ax.set_title("Toroid — bounded proof time vs depth (counter, yosys-sat)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    return True


def main() -> None:
    rows = measure()
    OUT.mkdir(parents=True, exist_ok=True)
    csv = "depth,seconds\n" + "\n".join(f"{d},{t:.3f}" for d, t in rows) + "\n"
    print(csv)
    (OUT / "depth_vs_time.csv").write_text(csv, encoding="utf-8")
    chart = OUT / "depth_vs_time.png"
    if plot(rows, chart):
        print(f"chart: {chart}")
    else:
        print("(install matplotlib for the chart: pip install -e '.[bench]')")


if __name__ == "__main__":
    main()
