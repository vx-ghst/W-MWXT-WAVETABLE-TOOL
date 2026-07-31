
from w_mwxt_wavetable_tool import (
    PhaseContinuityClass,
    PhaseFrameAnalysis,
    PhaseMotionAnalysis,
    PhaseTransitionAnalysis,
    PitchMotionClass,
    analyze_audio_source_phase_motion,
    analyze_phase_motion,
)


def test_code_v4c_public_api_is_available() -> None:
    assert PhaseContinuityClass.STABLE.value == "stable"
    assert PitchMotionClass.GLIDE_UP.value == "glide_up"
    assert PhaseFrameAnalysis.__name__ == "PhaseFrameAnalysis"
    assert PhaseTransitionAnalysis.__name__ == "PhaseTransitionAnalysis"
    assert PhaseMotionAnalysis.__name__ == "PhaseMotionAnalysis"
    assert callable(analyze_phase_motion)
    assert callable(analyze_audio_source_phase_motion)
