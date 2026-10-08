from __future__ import annotations

import json

import numpy as np
import pytest

from w_mwxt_wavetable_tool.analysis import (
    SignalExtensionAnalysis,
    analyze_signal,
    analyze_signal_extensions,
)


def source_signal() -> tuple[np.ndarray, int]:
    sample_rate = 16000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    samples = 0.4 * np.sin(2.0 * np.pi * 220.0 * time)
    return samples, sample_rate


def test_extension_links_every_component_to_one_base_signal() -> None:
    samples, sample_rate = source_signal()
    base = analyze_signal(samples, sample_rate)
    extension = analyze_signal_extensions(
        samples,
        sample_rate,
        signal_analysis=base,
    )
    assert extension.signal_analysis_sha256 == base.analysis_sha256
    assert (
        extension.pitch_periodicity_analysis_sha256
        == base.pitch_periodicity_analysis.analysis_sha256
    )
    assert extension.sample_sha256 == base.sample_sha256
    assert len(extension.component_analysis_sha256) == 4
    json.dumps(extension.to_dict(), allow_nan=False, sort_keys=True)


def test_extension_is_deterministic() -> None:
    samples, sample_rate = source_signal()
    base = analyze_signal(samples, sample_rate)
    first = analyze_signal_extensions(samples, sample_rate, signal_analysis=base)
    second = analyze_signal_extensions(samples, sample_rate, signal_analysis=base)
    assert first.analysis_sha256 == second.analysis_sha256
    assert first.to_dict() == second.to_dict()


def test_extension_rejects_a_different_sample_identity() -> None:
    samples, sample_rate = source_signal()
    base = analyze_signal(samples, sample_rate)
    changed = samples.copy()
    changed[0] = 0.125
    with pytest.raises(ValueError, match="sample hash"):
        analyze_signal_extensions(changed, sample_rate, signal_analysis=base)


def test_direct_extension_rejects_wrong_pitch_link() -> None:
    samples, sample_rate = source_signal()
    base = analyze_signal(samples, sample_rate)
    extension = analyze_signal_extensions(samples, sample_rate, signal_analysis=base)
    payload = {
        name: getattr(extension, name)
        for name in extension.__dataclass_fields__
    }
    payload["pitch_periodicity_analysis_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="does not link"):
        SignalExtensionAnalysis(**payload)
