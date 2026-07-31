
from __future__ import annotations

from hashlib import sha256
import math

import numpy as np
import numpy.typing as npt

from .framing import validate_mono_samples
from .models import (
    PhaseContinuityClass,
    PhaseFrameAnalysis,
    PhaseMotionAnalysis,
    PhaseTransitionAnalysis,
    PitchMotionClass,
    PitchPeriodicityAnalysis,
)
from .periodicity import analyze_pitch_periodicity
from ..audio import AudioSource
from ..errors import AnalysisError


def _sample_sha256(samples: npt.NDArray[np.float64]) -> str:
    canonical = samples.astype("<f8", copy=False).tobytes(order="C")
    return sha256(canonical).hexdigest()


def _wrap_phase(value: float) -> float:
    wrapped = (float(value) + math.pi) % (2.0 * math.pi) - math.pi
    if wrapped == -math.pi and value > 0.0:
        return math.pi
    return float(wrapped)


def _estimate_center_phase(
    frame: npt.NDArray[np.float64],
    sample_rate: int,
    frequency_hz: float,
) -> tuple[float, float]:
    centered = frame - float(np.mean(frame, dtype=np.float64))
    if centered.size == 1:
        return 0.0, 0.0
    window = np.hanning(centered.size).astype(np.float64, copy=False)
    weighted = centered * window
    energy = float(np.dot(weighted, weighted))
    if energy <= 1e-24:
        return 0.0, 0.0
    indices = np.arange(centered.size, dtype=np.float64)
    angular_frequency = 2.0 * math.pi * frequency_hz / sample_rate
    basis = np.exp(-1j * angular_frequency * indices)
    coefficient = np.dot(weighted, basis)
    center_index = (centered.size - 1) / 2.0
    phase = _wrap_phase(float(np.angle(coefficient) + math.pi / 2.0 + angular_frequency * center_index))
    basis_energy = float(np.dot(window, window))
    strength = float(
        np.clip(
            math.sqrt(2.0) * abs(coefficient) / math.sqrt(energy * basis_energy),
            0.0,
            1.0,
        )
    )
    return phase, strength


def _phase_classification(
    *,
    transition_count: int,
    discontinuity_ratio: float,
    median_error_degrees: float | None,
    p95_error_degrees: float | None,
    threshold_degrees: float,
) -> tuple[PhaseContinuityClass, str]:
    if transition_count == 0:
        return (
            PhaseContinuityClass.UNAVAILABLE,
            "Fewer than two consecutive voiced frames were available for phase comparison.",
        )
    assert median_error_degrees is not None
    assert p95_error_degrees is not None
    if discontinuity_ratio == 0.0 and median_error_degrees <= min(15.0, threshold_degrees / 2.0):
        return (
            PhaseContinuityClass.STABLE,
            "Consecutive voiced frames preserve phase with low median error and no threshold discontinuity.",
        )
    if discontinuity_ratio == 0.0 and p95_error_degrees <= threshold_degrees:
        return (
            PhaseContinuityClass.VARIABLE,
            "Phase varies across voiced frames but remains below the configured discontinuity threshold.",
        )
    return (
        PhaseContinuityClass.DISCONTINUOUS,
        "One or more phase transitions exceed the configured discontinuity threshold at a material rate.",
    )


def _pitch_motion_classification(
    *,
    voiced_frame_count: int,
    pitch_transition_count: int,
    excursion_cents: float | None,
    median_step_cents: float | None,
    maximum_step_cents: float | None,
    slope_cents_per_second: float | None,
    direction_consistency: float,
    reversal_count: int,
    reversal_rate: float,
    stable_threshold_cents: float,
    glide_slope_threshold: float,
    stepped_threshold_cents: float,
) -> tuple[PitchMotionClass, str]:
    if voiced_frame_count == 0:
        return PitchMotionClass.UNVOICED, "No voiced pitch frames were available."
    if pitch_transition_count == 0:
        return (
            PitchMotionClass.INSUFFICIENT,
            "Only one voiced frame or no consecutive voiced transition was available.",
        )
    assert excursion_cents is not None
    assert median_step_cents is not None
    assert maximum_step_cents is not None
    assert slope_cents_per_second is not None
    if excursion_cents <= stable_threshold_cents:
        return (
            PitchMotionClass.STABLE,
            "The voiced pitch excursion remains within the configured stable range.",
        )
    if (
        abs(slope_cents_per_second) >= glide_slope_threshold
        and direction_consistency >= 0.75
    ):
        if slope_cents_per_second > 0.0:
            return (
                PitchMotionClass.GLIDE_UP,
                "Pitch rises with a sustained slope and predominantly positive frame-to-frame motion.",
            )
        return (
            PitchMotionClass.GLIDE_DOWN,
            "Pitch falls with a sustained slope and predominantly negative frame-to-frame motion.",
        )
    if maximum_step_cents >= stepped_threshold_cents and median_step_cents <= stepped_threshold_cents / 3.0:
        return (
            PitchMotionClass.STEPPED,
            "Pitch is mostly locally stable but includes at least one large discrete step.",
        )
    if (
        reversal_count >= 4
        and direction_consistency <= 0.70
        and excursion_cents <= 250.0
        and abs(slope_cents_per_second) < glide_slope_threshold
    ):
        return (
            PitchMotionClass.VIBRATO,
            "Pitch repeatedly reverses direction within a bounded excursion.",
        )
    return (
        PitchMotionClass.IRREGULAR,
        "Pitch motion is voiced but does not match the stable, glide, vibrato, or stepped criteria.",
    )


def analyze_phase_motion(
    samples: npt.ArrayLike,
    sample_rate: int,
    *,
    pitch_periodicity: PitchPeriodicityAnalysis | None = None,
    frame_size: int = 4096,
    hop_size: int = 1024,
    minimum_frequency_hz: float = 40.0,
    maximum_frequency_hz: float = 2000.0,
    active_rms_threshold: float = 1e-6,
    confidence_threshold: float = 0.60,
    reference_a4_hz: float = 440.0,
    phase_discontinuity_threshold_degrees: float = 60.0,
    stable_pitch_threshold_cents: float = 15.0,
    glide_slope_threshold_cents_per_second: float = 25.0,
    stepped_pitch_threshold_cents: float = 100.0,
    pitch_deadband_cents: float = 1.0,
) -> PhaseMotionAnalysis:
    data = validate_mono_samples(samples)
    if sample_rate <= 0:
        raise AnalysisError("sample_rate must be positive")
    for name, value in (
        ("phase_discontinuity_threshold_degrees", phase_discontinuity_threshold_degrees),
        ("stable_pitch_threshold_cents", stable_pitch_threshold_cents),
        ("glide_slope_threshold_cents_per_second", glide_slope_threshold_cents_per_second),
        ("stepped_pitch_threshold_cents", stepped_pitch_threshold_cents),
    ):
        if not math.isfinite(value) or value <= 0.0:
            raise AnalysisError(f"{name} must be finite and positive")
    if phase_discontinuity_threshold_degrees > 180.0:
        raise AnalysisError("phase_discontinuity_threshold_degrees must not exceed 180")
    if not math.isfinite(pitch_deadband_cents) or pitch_deadband_cents < 0.0:
        raise AnalysisError("pitch_deadband_cents must be finite and non-negative")

    pitch = pitch_periodicity
    if pitch is None:
        pitch = analyze_pitch_periodicity(
            data,
            sample_rate,
            frame_size=frame_size,
            hop_size=hop_size,
            minimum_frequency_hz=minimum_frequency_hz,
            maximum_frequency_hz=maximum_frequency_hz,
            active_rms_threshold=active_rms_threshold,
            confidence_threshold=confidence_threshold,
            reference_a4_hz=reference_a4_hz,
        )
    if pitch.sample_rate != sample_rate or pitch.sample_count != data.size:
        raise AnalysisError("pitch_periodicity does not describe the supplied signal")
    if pitch.sample_sha256 != _sample_sha256(data):
        raise AnalysisError("pitch_periodicity sample fingerprint does not match")

    phase_frames: list[PhaseFrameAnalysis] = []
    for index, pitch_frame in enumerate(pitch.frames):
        phase: float | None = None
        strength = 0.0
        frequency = pitch_frame.frequency_hz
        if pitch_frame.voiced and frequency is not None:
            stop = min(pitch_frame.start_sample + pitch_frame.sample_count, data.size)
            frame = data[pitch_frame.start_sample:stop]
            phase, strength = _estimate_center_phase(frame, sample_rate, frequency)
        phase_frames.append(
            PhaseFrameAnalysis(
                frame_index=index,
                start_sample=pitch_frame.start_sample,
                center_seconds=pitch_frame.center_seconds,
                sample_count=pitch_frame.sample_count,
                voiced=pitch_frame.voiced,
                frequency_hz=frequency if pitch_frame.voiced else None,
                phase_radians=phase,
                projection_strength=strength,
            )
        )

    threshold_radians = math.radians(phase_discontinuity_threshold_degrees)
    phase_transitions: list[PhaseTransitionAnalysis] = []
    for left, right in zip(phase_frames, phase_frames[1:]):
        if not left.voiced or not right.voiced:
            continue
        assert left.phase_radians is not None and right.phase_radians is not None
        assert left.frequency_hz is not None and right.frequency_hz is not None
        delta_seconds = right.center_seconds - left.center_seconds
        if delta_seconds <= 0.0:
            continue
        mean_frequency = (left.frequency_hz + right.frequency_hz) / 2.0
        predicted_advance = 2.0 * math.pi * mean_frequency * delta_seconds
        observed_advance = right.phase_radians - left.phase_radians
        error = _wrap_phase(observed_advance - predicted_advance)
        phase_transitions.append(
            PhaseTransitionAnalysis(
                from_frame_index=left.frame_index,
                to_frame_index=right.frame_index,
                delta_seconds=delta_seconds,
                phase_error_radians=error,
                phase_error_degrees=math.degrees(error),
                discontinuity=abs(error) > threshold_radians,
            )
        )

    if phase_transitions:
        absolute_phase_errors = np.asarray(
            [abs(transition.phase_error_degrees) for transition in phase_transitions],
            dtype=np.float64,
        )
        median_phase_error = float(np.median(absolute_phase_errors))
        p95_phase_error = float(np.percentile(absolute_phase_errors, 95.0))
        maximum_phase_error = float(np.max(absolute_phase_errors))
        phase_stability = float(1.0 - min(1.0, median_phase_error / 180.0))
    else:
        median_phase_error = None
        p95_phase_error = None
        maximum_phase_error = None
        phase_stability = 0.0
    discontinuity_count = sum(transition.discontinuity for transition in phase_transitions)
    discontinuity_ratio = (
        0.0
        if not phase_transitions
        else float(discontinuity_count / len(phase_transitions))
    )
    phase_class, phase_reason = _phase_classification(
        transition_count=len(phase_transitions),
        discontinuity_ratio=discontinuity_ratio,
        median_error_degrees=median_phase_error,
        p95_error_degrees=p95_phase_error,
        threshold_degrees=phase_discontinuity_threshold_degrees,
    )

    voiced_frames = [frame for frame in phase_frames if frame.voiced]
    pitch_steps: list[float] = []
    pitch_step_times: list[float] = []
    for left, right in zip(phase_frames, phase_frames[1:]):
        if not left.voiced or not right.voiced:
            continue
        assert left.frequency_hz is not None and right.frequency_hz is not None
        cents_delta = 1200.0 * math.log2(right.frequency_hz / left.frequency_hz)
        pitch_steps.append(float(cents_delta))
        pitch_step_times.append(float(right.center_seconds - left.center_seconds))

    if voiced_frames:
        voiced_times = np.asarray(
            [frame.center_seconds for frame in voiced_frames], dtype=np.float64
        )
        voiced_cents = np.asarray(
            [1200.0 * math.log2(frame.frequency_hz / reference_a4_hz) for frame in voiced_frames],
            dtype=np.float64,
        )
        excursion = float(np.max(voiced_cents) - np.min(voiced_cents))
        if voiced_times.size >= 2 and float(np.ptp(voiced_times)) > 0.0:
            centered_times = voiced_times - float(np.mean(voiced_times))
            centered_cents = voiced_cents - float(np.mean(voiced_cents))
            denominator = float(np.dot(centered_times, centered_times))
            slope = 0.0 if denominator <= 0.0 else float(np.dot(centered_times, centered_cents) / denominator)
        else:
            slope = None
    else:
        excursion = None
        slope = None

    if pitch_steps:
        steps = np.asarray(pitch_steps, dtype=np.float64)
        absolute_steps = np.abs(steps)
        median_step = float(np.median(absolute_steps))
        maximum_step = float(np.max(absolute_steps))
        significant_signs = np.sign(steps[absolute_steps > pitch_deadband_cents])
        if significant_signs.size == 0:
            direction_consistency = 1.0
            reversal_count = 0
            reversal_rate = 0.0
        else:
            positive = int(np.count_nonzero(significant_signs > 0.0))
            negative = int(np.count_nonzero(significant_signs < 0.0))
            direction_consistency = float(max(positive, negative) / significant_signs.size)
            reversal_count = int(np.count_nonzero(significant_signs[1:] != significant_signs[:-1]))
            reversal_rate = (
                0.0
                if significant_signs.size < 2
                else float(reversal_count / (significant_signs.size - 1))
            )
    else:
        median_step = None
        maximum_step = None
        direction_consistency = 0.0
        reversal_count = 0
        reversal_rate = 0.0

    motion_class, motion_reason = _pitch_motion_classification(
        voiced_frame_count=len(voiced_frames),
        pitch_transition_count=len(pitch_steps),
        excursion_cents=excursion,
        median_step_cents=median_step,
        maximum_step_cents=maximum_step,
        slope_cents_per_second=slope,
        direction_consistency=direction_consistency,
        reversal_count=reversal_count,
        reversal_rate=reversal_rate,
        stable_threshold_cents=stable_pitch_threshold_cents,
        glide_slope_threshold=glide_slope_threshold_cents_per_second,
        stepped_threshold_cents=stepped_pitch_threshold_cents,
    )

    return PhaseMotionAnalysis(
        schema_version=1,
        sample_rate=int(sample_rate),
        sample_count=int(data.size),
        sample_sha256=_sample_sha256(data),
        frame_size=pitch.frame_size,
        hop_size=pitch.hop_size,
        phase_discontinuity_threshold_degrees=float(phase_discontinuity_threshold_degrees),
        stable_pitch_threshold_cents=float(stable_pitch_threshold_cents),
        glide_slope_threshold_cents_per_second=float(glide_slope_threshold_cents_per_second),
        stepped_pitch_threshold_cents=float(stepped_pitch_threshold_cents),
        frames=tuple(phase_frames),
        phase_transitions=tuple(phase_transitions),
        phase_frame_count=sum(frame.voiced for frame in phase_frames),
        phase_transition_count=len(phase_transitions),
        median_phase_error_degrees=median_phase_error,
        phase_error_p95_degrees=p95_phase_error,
        maximum_phase_error_degrees=maximum_phase_error,
        phase_stability=phase_stability,
        discontinuity_count=discontinuity_count,
        discontinuity_ratio=discontinuity_ratio,
        phase_continuity_class=phase_class,
        phase_classification_reason=phase_reason,
        pitch_transition_count=len(pitch_steps),
        pitch_excursion_cents=excursion,
        median_pitch_step_cents=median_step,
        maximum_pitch_step_cents=maximum_step,
        pitch_slope_cents_per_second=slope,
        direction_consistency=direction_consistency,
        reversal_count=reversal_count,
        reversal_rate=reversal_rate,
        pitch_motion_class=motion_class,
        pitch_motion_reason=motion_reason,
    )


def analyze_audio_source_phase_motion(
    source: AudioSource,
    *,
    pitch_periodicity: PitchPeriodicityAnalysis | None = None,
    **kwargs: float | int,
) -> PhaseMotionAnalysis:
    return analyze_phase_motion(
        source.mono_samples,
        source.metadata.sample_rate,
        pitch_periodicity=pitch_periodicity,
        **kwargs,
    )
