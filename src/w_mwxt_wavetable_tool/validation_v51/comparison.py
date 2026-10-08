from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import numpy.typing as npt
import soundfile as sf

from ..dump import DumpFile

CAPTURE_ANALYSIS_SCHEMA_VERSION = 1
_EPSILON = 1.0e-12


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return document


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _load_audio(path: Path, *, label: str) -> tuple[npt.NDArray[np.float64], int, dict[str, object]]:
    info = sf.info(str(path))
    if info.channels != 1:
        raise ValueError(f"{label} must be mono; got {info.channels} channels")
    if info.samplerate not in {48_000, 96_000}:
        raise ValueError(f"{label} must be 48 or 96 kHz; got {info.samplerate}")
    if info.subtype != "PCM_24":
        raise ValueError(f"{label} must be PCM_24; got {info.subtype}")
    samples, sample_rate = sf.read(str(path), dtype="float64", always_2d=False)
    array = np.asarray(samples, dtype=np.float64)
    if array.ndim != 1 or not np.all(np.isfinite(array)):
        raise ValueError(f"{label} contains invalid decoded samples")
    peak = float(np.max(np.abs(array))) if array.size else 0.0
    clipped = bool(np.count_nonzero(np.abs(array) >= 0.999969) > 0)
    metadata = {
        "path": str(path),
        "sha256": _file_hash(path),
        "sample_rate": int(sample_rate),
        "frames": int(array.size),
        "duration_seconds": float(array.size / sample_rate),
        "subtype": info.subtype,
        "peak": peak,
        "peak_dbfs": 20.0 * math.log10(max(peak, _EPSILON)),
        "clipped": clipped,
    }
    return array, int(sample_rate), metadata


def _load_source_audio(path: Path) -> tuple[npt.NDArray[np.float64], int, dict[str, object]]:
    info = sf.info(str(path))
    samples, sample_rate = sf.read(str(path), dtype="float64", always_2d=True)
    matrix = np.asarray(samples, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or not np.all(np.isfinite(matrix)):
        raise ValueError("campaign source contains invalid decoded samples")
    mono = np.mean(matrix, axis=1, dtype=np.float64)
    peak = float(np.max(np.abs(mono)))
    return mono, int(sample_rate), {
        "path": str(path),
        "sha256": _file_hash(path),
        "sample_rate": int(sample_rate),
        "channels_original": int(info.channels),
        "frames": int(mono.size),
        "duration_seconds": float(mono.size / sample_rate),
        "subtype": info.subtype,
        "peak": peak,
    }


def _resample_curve(curve: npt.NDArray[np.float64], count: int = 128) -> npt.NDArray[np.float64]:
    if curve.size == 0:
        return np.zeros(count, dtype=np.float64)
    if curve.size == 1:
        return np.full(count, float(curve[0]), dtype=np.float64)
    source = np.linspace(0.0, 1.0, curve.size, dtype=np.float64)
    target = np.linspace(0.0, 1.0, count, dtype=np.float64)
    return np.interp(target, source, curve).astype(np.float64)


def _resample_linear(samples: npt.NDArray[np.float64], source_rate: int, target_rate: int) -> npt.NDArray[np.float64]:
    if source_rate == target_rate:
        return samples.copy()
    source_positions = np.arange(samples.size, dtype=np.float64) / source_rate
    target_count = int(round(samples.size * target_rate / source_rate))
    target_positions = np.arange(target_count, dtype=np.float64) / target_rate
    return np.interp(target_positions, source_positions, samples).astype(np.float64)


def _envelope(samples: npt.NDArray[np.float64], sample_rate: int, rate: int = 200) -> npt.NDArray[np.float64]:
    block = max(1, sample_rate // rate)
    count = samples.size // block
    if count <= 0:
        return np.zeros(0, dtype=np.float64)
    trimmed = samples[: count * block].reshape(count, block)
    return np.sqrt(np.mean(np.square(trimmed), axis=1, dtype=np.float64))


def _alignment_lag_seconds(
    expected: npt.NDArray[np.float64],
    capture: npt.NDArray[np.float64],
    sample_rate: int,
    *,
    maximum_lag_seconds: float = 3.0,
) -> float:
    expected_env = _envelope(expected, sample_rate)
    capture_env = _envelope(capture, sample_rate)
    length = min(expected_env.size, capture_env.size)
    if length < 10:
        return 0.0
    expected_env = expected_env[:length] - float(np.mean(expected_env[:length]))
    capture_env = capture_env[:length] - float(np.mean(capture_env[:length]))
    scale = float(np.linalg.norm(expected_env) * np.linalg.norm(capture_env))
    if scale <= _EPSILON:
        return 0.0
    max_lag = min(int(round(maximum_lag_seconds * 200)), length - 1)
    best_lag = 0
    best_score = -float("inf")
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            left = expected_env[: length - lag]
            right = capture_env[lag:length]
        else:
            left = expected_env[-lag:length]
            right = capture_env[: length + lag]
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        score = -1.0 if denominator <= _EPSILON else float(np.dot(left, right) / denominator)
        if score > best_score:
            best_score = score
            best_lag = lag
    return best_lag / 200.0


def _slice_with_lag(
    samples: npt.NDArray[np.float64],
    sample_rate: int,
    start_seconds: float,
    end_seconds: float,
    lag_seconds: float,
) -> npt.NDArray[np.float64]:
    start = int(round((start_seconds + lag_seconds) * sample_rate))
    end = int(round((end_seconds + lag_seconds) * sample_rate))
    start = max(0, start)
    end = min(samples.size, end)
    if end <= start:
        return np.zeros(0, dtype=np.float64)
    return np.asarray(samples[start:end], dtype=np.float64)


def _estimate_pitch(segment: npt.NDArray[np.float64], sample_rate: int, expected_hz: float) -> float:
    if segment.size < 128:
        return 0.0
    centered = segment - float(np.mean(segment))
    maximum = float(np.max(np.abs(centered)))
    if maximum <= _EPSILON:
        return 0.0
    centered = centered / maximum
    minimum_lag = max(2, int(sample_rate / (expected_hz * 1.08)))
    maximum_lag = min(centered.size // 2, int(sample_rate / (expected_hz * 0.92)))
    if maximum_lag <= minimum_lag:
        return 0.0
    correlations = np.asarray(
        [float(np.dot(centered[:-lag], centered[lag:])) for lag in range(minimum_lag, maximum_lag + 1)],
        dtype=np.float64,
    )
    index = int(np.argmax(correlations))
    lag = float(minimum_lag + index)
    if 0 < index < correlations.size - 1:
        left, middle, right = correlations[index - 1 : index + 2]
        denominator = left - 2.0 * middle + right
        if abs(denominator) > _EPSILON:
            lag += 0.5 * (left - right) / denominator
    return sample_rate / lag


def _harmonic_coefficients(
    segment: npt.NDArray[np.float64],
    sample_rate: int,
    fundamental_hz: float,
    *,
    maximum_harmonics: int = 24,
) -> npt.NDArray[np.complex128]:
    if segment.size < 64 or fundamental_hz <= 0.0:
        return np.zeros(maximum_harmonics, dtype=np.complex128)
    centered = segment - float(np.mean(segment))
    window = np.hanning(centered.size)
    weighted = centered * window
    time = np.arange(centered.size, dtype=np.float64) / sample_rate
    coefficients = np.zeros(maximum_harmonics, dtype=np.complex128)
    for harmonic in range(1, maximum_harmonics + 1):
        frequency = harmonic * fundamental_hz
        if frequency >= 0.46 * sample_rate:
            break
        oscillator = np.exp(-2j * math.pi * frequency * time)
        coefficients[harmonic - 1] = np.dot(weighted, oscillator)
    return coefficients


def _harmonic_metrics(
    expected: npt.NDArray[np.float64],
    capture: npt.NDArray[np.float64],
    sample_rate: int,
    fundamental_hz: float,
) -> dict[str, float]:
    expected_coeff = _harmonic_coefficients(expected, sample_rate, fundamental_hz)
    capture_coeff = _harmonic_coefficients(capture, sample_rate, fundamental_hz)
    expected_mag = np.abs(expected_coeff)
    capture_mag = np.abs(capture_coeff)
    expected_mag /= max(float(np.linalg.norm(expected_mag)), _EPSILON)
    capture_mag /= max(float(np.linalg.norm(capture_mag)), _EPSILON)
    magnitude_similarity = float(np.clip(np.dot(expected_mag, capture_mag), 0.0, 1.0))

    # Remove one global time shift from both complex harmonic vectors. A time shift
    # rotates harmonic h by h times the fundamental phase; the remaining phase is
    # the relative waveform phase that the V4.5 magnitude-only method discarded.
    def relative(coefficients: npt.NDArray[np.complex128]) -> npt.NDArray[np.complex128]:
        if abs(coefficients[0]) <= _EPSILON:
            return np.zeros_like(coefficients)
        base_phase = float(np.angle(coefficients[0]))
        harmonic_index = np.arange(1, coefficients.size + 1, dtype=np.float64)
        adjusted = coefficients * np.exp(-1j * harmonic_index * base_phase)
        norm = float(np.linalg.norm(adjusted))
        return adjusted / max(norm, _EPSILON)

    expected_relative = relative(expected_coeff)
    capture_relative = relative(capture_coeff)
    complex_similarity = float(
        np.clip(abs(np.vdot(expected_relative, capture_relative)), 0.0, 1.0)
    )
    relative_phase_error = float(
        np.linalg.norm(expected_relative - capture_relative) / math.sqrt(2.0)
    )
    return {
        "magnitude_similarity": magnitude_similarity,
        "complex_phase_aware_similarity": complex_similarity,
        "relative_phase_error": relative_phase_error,
    }


def _midi_frequency(note: int) -> float:
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


def _frame_features(
    samples: npt.NDArray[np.float64],
    sample_rate: int,
    *,
    frame_seconds: float = 0.10,
    hop_seconds: float = 0.05,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    frame = max(64, int(round(frame_seconds * sample_rate)))
    hop = max(1, int(round(hop_seconds * sample_rate)))
    if samples.size < frame:
        return np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64)
    centroids = []
    rms_values = []
    frequencies = np.fft.rfftfreq(frame, 1.0 / sample_rate)
    window = np.hanning(frame)
    for start in range(0, samples.size - frame + 1, hop):
        segment = samples[start : start + frame]
        rms = float(np.sqrt(np.mean(np.square(segment), dtype=np.float64)))
        spectrum = np.abs(np.fft.rfft((segment - float(np.mean(segment))) * window))
        total = float(np.sum(spectrum))
        centroid = 0.0 if total <= _EPSILON else float(np.dot(frequencies, spectrum) / total)
        centroids.append(centroid)
        rms_values.append(rms)
    return np.asarray(centroids, dtype=np.float64), np.asarray(rms_values, dtype=np.float64)


def _correlation(left: npt.NDArray[np.float64], right: npt.NDArray[np.float64]) -> float:
    length = min(left.size, right.size)
    if length < 3:
        return 0.0
    left = left[:length]
    right = right[:length]
    left = left - float(np.mean(left))
    right = right - float(np.mean(right))
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    return 0.0 if denominator <= _EPSILON else float(np.clip(np.dot(left, right) / denominator, -1.0, 1.0))


def _click_count(samples: npt.NDArray[np.float64]) -> int:
    if samples.size < 4:
        return 0
    difference = np.diff(samples)
    median = float(np.median(difference))
    mad = float(np.median(np.abs(difference - median)))
    scale = max(1.4826 * mad, 1.0e-7)
    candidates = np.flatnonzero(np.abs(difference - median) > 14.0 * scale)
    if candidates.size == 0:
        return 0
    # Merge adjacent sample detections into one event.
    return int(1 + np.count_nonzero(np.diff(candidates) > 8))


def compare_package_readback(package_path: Path, readback_path: Path) -> dict[str, object]:
    sent = DumpFile.from_bytes(package_path.read_bytes())
    readback = DumpFile.from_bytes(readback_path.read_bytes())
    index = {(int(message.dump_type), message.address): message for message in readback.messages}
    comparisons = []
    for message in sent.messages:
        key = (int(message.dump_type), message.address)
        actual = index.get(key)
        comparisons.append(
            {
                "dump_type": key[0],
                "address": key[1],
                "present": actual is not None,
                "payload_equal": actual is not None and actual.payload == message.payload,
                "sent_sha256": sha256(message.to_bytes()).hexdigest(),
                "readback_sha256": None if actual is None else sha256(actual.to_bytes()).hexdigest(),
            }
        )
    passed = all(item["payload_equal"] for item in comparisons)
    return {
        "status": "pass" if passed else "fail",
        "package_path": str(package_path),
        "package_sha256": _file_hash(package_path),
        "readback_path": str(readback_path),
        "readback_sha256": _file_hash(readback_path),
        "expected_message_count": len(sent.messages),
        "matched_message_count": sum(bool(item["payload_equal"]) for item in comparisons),
        "comparisons": comparisons,
    }


def _recommendations(
    *,
    readback_pass: bool,
    fixed_blocks: Sequence[Mapping[str, object]],
    sweep: Mapping[str, object],
    source_to_xt: Mapping[str, object],
) -> list[dict[str, object]]:
    recommendations: list[dict[str, object]] = []
    if not readback_pass:
        recommendations.append(
            {
                "priority": "blocking",
                "classification": "transport_or_state",
                "modules": [
                    "src/w_mwxt_wavetable_tool/hardware_validation.py",
                    "src/w_mwxt_wavetable_tool/wavetable/package.py",
                    "src/w_mwxt_wavetable_tool/wavetable/materialization.py",
                ],
                "action": "Do not tune DSP algorithms. Fix package/read-back identity first.",
            }
        )
        return recommendations

    pitch_failures = [block for block in fixed_blocks if abs(float(block["pitch_cents_error"])) > 35.0]
    magnitude_values = [float(block["magnitude_similarity"]) for block in fixed_blocks]
    phase_values = [float(block["complex_phase_aware_similarity"]) for block in fixed_blocks]
    by_position: dict[int, list[Mapping[str, object]]] = {}
    for block in fixed_blocks:
        by_position.setdefault(int(block["position"]), []).append(block)
    endpoint_scores = [
        float(item["magnitude_similarity"])
        for position in (0, 60)
        for item in by_position.get(position, [])
    ]
    middle_scores = [
        float(item["magnitude_similarity"])
        for position in (10, 20, 30, 40, 50)
        for item in by_position.get(position, [])
    ]

    if pitch_failures:
        recommendations.append(
            {
                "priority": "blocking",
                "classification": "capture_or_sound_setup",
                "modules": [],
                "action": "Verify the controlled Sound, MIDI note mapping, sample-rate stability and DAW Warp before changing repository algorithms.",
                "evidence": {"pitch_failure_count": len(pitch_failures)},
            }
        )
    if magnitude_values and float(np.mean(magnitude_values)) < 0.82:
        recommendations.append(
            {
                "priority": "high",
                "classification": "source_reconstruction_or_xt_projection",
                "modules": [
                    "src/w_mwxt_wavetable_tool/analysis/cycle_detection.py",
                    "src/w_mwxt_wavetable_tool/analysis/cycle_selection.py",
                    "src/w_mwxt_wavetable_tool/analysis/reconstruction.py",
                    "src/w_mwxt_wavetable_tool/xt/projection.py",
                ],
                "action": "Compare source-cycle selection and 128-to-64 projection variants against the measured harmonic profile. Add the current source/package hashes as a non-regression corpus before changing weights.",
                "evidence": {"mean_magnitude_similarity": float(np.mean(magnitude_values))},
            }
        )
    if phase_values and float(np.mean(phase_values)) + 0.08 < float(np.mean(magnitude_values)):
        recommendations.append(
            {
                "priority": "high",
                "classification": "phase_model_mismatch",
                "modules": [
                    "src/w_mwxt_wavetable_tool/xt/projection.py",
                    "src/w_mwxt_wavetable_tool/xt/trajectory.py",
                    "src/w_mwxt_wavetable_tool/wavetable/interpolation.py",
                ],
                "action": "Magnitude is acceptable but relative harmonic phase is not. Review phase rotation selection and phase-aware interpolation; do not replace the metric with magnitude-only FFT.",
                "evidence": {
                    "mean_magnitude_similarity": float(np.mean(magnitude_values)),
                    "mean_phase_aware_similarity": float(np.mean(phase_values)),
                },
            }
        )
    if endpoint_scores and middle_scores and float(np.mean(endpoint_scores)) - float(np.mean(middle_scores)) > 0.10:
        recommendations.append(
            {
                "priority": "high",
                "classification": "interpolation_or_placement",
                "modules": [
                    "src/w_mwxt_wavetable_tool/wavetable/interpolation.py",
                    "src/w_mwxt_wavetable_tool/wavetable/transition_planner.py",
                    "src/w_mwxt_wavetable_tool/wavetable/builder.py",
                    "src/w_mwxt_wavetable_tool/wavetable/continuity.py",
                ],
                "action": "Endpoints reproduce better than interior positions. Tune interval method selection, density allocation or placement using the position-level evidence.",
                "evidence": {
                    "endpoint_mean": float(np.mean(endpoint_scores)),
                    "middle_mean": float(np.mean(middle_scores)),
                },
            }
        )
    if float(sweep.get("centroid_correlation", 0.0)) < 0.80:
        recommendations.append(
            {
                "priority": "high",
                "classification": "trajectory_order_or_scan",
                "modules": [
                    "src/w_mwxt_wavetable_tool/wavetable/ordering.py",
                    "src/w_mwxt_wavetable_tool/wavetable/placement.py",
                    "src/w_mwxt_wavetable_tool/wavetable/factory_placement.py",
                    "src/w_mwxt_wavetable_tool/xt/trajectory.py",
                ],
                "action": "The measured timbral trajectory does not follow the mathematical sweep. Review ordering and placement before changing individual wave projection.",
                "evidence": {"centroid_correlation": float(sweep.get("centroid_correlation", 0.0))},
            }
        )
    if int(sweep.get("excess_click_count", 0)) > 0:
        recommendations.append(
            {
                "priority": "high",
                "classification": "discontinuity",
                "modules": [
                    "src/w_mwxt_wavetable_tool/wavetable/continuity.py",
                    "src/w_mwxt_wavetable_tool/wavetable/transition_shaping.py",
                    "src/w_mwxt_wavetable_tool/xt/trajectory_qc.py",
                ],
                "action": "Add measured click locations to transition QC and test alternate phase/transition choices around those positions.",
                "evidence": {"excess_click_count": int(sweep.get("excess_click_count", 0))},
            }
        )
    source_expected = float(source_to_xt.get("source_to_expected_forward_centroid_correlation", 0.0))
    source_actual = float(source_to_xt.get("source_to_xt_forward_centroid_correlation", 0.0))
    reverse_repeatability = float(source_to_xt.get("xt_forward_reverse_repeatability", 0.0))
    if source_expected < 0.60:
        recommendations.append(
            {
                "priority": "review",
                "classification": "source_to_trajectory_mapping",
                "modules": [
                    "src/w_mwxt_wavetable_tool/analysis/code_v6.py",
                    "src/w_mwxt_wavetable_tool/analysis/cycle_selection.py",
                    "src/w_mwxt_wavetable_tool/xt/trajectory.py",
                    "src/w_mwxt_wavetable_tool/wavetable/ordering.py",
                ],
                "action": "The mathematical sweep does not closely follow the source spectral-centroid evolution. Review source segmentation, candidate selection and trajectory ordering before attributing the difference to the XT hardware.",
                "evidence": {
                    "source_to_expected_forward_centroid_correlation": source_expected,
                },
            }
        )
    elif source_expected - source_actual > 0.12:
        recommendations.append(
            {
                "priority": "high",
                "classification": "software_preview_to_xt_gap",
                "modules": [
                    "src/w_mwxt_wavetable_tool/xt/projection.py",
                    "src/w_mwxt_wavetable_tool/wavetable/interpolation.py",
                    "src/w_mwxt_wavetable_tool/xt/trajectory_qc.py",
                ],
                "action": "The source follows the mathematical preview more closely than the real XT sweep. Preserve this source/package/read-back evidence and test projection or interpolation changes one variable at a time.",
                "evidence": {
                    "source_to_expected_forward_centroid_correlation": source_expected,
                    "source_to_xt_forward_centroid_correlation": source_actual,
                },
            }
        )
    if reverse_repeatability < 0.80:
        recommendations.append(
            {
                "priority": "review",
                "classification": "scan_direction_or_capture_repeatability",
                "modules": [
                    "src/w_mwxt_wavetable_tool/xt/trajectory_qc.py",
                    "src/w_mwxt_wavetable_tool/wavetable/continuity.py",
                ],
                "action": "Forward and reverse XT scans are not sufficiently repeatable. Repeat the capture before changing a core algorithm; then inspect direction-dependent transition behavior.",
                "evidence": {"xt_forward_reverse_repeatability": reverse_repeatability},
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "priority": "normal",
                "classification": "measured_path_consistent",
                "modules": [
                    "tests/test_real_sample_calibration.py",
                    "docs/validation/CODE_V10_REAL_SAMPLE_CALIBRATION.md",
                ],
                "action": "Promote the measured metrics and hashes to a private non-regression fixture; no core algorithm change is justified by this run alone.",
            }
        )
    return recommendations


def analyze_campaign_captures(
    campaign_root: str | Path,
    *,
    readback_path: str | Path,
    fixed_capture_path: str | Path,
    sweep_capture_path: str | Path,
) -> tuple[Path, Path, Path]:
    root = Path(campaign_root).expanduser().resolve(strict=True)
    campaign = _read_json(root / "CAMPAIGN.json")
    stem = str(campaign["campaign_stem"])
    package_relative = next(
        name for name in campaign["artifacts"] if name.endswith(".package.syx")
    )
    package_path = root / package_relative
    readback = Path(readback_path).expanduser().resolve(strict=True)
    fixed_capture = Path(fixed_capture_path).expanduser().resolve(strict=True)
    sweep_capture = Path(sweep_capture_path).expanduser().resolve(strict=True)

    readback_report = compare_package_readback(package_path, readback)

    fixed_manifest_path = root / str(campaign["required_captures"]["fixed_positions"]["midi"]).replace(".mid", ".json")
    sweep_manifest_path = root / str(campaign["required_captures"]["sweep"]["midi"]).replace(".mid", ".json")
    fixed_manifest = _read_json(fixed_manifest_path)
    sweep_manifest = _read_json(sweep_manifest_path)
    fixed_expected_path = root / str(campaign["required_captures"]["fixed_positions"]["expected_preview"])
    sweep_expected_path = root / str(campaign["required_captures"]["sweep"]["expected_preview"])

    fixed_expected, fixed_expected_rate, fixed_expected_meta = _load_audio(fixed_expected_path, label="fixed expected preview")
    fixed_actual, fixed_rate, fixed_actual_meta = _load_audio(fixed_capture, label="fixed XT capture")
    sweep_expected, sweep_expected_rate, sweep_expected_meta = _load_audio(sweep_expected_path, label="sweep expected preview")
    sweep_actual, sweep_rate, sweep_actual_meta = _load_audio(sweep_capture, label="sweep XT capture")
    source_relative = str(campaign["source"].get("campaign_path", ""))
    source_path = root / source_relative if source_relative else Path(str(campaign["source"].get("original_path", "")))
    source_samples, source_rate, source_meta = _load_source_audio(source_path.resolve(strict=True))
    if fixed_expected_rate != fixed_rate:
        fixed_expected = _resample_linear(fixed_expected, fixed_expected_rate, fixed_rate)
        fixed_expected_rate = fixed_rate
    if sweep_expected_rate != sweep_rate:
        sweep_expected = _resample_linear(sweep_expected, sweep_expected_rate, sweep_rate)
        sweep_expected_rate = sweep_rate

    fixed_lag = _alignment_lag_seconds(fixed_expected, fixed_actual, fixed_rate)
    fixed_blocks: list[dict[str, object]] = []
    for block in fixed_manifest["blocks"]:
        start = float(block["analysis_start_seconds"])
        end = float(block["analysis_end_seconds"])
        expected_segment = _slice_with_lag(fixed_expected, fixed_rate, start, end, 0.0)
        actual_segment = _slice_with_lag(fixed_actual, fixed_rate, start, end, fixed_lag)
        expected_hz = _midi_frequency(int(block["midi_note"]))
        measured_hz = _estimate_pitch(actual_segment, fixed_rate, expected_hz)
        cents = 1200.0 * math.log2(measured_hz / expected_hz) if measured_hz > 0.0 else 9999.0
        harmonics = _harmonic_metrics(
            expected_segment,
            actual_segment,
            fixed_rate,
            measured_hz if measured_hz > 0.0 else expected_hz,
        )
        expected_rms = float(np.sqrt(np.mean(np.square(expected_segment), dtype=np.float64))) if expected_segment.size else 0.0
        actual_rms = float(np.sqrt(np.mean(np.square(actual_segment), dtype=np.float64))) if actual_segment.size else 0.0
        fixed_blocks.append(
            {
                "index": int(block["index"]),
                "position": int(block["position"]),
                "midi_note": int(block["midi_note"]),
                "expected_frequency_hz": expected_hz,
                "measured_frequency_hz": measured_hz,
                "pitch_cents_error": cents,
                "expected_rms": expected_rms,
                "capture_rms": actual_rms,
                "level_ratio": actual_rms / max(expected_rms, _EPSILON),
                **harmonics,
            }
        )

    sweep_lag = _alignment_lag_seconds(sweep_expected, sweep_actual, sweep_rate)
    sweep_start = float(sweep_manifest["note_start_seconds"])
    sweep_end = float(sweep_manifest["note_end_seconds"])
    expected_sweep_segment = _slice_with_lag(sweep_expected, sweep_rate, sweep_start, sweep_end, 0.0)
    actual_sweep_segment = _slice_with_lag(sweep_actual, sweep_rate, sweep_start, sweep_end, sweep_lag)
    expected_centroid, expected_rms = _frame_features(expected_sweep_segment, sweep_rate)
    actual_centroid, actual_rms = _frame_features(actual_sweep_segment, sweep_rate)
    centroid_correlation = _correlation(expected_centroid, actual_centroid)
    expected_clicks = _click_count(expected_sweep_segment)
    actual_clicks = _click_count(actual_sweep_segment)
    median_rms = float(np.median(actual_rms)) if actual_rms.size else 0.0
    dropout_threshold = median_rms * (10.0 ** (-30.0 / 20.0))
    dropout_ratio = 0.0 if actual_rms.size == 0 else float(np.mean(actual_rms < dropout_threshold))
    sweep_report = {
        "alignment_lag_seconds": sweep_lag,
        "centroid_correlation": centroid_correlation,
        "expected_click_count": expected_clicks,
        "capture_click_count": actual_clicks,
        "excess_click_count": max(0, actual_clicks - expected_clicks),
        "dropout_ratio": dropout_ratio,
        "frame_count": int(min(expected_centroid.size, actual_centroid.size)),
    }

    schedule = sweep_manifest.get("schedule", [])
    if not isinstance(schedule, list) or len(schedule) < 62:
        raise ValueError("sweep manifest does not expose the complete forward/reverse schedule")
    step_seconds = float(sweep_manifest["step_seconds"])
    forward_end = float(schedule[60]["time_seconds"]) + step_seconds
    reverse_start = float(schedule[61]["time_seconds"])
    source_trim = max(0, int(round(source_samples.size * 0.03)))
    source_core = source_samples[source_trim: source_samples.size - source_trim] if source_samples.size > 2 * source_trim else source_samples
    source_centroid, _ = _frame_features(source_core, source_rate)
    expected_forward, _ = _frame_features(
        _slice_with_lag(sweep_expected, sweep_rate, sweep_start, forward_end, 0.0), sweep_rate
    )
    actual_forward, _ = _frame_features(
        _slice_with_lag(sweep_actual, sweep_rate, sweep_start, forward_end, sweep_lag), sweep_rate
    )
    actual_reverse, _ = _frame_features(
        _slice_with_lag(sweep_actual, sweep_rate, reverse_start, sweep_end, sweep_lag), sweep_rate
    )
    source_curve = np.log1p(_resample_curve(source_centroid))
    expected_forward_curve = np.log1p(_resample_curve(expected_forward))
    actual_forward_curve = np.log1p(_resample_curve(actual_forward))
    actual_reverse_curve = np.log1p(_resample_curve(actual_reverse))[::-1]
    source_to_xt_report = {
        "source": source_meta,
        "source_to_expected_forward_centroid_correlation": _correlation(source_curve, expected_forward_curve),
        "source_to_xt_forward_centroid_correlation": _correlation(source_curve, actual_forward_curve),
        "expected_to_xt_forward_centroid_correlation": _correlation(expected_forward_curve, actual_forward_curve),
        "xt_forward_reverse_repeatability": _correlation(actual_forward_curve, actual_reverse_curve),
        "metric_role": (
            "Product-level diagnostic of spectral-evolution shape. It complements, but does not replace, "
            "the position-level projection and phase-aware waveform comparisons."
        ),
    }

    readback_pass = readback_report["status"] == "pass"
    fixed_pass = bool(fixed_blocks) and all(
        abs(float(item["pitch_cents_error"])) <= 35.0
        and float(item["magnitude_similarity"]) >= 0.78
        and float(item["complex_phase_aware_similarity"]) >= 0.62
        for item in fixed_blocks
    )
    sweep_pass = (
        centroid_correlation >= 0.78
        and int(sweep_report["excess_click_count"]) <= 2
        and dropout_ratio <= 0.01
    )
    status = "pass" if readback_pass and fixed_pass and sweep_pass else "review"
    if not readback_pass:
        status = "fail"

    recommendations = _recommendations(
        readback_pass=readback_pass,
        fixed_blocks=fixed_blocks,
        sweep=sweep_report,
        source_to_xt=source_to_xt_report,
    )
    report: dict[str, object] = {
        "schema_version": CAPTURE_ANALYSIS_SCHEMA_VERSION,
        "status": status,
        "campaign_sha256": campaign["campaign_sha256"],
        "campaign_stem": stem,
        "source_sha256": campaign["source"]["sha256"],
        "package_sha256": campaign["hash_links"]["hardware_package_sha256"],
        "readback": readback_report,
        "fixed_capture": {
            "expected": fixed_expected_meta,
            "actual": fixed_actual_meta,
            "alignment_lag_seconds": fixed_lag,
            "blocks": fixed_blocks,
            "pass": fixed_pass,
            "mean_magnitude_similarity": float(np.mean([float(item["magnitude_similarity"]) for item in fixed_blocks])),
            "mean_phase_aware_similarity": float(np.mean([float(item["complex_phase_aware_similarity"]) for item in fixed_blocks])),
            "maximum_absolute_pitch_error_cents": max(abs(float(item["pitch_cents_error"])) for item in fixed_blocks),
        },
        "sweep_capture": {
            "expected": sweep_expected_meta,
            "actual": sweep_actual_meta,
            **sweep_report,
            "pass": sweep_pass,
        },
        "source_to_xt_product_metrics": source_to_xt_report,
        "repository_change_recommendations": recommendations,
        "claim_boundary": (
            "PASS means this source-derived package, controlled Sound, fixed-position capture and sweep are consistent within the stated tolerances. "
            "It is not a bit-exact DSP-emulation claim and does not by itself authorize changing a core algorithm without a second source and repeat capture."
        ),
    }
    report["analysis_sha256"] = sha256(
        json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()

    reports = root / "reports"
    json_path = reports / f"{stem}.XT_REAL_SAMPLE_ANALYSIS.json"
    markdown_path = reports / f"{stem}.XT_REAL_SAMPLE_ANALYSIS.md"
    recommendations_path = reports / f"{stem}.REPOSITORY_CHANGE_PLAN.json"
    _write_json(json_path, report)
    _write_json(
        recommendations_path,
        {
            "schema_version": 1,
            "analysis_sha256": report["analysis_sha256"],
            "status": status,
            "recommendations": recommendations,
            "rule": "Core algorithm changes require repeatable evidence from the generated reference source and at least one independent user source.",
        },
    )

    rows = [
        f"# {stem} — analyse réelle du Microwave XT",
        "",
        f"- Statut : **{status.upper()}**",
        f"- Read-back : **{str(readback_report['status']).upper()}**",
        f"- Test positions fixes : **{'PASS' if fixed_pass else 'REVIEW'}**",
        f"- Sweep : **{'PASS' if sweep_pass else 'REVIEW'}**",
        f"- Corrélation du centroïde du sweep : `{centroid_correlation:.6f}`",
        f"- Clics excédentaires : `{sweep_report['excess_click_count']}`",
        f"- Dropouts : `{dropout_ratio:.6%}`",
        f"- Source → preview (évolution spectrale) : `{float(source_to_xt_report['source_to_expected_forward_centroid_correlation']):.6f}`",
        f"- Source → XT (évolution spectrale) : `{float(source_to_xt_report['source_to_xt_forward_centroid_correlation']):.6f}`",
        f"- Répétabilité XT aller/retour : `{float(source_to_xt_report['xt_forward_reverse_repeatability']):.6f}`",
        "",
        "## Positions fixes",
        "",
        "| Position | Note | Erreur cents | Similarité magnitude | Similarité phase-aware |",
        "|---:|---:|---:|---:|---:|",
    ]
    for item in fixed_blocks:
        rows.append(
            f"| {item['position']} | {item['midi_note']} | {float(item['pitch_cents_error']):.3f} | "
            f"{float(item['magnitude_similarity']):.6f} | {float(item['complex_phase_aware_similarity']):.6f} |"
        )
    rows.extend(["", "## Plan de modification du dépôt", ""])
    for recommendation in recommendations:
        rows.append(f"### {str(recommendation['priority']).upper()} — {recommendation['classification']}")
        rows.append("")
        rows.append(str(recommendation["action"]))
        modules = recommendation.get("modules", [])
        if modules:
            rows.append("")
            rows.append("Modules concernés : " + ", ".join(f"`{module}`" for module in modules))
        rows.append("")
    rows.extend(["## Limite de revendication", "", str(report["claim_boundary"]), ""])
    markdown_path.write_text("\n".join(rows), encoding="utf-8", newline="\n")
    return json_path, markdown_path, recommendations_path


__all__ = [
    "CAPTURE_ANALYSIS_SCHEMA_VERSION",
    "compare_package_readback",
    "analyze_campaign_captures",
]
