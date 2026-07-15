"""Parsing Yosys `write_json` output into the interface model, plus the clock/
reset detection heuristics. Pure — no toolchain needed.
"""

from __future__ import annotations

import pytest

from toroid.adapters.yosys import parse_write_json

# A trimmed but faithful `write_json` payload for designs/counter.v (post-`proc`).
COUNTER_JSON = {
    "creator": "Yosys (test fixture)",
    "modules": {
        "counter": {
            "attributes": {"top": 1},
            "ports": {
                "clk": {"direction": "input", "bits": [2]},
                "rst": {"direction": "input", "bits": [3]},
                "en": {"direction": "input", "bits": [4]},
                "count": {"direction": "output", "bits": [5, 6, 7, 8]},
            },
        }
    },
}


def test_ports_widths_and_directions() -> None:
    iface = parse_write_json(COUNTER_JSON, "counter")
    assert iface.top == "counter"
    assert iface.port("count").width == 4
    assert iface.port("count").direction == "output"
    assert iface.port("en").width == 1
    assert {p.name for p in iface.inputs()} == {"clk", "rst", "en"}


def test_clock_and_reset_detected_active_high() -> None:
    iface = parse_write_json(COUNTER_JSON, "counter")
    assert iface.clock == "clk"
    assert iface.reset == "rst"
    assert iface.reset_active_high is True
    assert iface.port("clk").is_clock
    assert iface.port("rst").is_reset
    # driven_inputs excludes the clock (the harness toggles it).
    assert "clk" not in {p.name for p in iface.driven_inputs()}


def test_active_low_reset_name() -> None:
    data = {
        "modules": {
            "m": {
                "ports": {
                    "clk": {"direction": "input", "bits": [2]},
                    "rst_n": {"direction": "input", "bits": [3]},
                }
            }
        }
    }
    iface = parse_write_json(data, "m")
    assert iface.reset == "rst_n"
    assert iface.reset_active_high is False


def test_missing_top_raises() -> None:
    with pytest.raises(KeyError, match="nope"):
        parse_write_json(COUNTER_JSON, "nope")
