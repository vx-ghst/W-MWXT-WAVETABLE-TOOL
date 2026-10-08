from __future__ import annotations

from w_mwxt_wavetable_tool.wavetable import (
    GenerationMethod,
    WavetableBuildStatus,
    create_wavetable_build_request,
)

from v8a_helpers import candidate, fixed_tail, ready_preflight


def test_v8a_declares_all_interpolation_families_without_executing_them() -> None:
    names = {method.value for method in GenerationMethod if method.is_interpolation}
    assert names == {
        "waveform_interpolation",
        "amplitude_interpolation",
        "phase_aware_interpolation",
        "spectral_interpolation",
        "harmonic_interpolation",
        "perceptual_interpolation",
    }


def test_v8a_request_boundary_does_not_materialize_wctd_or_sysex() -> None:
    request = create_wavetable_build_request(
        ready_preflight(),
        (candidate("first"), candidate("second", source_index=1, offset=1)),
        fixed_tail(),
    )
    payload = request.to_dict()
    boundaries = payload["boundaries"]
    assert boundaries == {
        "selects_structural_waves": False,
        "orders_candidates": False,
        "interpolates_transitions": False,
        "materializes_wctd": False,
        "allocates_xt_memory": False,
        "generates_sysex": False,
        "opens_midi_port": False,
        "transmits_midi": False,
    }


def test_v8a_models_do_not_claim_an_implemented_builder() -> None:
    assert {status.value for status in WavetableBuildStatus} == {"complete", "rejected"}
