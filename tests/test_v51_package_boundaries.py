from __future__ import annotations

from pathlib import Path
import inspect

from w_mwxt_wavetable_tool.validation_v51 import core


def test_v51_validation_module_does_not_open_midi() -> None:
    source = inspect.getsource(core).lower()
    forbidden = ("mido.open_output", "rtmidi", "midiout", "send_message(")
    assert not any(token in source for token in forbidden)


def test_v51_product_and_diagnostic_contracts_are_distinguished() -> None:
    source = inspect.getsource(core)
    assert "product_contract" in source
    assert "N WAVD + 1 WCTD" in source
    assert "diagnostic_carrier" in source
    assert "v9_claim" in source
