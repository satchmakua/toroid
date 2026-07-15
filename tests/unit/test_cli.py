"""The CLI must run offline: `version` and `demo` work with no toolchain, and
`verify` degrades gracefully (exit code 2 + guidance) when yosys/sby are absent.
"""

from __future__ import annotations

import pytest

from toroid import __version__
from toroid.cli import main


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0
    assert __version__ in capsys.readouterr().out


def test_demo_runs_offline_and_renders_wrapper_and_report(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "module counter_fv (input clk);" in out  # the rendered wrapper
    assert "Toroid report" in out  # the sample report
    assert "$anyseq" in out


def test_verify_llm_path_without_api_key_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    # The LLM path (no --no-llm) needs ANTHROPIC_API_KEY; without it (or without any
    # Yosys), verify must exit 2 with useful guidance rather than crashing.
    import os

    if os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("API key present; the missing-key path is not exercised here")
    rc = main(["verify", "designs/counter.v", "--top", "counter"])
    err = capsys.readouterr().err.lower()
    assert rc == 2
    assert "anthropic_api_key" in err or "yosys" in err
