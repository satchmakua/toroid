"""The structured-output schema ↔ domain conversion and the interface renderer.
Pure — exercises no network (the `anthropic` client is never constructed).
"""

from __future__ import annotations

from toroid.adapters.llm import (
    CexCause,
    _CexOut,
    _diag_to_domain,
    _PatchOut,
    _PropertyOut,
    _PropertySetOut,
    _to_domain,
    render_interface,
)
from toroid.domain.interface import ModuleInterface, Port
from toroid.domain.properties import PropertyKind


def test_schema_converts_to_domain_property_set() -> None:
    out = _PropertySetOut(
        properties=[
            _PropertyOut(pid="P1", kind="assert", summary="no overflow", expr="count <= 4'd15"),
            _PropertyOut(pid="P2", kind="cover", summary="reaches max", expr="count == 4'd15"),
        ]
    )
    pset = _to_domain(out)
    assert [p.pid for p in pset.properties] == ["P1", "P2"]
    assert pset.asserts()[0].kind is PropertyKind.ASSERT
    assert pset.covers()[0].pid == "P2"
    assert all(p.origin == "llm" for p in pset.properties)  # provenance tagged
    assert pset.has_reachability_witness()


def test_render_interface_lists_ports_clock_reset() -> None:
    iface = ModuleInterface(
        top="counter",
        ports=(
            Port("clk", "input", 1, is_clock=True),
            Port("rst", "input", 1, is_reset=True),
            Port("count", "output", 4),
        ),
        clock="clk",
        reset="rst",
        reset_active_high=False,
    )
    text = render_interface(iface)
    assert "Module: counter" in text
    assert "clock: clk" in text
    assert "active-low" in text
    assert "output [4] count" in text


def test_cex_diagnosis_with_patch_converts_to_domain() -> None:
    out = _CexOut(
        cause="over_strong",
        narration="count climbs past 10 under normal counting",
        patch=_PatchOut(pid="PB", kind="assert", summary="fixed", expr="count <= 4'd15"),
    )
    diag = _diag_to_domain(out)
    assert diag.cause is CexCause.OVER_STRONG
    assert diag.proposed_patch is not None
    assert diag.proposed_patch.kind is PropertyKind.ASSERT
    assert diag.proposed_patch.origin == "refined"


def test_rtl_bug_diagnosis_has_no_patch() -> None:
    diag = _diag_to_domain(_CexOut(cause="rtl_bug", narration="genuine bug", patch=None))
    assert diag.cause is CexCause.RTL_BUG
    assert diag.proposed_patch is None
