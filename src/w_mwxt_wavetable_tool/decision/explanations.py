from __future__ import annotations

from importlib import import_module

from .models import ConversionMode, ModeExecutionPath


MODE_EXECUTION_PATHS: dict[ConversionMode, ModeExecutionPath] = {
    ConversionMode.STABLE_CYCLE: ModeExecutionPath(
        mode=ConversionMode.STABLE_CYCLE,
        module="w_mwxt_wavetable_tool.analysis.cycle_detection",
        callable_name="discover_cycles",
        strategy_argument=None,
        purpose="Discover stable source cycles before representative-cycle selection.",
    ),
    ConversionMode.EVOLVING_HARMONICS: ModeExecutionPath(
        mode=ConversionMode.EVOLVING_HARMONICS,
        module="w_mwxt_wavetable_tool.analysis.regions",
        callable_name="analyze_region_interest",
        strategy_argument=None,
        purpose="Allocate analysis density to evolving harmonic regions before cycle selection.",
    ),
    ConversionMode.DYNAMIC_PITCH: ModeExecutionPath(
        mode=ConversionMode.DYNAMIC_PITCH,
        module="w_mwxt_wavetable_tool.analysis.repitch",
        callable_name="plan_working_pitch",
        strategy_argument=None,
        purpose="Plan an explicit working pitch before cycle discovery and reconstruction.",
    ),
    ConversionMode.SPECTRAL_RECONSTRUCTION: ModeExecutionPath(
        mode=ConversionMode.SPECTRAL_RECONSTRUCTION,
        module="w_mwxt_wavetable_tool.analysis.reconstruction",
        callable_name="reconstruct_selected_cycles",
        strategy_argument="spectral",
        purpose="Use the executable spectral reconstruction path for weakly periodic material.",
    ),
    ConversionMode.HYBRID: ModeExecutionPath(
        mode=ConversionMode.HYBRID,
        module="w_mwxt_wavetable_tool.analysis.reconstruction",
        callable_name="reconstruct_selected_cycles",
        strategy_argument="hybrid",
        purpose="Use the executable hybrid time-domain and spectral reconstruction path.",
    ),
}


def execution_path_for_mode(mode: ConversionMode | str) -> ModeExecutionPath:
    try:
        selected = ConversionMode(mode)
    except ValueError as exc:
        raise ValueError(f"Unknown conversion mode: {mode!r}") from exc
    return MODE_EXECUTION_PATHS[selected]


def validate_mode_execution_paths() -> tuple[ModeExecutionPath, ...]:
    """Import every declared module and prove the declared callable is executable."""

    paths = tuple(MODE_EXECUTION_PATHS[mode] for mode in ConversionMode)
    if len(paths) != len(ConversionMode):
        raise ValueError("every conversion mode must have exactly one execution path")
    for path in paths:
        module = import_module(path.module)
        target = getattr(module, path.callable_name, None)
        if not callable(target):
            raise ValueError(
                f"Mode {path.mode.value} does not resolve to callable "
                f"{path.module}.{path.callable_name}"
            )
    return paths


def confidence_from_ranked_scores(scores: tuple[float, ...]) -> tuple[float, float]:
    if not scores:
        raise ValueError("scores must not be empty")
    ordered = sorted((float(value) for value in scores), reverse=True)
    if any(value < 0.0 or value > 1.0 for value in ordered):
        raise ValueError("scores must be between 0 and 1")
    winner = ordered[0]
    runner_up = ordered[1] if len(ordered) > 1 else 0.0
    separation = max(0.0, winner - runner_up)
    confidence = min(1.0, max(0.0, 0.55 * winner + 0.45 * separation))
    return confidence, float(1.0 - confidence)
