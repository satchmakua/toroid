"""The CLI must run offline: `version` and `demo` work with no toolchain, and
`verify` degrades gracefully (exit code 2 + guidance) when yosys/sby are absent.
"""

from __future__ import annotations

import pytest

from inductor import __version__
from inductor.adapters import toolchain_status
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


def test_verify_without_toolchain_exits_2_with_guidance(
    capsys: pytest.CaptureFixture[str],
) -> None:
    if toolchain_status().ready:
        pytest.skip("toolchain present; the missing-tool path is not exercised here")
    rc = main(["verify", "designs/counter.v", "--top", "counter"])
    assert rc == 2
    assert "oss-cad-suite" in capsys.readouterr().err.lower()
