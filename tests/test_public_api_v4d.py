
from w_mwxt_wavetable_tool import (
    ChangePointEvent,
    NoiseAnalysis,
    NoiseClass,
    NoiseFrameAnalysis,
    TransientChangeAnalysis,
    TransientChangeClass,
    TransientEvent,
    TransientFrameAnalysis,
    analyze_audio_source_noise,
    analyze_audio_source_transients,
    analyze_noise,
    analyze_transients,
)


def test_code_v4d_public_api_is_available() -> None:
    assert NoiseClass.SIGNAL_DOMINATED.value == "signal_dominated"
    assert TransientChangeClass.STEADY.value == "steady"
    assert NoiseAnalysis.__name__ == "NoiseAnalysis"
    assert NoiseFrameAnalysis.__name__ == "NoiseFrameAnalysis"
    assert TransientChangeAnalysis.__name__ == "TransientChangeAnalysis"
    assert TransientFrameAnalysis.__name__ == "TransientFrameAnalysis"
    assert TransientEvent.__name__ == "TransientEvent"
    assert ChangePointEvent.__name__ == "ChangePointEvent"
    assert callable(analyze_noise)
    assert callable(analyze_audio_source_noise)
    assert callable(analyze_transients)
    assert callable(analyze_audio_source_transients)
