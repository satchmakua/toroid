"""The CLI must run offline: `version` and `demo` work with no toolchain, and
`verify` degrades gracefully (exit code 2 + guidance) when yosys/sby are absent.
"""

from __future__ import annotations

import pytest

from inductor import __version__
from inductor.cli import main


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0
    assert __version__ in capsys.readouterr().out


def test_demo_runs_offline_and_renders_wrapper_and_report(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "module counter_fv (input clk);" in out  # the rendered wrapper
    assert "Inductor report" in out  # the sample report
    assert "$anyseq" in out


def test_verify_without_no_llm_flag_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    # Without --no-llm (and with no LLM backend yet), verify refuses with exit 2.
    # If no Yosys is found at all, it also exits 2 (with install guidance) — either
    # way the command must not crash and must point the user somewhere useful.
    rc = main(["verify", "designs/counter.v", "--top", "counter"])
    err = capsys.readouterr().err.lower()
    assert rc == 2
    assert "m2" in err or "yosys" in err
