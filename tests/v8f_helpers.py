from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace

import numpy as np


def digest(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


def component(label: str, **values: object) -> SimpleNamespace:
    return SimpleNamespace(analysis_sha256=digest(label), **values)


def source_components(*, with_v7_chain: bool = True) -> dict[str, object]:
    sample_rate = 16000
    samples = np.linspace(-0.75, 0.75, 128, dtype=np.float64)
    sample_hash = sha256(samples.astype("<f8").tobytes()).hexdigest()
    audio = SimpleNamespace(
        metadata=SimpleNamespace(sample_rate=sample_rate),
        mono_samples=samples,
        sample_sha256=sample_hash,
        state_sha256=digest("imported-state"),
    )
    signal = component("signal")
    spectral = component("spectral")
    harmonic = component("harmonic")
    code_v5 = component(
        "code-v5",
        signal_analysis=signal,
        spectral_analysis=spectral,
        harmonic_perceptual_analysis=harmonic,
    )
    segmentation = component("segmentation")
    reconstructed = component("reconstructed")
    code_v6 = component(
        "code-v6",
        sample_rate=sample_rate,
        sample_count=samples.size,
        sample_sha256=sample_hash,
        code_v5_analysis=code_v5,
        segmentation_analysis=segmentation,
        reconstructed_wave_set=reconstructed,
    )
    projection = component(
        "projection",
        source_code_v6_analysis_sha256=code_v6.analysis_sha256,
        source_reconstructed_wave_set_sha256=reconstructed.analysis_sha256,
    )
    result: dict[str, object] = {
        "audio": audio,
        "signal": signal,
        "spectral": spectral,
        "harmonic": harmonic,
        "segmentation": segmentation,
        "reconstructed": reconstructed,
        "code_v5": code_v5,
        "code_v6": code_v6,
        "projection": projection,
    }
    if with_v7_chain:
        trajectory = component(
            "trajectory",
            source_projection_set_sha256=projection.analysis_sha256,
            source_reconstructed_wave_set_sha256=reconstructed.analysis_sha256,
        )
        qc = component(
            "qc",
            source_trajectory_sha256=trajectory.analysis_sha256,
            source_projection_set_sha256=projection.analysis_sha256,
        )
        package = component(
            "package",
            source_trajectory_sha256=trajectory.analysis_sha256,
            source_qc_sha256=qc.analysis_sha256,
            source_projection_set_sha256=projection.analysis_sha256,
        )
        result.update(trajectory=trajectory, qc=qc, package=package)
    return result


def decision_components(*, rejected: bool = False, wave_count: int = 4) -> dict[str, object]:
    source = source_components(with_v7_chain=False)
    code_v6 = source["code_v6"]
    signal = source["signal"]
    spectral = source["spectral"]
    harmonic = source["harmonic"]
    segmentation = source["segmentation"]
    sample_rate = code_v6.sample_rate
    sample_count = code_v6.sample_count
    sample_hash = code_v6.sample_sha256

    identity = {
        "sample_rate": sample_rate,
        "sample_count": sample_count,
        "sample_sha256": sample_hash,
    }
    extension = component(
        "extension",
        **identity,
        signal_analysis_sha256=signal.analysis_sha256,
    )
    behavior = component(
        "behavior",
        **identity,
        signal_analysis_sha256=signal.analysis_sha256,
        signal_extension_analysis_sha256=extension.analysis_sha256,
    )
    regions = component(
        "regions",
        **identity,
        signal_analysis_sha256=signal.analysis_sha256,
        signal_extension_analysis_sha256=extension.analysis_sha256,
        segmentation_analysis_sha256=segmentation.analysis_sha256,
    )
    formants = component(
        "formants",
        **identity,
        spectral_analysis_sha256=spectral.analysis_sha256,
    )
    evolution = component(
        "evolution",
        **identity,
        spectral_analysis_sha256=spectral.analysis_sha256,
        harmonic_perceptual_analysis_sha256=harmonic.analysis_sha256,
    )
    perceptual = component(
        "perceptual",
        **identity,
        signal_analysis_sha256=signal.analysis_sha256,
        signal_extension_analysis_sha256=extension.analysis_sha256,
        spectral_analysis_sha256=spectral.analysis_sha256,
        harmonic_perceptual_analysis_sha256=harmonic.analysis_sha256,
        spectral_evolution_analysis_sha256=evolution.analysis_sha256,
        formant_analysis_sha256=formants.analysis_sha256,
    )
    musical = component(
        "musical",
        **identity,
        behavior_classification_sha256=behavior.analysis_sha256,
        perceptual_feature_sha256=perceptual.analysis_sha256,
        formant_analysis_sha256=formants.analysis_sha256,
    )
    mode_status = "rejected" if rejected else "selected"
    mode = component(
        "mode",
        **identity,
        behavior_classification_sha256=behavior.analysis_sha256,
        musical_classification_sha256=musical.analysis_sha256,
        perceptual_feature_sha256=perceptual.analysis_sha256,
        spectral_evolution_analysis_sha256=evolution.analysis_sha256,
        status=SimpleNamespace(value=mode_status),
        selected_mode=None if rejected else SimpleNamespace(value="stable_cycle"),
        warnings=("source rejected",) if rejected else (),
    )
    definition = component("profile-definition")
    profile = component(
        "profile-selection",
        musical_classification_sha256=musical.analysis_sha256,
        mode_decision_sha256=mode.analysis_sha256,
        selected_profile=SimpleNamespace(value="pad"),
        definition=definition,
        warnings=(),
    )
    optimization = component(
        "optimization",
        profile=definition,
        entries=tuple(SimpleNamespace(index=index) for index in range(wave_count)),
    )
    repair = component(
        "repair-sequence",
        entries=tuple(SimpleNamespace(index=index) for index in range(wave_count)),
    )
    return {
        **source,
        "extension": extension,
        "behavior": behavior,
        "regions": regions,
        "formants": formants,
        "evolution": evolution,
        "perceptual": perceptual,
        "musical": musical,
        "mode": mode,
        "profile": profile,
        "optimization": optimization,
        "repair": repair,
    }
