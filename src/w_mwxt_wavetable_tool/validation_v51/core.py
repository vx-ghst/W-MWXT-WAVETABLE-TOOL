from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import struct
import sys
from typing import Any, Mapping, Sequence

import numpy as np
import soundfile as sf

PROFILE_NAMES = (
    "bass_sub", "lead", "pad", "bell_fm", "vocal_choir",
    "texture", "drone", "percussive", "experimental",
)
CORPUS_VARIANTS = ("canonical", "evolving", "edge")
N_MATRIX = (1, 2, 3, 4, 8, 16, 32, 60, 61)


def canonical_hash(payload: Mapping[str, object]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def _normalize(samples: np.ndarray, peak: float = 0.82) -> np.ndarray:
    values = np.asarray(samples, dtype=np.float64)
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    values -= float(np.mean(values))
    maximum = float(np.max(np.abs(values))) if values.size else 0.0
    if maximum > 1.0e-12:
        values = values * (peak / maximum)
    return np.ascontiguousarray(values, dtype=np.float64)


def _fade(samples: np.ndarray, sample_rate: int, seconds: float = 0.03) -> np.ndarray:
    result = np.asarray(samples, dtype=np.float64).copy()
    count = min(int(round(sample_rate * seconds)), result.size // 2)
    if count > 0:
        ramp = np.sin(np.linspace(0.0, math.pi / 2.0, count)) ** 2
        result[:count] *= ramp
        result[-count:] *= ramp[::-1]
    return result


def _harmonic_series(t: np.ndarray, f0: float, amplitudes: Sequence[float], phases: Sequence[float] | None = None) -> np.ndarray:
    result = np.zeros_like(t)
    phases = tuple(0.0 for _ in amplitudes) if phases is None else tuple(phases)
    for harmonic, (amplitude, phase) in enumerate(zip(amplitudes, phases), start=1):
        result += float(amplitude) * np.sin(2.0 * math.pi * f0 * harmonic * t + float(phase))
    return result


def _formant_series(t: np.ndarray, f0: float, centers: Sequence[float], widths: Sequence[float], motion: np.ndarray | None = None) -> np.ndarray:
    sample_rate = 1.0 / (t[1] - t[0])
    result = np.zeros_like(t)
    for harmonic in range(1, int((sample_rate / 2) // f0)):
        frequency = harmonic * f0
        envelope = 0.0
        for center, width in zip(centers, widths):
            envelope += math.exp(-0.5 * ((frequency - center) / width) ** 2)
        if motion is None:
            result += (envelope / max(1.0, harmonic ** 0.35)) * np.sin(2 * math.pi * frequency * t + 0.13 * harmonic)
        else:
            result += (envelope / max(1.0, harmonic ** 0.35)) * np.sin(2 * math.pi * frequency * t + 0.13 * harmonic + motion * harmonic * 0.03)
    return result


def make_profile_sample(profile: str, variant: str, *, sample_rate: int = 48_000, duration: float = 4.0) -> np.ndarray:
    if profile not in PROFILE_NAMES or variant not in CORPUS_VARIANTS:
        raise ValueError("unknown profile or variant")
    count = int(round(sample_rate * duration))
    t = np.arange(count, dtype=np.float64) / sample_rate
    progress = np.linspace(0.0, 1.0, count, dtype=np.float64)
    rng = np.random.default_rng(5100 + PROFILE_NAMES.index(profile) * 17 + CORPUS_VARIANTS.index(variant))

    if profile == "bass_sub":
        if variant == "canonical":
            x = _harmonic_series(t, 55.0, (1.0, 0.26, 0.12, 0.05))
        elif variant == "evolving":
            x = np.sin(2 * math.pi * 55 * t) + (0.08 + 0.35 * progress) * np.sin(2 * math.pi * 110 * t + 0.2) + 0.12 * progress**2 * np.sin(2 * math.pi * 165 * t)
        else:
            x = np.sin(2 * math.pi * 43.65 * t) + 0.42 * np.sin(2 * math.pi * 87.3 * t + math.pi * progress) + 0.05 * np.sin(2 * math.pi * 698.4 * t)
    elif profile == "lead":
        harmonics = np.asarray([1.0 / harmonic for harmonic in range(1, 18)], dtype=np.float64)
        if variant == "canonical":
            x = _harmonic_series(t, 220.0, harmonics)
        elif variant == "evolving":
            x = np.zeros_like(t)
            for h, amp in enumerate(harmonics, start=1):
                x += amp * (0.3 + 0.7 * progress ** min(3, h / 5)) * np.sin(2 * math.pi * 220 * h * t + 0.07 * h)
        else:
            x = _harmonic_series(t, 329.63, tuple(1.0 / math.sqrt(h) for h in range(1, 30)), tuple((h % 5) * 0.7 for h in range(1, 30)))
    elif profile == "pad":
        env = np.sin(math.pi * np.clip(progress, 0, 1)) ** 0.35
        if variant == "canonical":
            x = env * (_harmonic_series(t, 110.0, (1.0, 0.5, 0.32, 0.22, 0.15)) + 0.5 * np.sin(2 * math.pi * 110.35 * t + 0.4))
        elif variant == "evolving":
            x = env * ((1-progress) * _harmonic_series(t, 110.0, (1, .25, .08, .03)) + progress * _harmonic_series(t, 110.0, (.45, .52, .38, .3, .22, .16, .12)))
        else:
            x = env * (0.65 * np.sin(2 * math.pi * 82.4 * t) + 0.55 * np.sin(2 * math.pi * 82.65 * t + 0.5) + 0.25 * np.sin(2 * math.pi * 329.6 * t))
    elif profile == "bell_fm":
        decay = np.exp(-progress * (3.0 if variant != "edge" else 1.5))
        index = 4.0 if variant == "canonical" else (1.0 + 8.0 * progress if variant == "evolving" else 10.0)
        ratio = math.sqrt(2.0) if variant != "edge" else 2.713
        x = decay * np.sin(2 * math.pi * 330.0 * t + index * np.sin(2 * math.pi * 330.0 * ratio * t))
    elif profile == "vocal_choir":
        if variant == "canonical":
            x = _formant_series(t, 100.0, (500, 1500, 2500), (150, 220, 300))
        elif variant == "evolving":
            motion = 2 * math.pi * progress
            x = (1-progress) * _formant_series(t, 100.0, (500, 1500, 2500), (170, 260, 320), motion) + progress * _formant_series(t, 100.0, (700, 1100, 2400), (150, 230, 280), motion)
        else:
            x = _formant_series(t, 146.83, (350, 900, 2800), (90, 120, 220)) + 0.25 * rng.normal(0.0, 0.15, count)
    elif profile == "texture":
        noise = rng.normal(0.0, 1.0, count)
        kernel = np.ones(31, dtype=np.float64) / 31.0
        smooth = np.convolve(noise, kernel, mode="same")
        if variant == "canonical":
            x = 0.55 * smooth + 0.35 * np.sin(2 * math.pi * (80 + 600 * progress) * t)
        elif variant == "evolving":
            x = (0.15 + 0.75 * progress) * smooth + 0.3 * np.sin(2 * math.pi * 120 * t + 12 * np.sin(2 * math.pi * 0.25 * t))
        else:
            x = 0.65 * noise + 0.2 * np.sign(np.sin(2 * math.pi * 350 * t))
    elif profile == "drone":
        if variant == "canonical":
            x = _harmonic_series(t, 73.42, (1.0, .4, .25, .18, .12)) + 0.35 * np.sin(2 * math.pi * 73.58 * t)
        elif variant == "evolving":
            x = _harmonic_series(t, 55.0, (1.0, .35, .18)) + (0.05 + 0.25 * progress) * np.sin(2 * math.pi * 220 * t)
        else:
            x = np.sin(2 * math.pi * 36.71 * t) + 0.7 * np.sin(2 * math.pi * 36.77 * t + 0.8)
    elif profile == "percussive":
        decay = np.exp(-progress * (12 if variant == "canonical" else 7))
        if variant == "canonical":
            x = decay * (_harmonic_series(t, 180.0, (1, .45, .2)) + 0.25 * rng.normal(0, 1, count))
        elif variant == "evolving":
            x = decay * np.sin(2 * math.pi * (220 - 140 * progress) * t) + 0.4 * np.exp(-progress * 30) * rng.normal(0, 1, count)
        else:
            x = np.zeros_like(t)
            for start in (0.0, 0.7, 1.4, 2.3, 3.1):
                index = int(start * sample_rate)
                if index >= count:
                    continue
                length = max(0, min(int(0.15 * sample_rate), count - index))
                if length <= 0:
                    continue
                local = np.arange(length) / sample_rate
                x[index:index+length] += np.exp(-local*35) * (np.sin(2*math.pi*700*local) + 0.5*rng.normal(0,1,length))
    else:  # experimental
        if variant == "canonical":
            phase = 2 * math.pi * (90 * t + 130 * t**2 / max(duration, 1e-6))
            x = np.sin(phase) + 0.4 * np.sign(np.sin(2 * math.pi * 7 * t)) * np.sin(2 * math.pi * 720 * t)
        elif variant == "evolving":
            x = np.sin(2 * math.pi * 110 * t + 8 * np.sin(2 * math.pi * (0.2 + 2.0 * progress) * t))
            x[progress > 0.55] *= -1.0
            x += 0.22 * rng.normal(0, 1, count) * progress
        else:
            x = np.tanh(3.5 * (_harmonic_series(t, 123.47, (1, .7, .55, .4, .3)) + 0.3 * np.sin(2 * math.pi * 19 * t)))
            x[int(count * 0.47):int(count * 0.53)] = 0.0

    return _fade(_normalize(x), sample_rate)


def make_ambiguity_sample(name: str, *, sample_rate: int = 48_000, duration: float = 4.0) -> tuple[np.ndarray, tuple[str, str]]:
    pairs = {
        "bass_sub__drone": ("bass_sub", "drone"),
        "lead__bell_fm": ("lead", "bell_fm"),
        "pad__vocal_choir": ("pad", "vocal_choir"),
        "texture__percussive": ("texture", "percussive"),
        "texture__experimental": ("texture", "experimental"),
    }
    left, right = pairs[name]
    a = make_profile_sample(left, "evolving", sample_rate=sample_rate, duration=duration)
    b = make_profile_sample(right, "canonical", sample_rate=sample_rate, duration=duration)
    return _normalize(0.5 * a + 0.5 * b), (left, right)


def generate_profile_corpus(directory: Path, *, sample_rate: int = 48_000, duration: float = 4.0) -> dict[str, object]:
    directory.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    for profile in PROFILE_NAMES:
        for variant in CORPUS_VARIANTS:
            samples = make_profile_sample(profile, variant, sample_rate=sample_rate, duration=duration)
            path = directory / f"{profile}__{variant}__48k24.wav"
            sf.write(str(path), samples, sample_rate, format="WAV", subtype="PCM_24")
            entries.append({
                "id": f"{profile}__{variant}", "kind": "profile", "expected_profile": profile,
                "variant": variant, "path": path.name, "sha256": file_hash(path),
                "sample_rate": sample_rate, "sample_count": int(samples.size), "duration_seconds": duration,
            })
    for name in ("bass_sub__drone", "lead__bell_fm", "pad__vocal_choir", "texture__percussive", "texture__experimental"):
        samples, expected = make_ambiguity_sample(name, sample_rate=sample_rate, duration=duration)
        path = directory / f"ambiguity__{name}__48k24.wav"
        sf.write(str(path), samples, sample_rate, format="WAV", subtype="PCM_24")
        entries.append({
            "id": f"ambiguity__{name}", "kind": "ambiguity", "expected_profiles": list(expected),
            "path": path.name, "sha256": file_hash(path), "sample_rate": sample_rate,
            "sample_count": int(samples.size), "duration_seconds": duration,
        })
    manifest: dict[str, object] = {
        "schema_version": 1, "sample_rate": sample_rate, "pcm_bits": 24,
        "duration_seconds": duration, "profile_count": len(PROFILE_NAMES),
        "variants_per_profile": len(CORPUS_VARIANTS), "profile_samples": 27,
        "ambiguity_samples": 5, "total_samples": len(entries), "entries": entries,
        "purpose": "Deterministic V5.1 corpus for software classification and staged hardware consequence validation.",
    }
    manifest["corpus_sha256"] = canonical_hash(manifest)
    write_json(directory / "CORPUS_MANIFEST.json", manifest)
    return manifest


def _resample_linear(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate:
        return np.asarray(samples, dtype=np.float64)
    duration = samples.size / source_rate
    source_x = np.arange(samples.size, dtype=np.float64) / source_rate
    target_count = int(round(duration * target_rate))
    target_x = np.arange(target_count, dtype=np.float64) / target_rate
    return np.interp(target_x, source_x, samples).astype(np.float64)


def configure_repo_imports(repo: Path) -> None:
    for path in (repo / "src", repo / "tests"):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


def analyze_profile_corpus(repo: Path, corpus_dir: Path, output_path: Path) -> dict[str, object]:
    configure_repo_imports(repo)
    from v8c_helpers import build_bundle
    from w_mwxt_wavetable_tool import select_optimization_profile

    manifest = json.loads((corpus_dir / "CORPUS_MANIFEST.json").read_text(encoding="utf-8"))
    results: list[dict[str, object]] = []
    strict_matches = 0
    ambiguity_hits = 0
    for entry in manifest["entries"]:
        samples, rate = sf.read(str(corpus_dir / entry["path"]), dtype="float64", always_2d=False)
        if samples.ndim != 1:
            raise RuntimeError(f"corpus sample is not mono: {entry['path']}")
        # The analytical classifier is evaluated on a deterministic 1.5 s, 16 kHz view.
        analysis = _resample_linear(samples[: int(rate * 1.5)], int(rate), 16_000)
        bundle = build_bundle(analysis, 16_000)
        selection = select_optimization_profile(bundle.musical, bundle.mode)
        ranked = sorted(selection.scores, key=lambda item: (-item.score, item.profile.value))
        result = {
            "id": entry["id"], "kind": entry["kind"],
            "selected_profile": selection.selected_profile.value,
            "confidence": selection.confidence, "ambiguity": selection.ambiguity,
            "selected_musical_classes": [item.value for item in bundle.musical.selected_classes],
            "conversion_mode": None if bundle.mode.selected_mode is None else bundle.mode.selected_mode.value,
            "top_profiles": [{"profile": item.profile.value, "score": item.score} for item in ranked[:4]],
            "selection_sha256": selection.analysis_sha256,
        }
        if entry["kind"] == "profile":
            result["expected_profile"] = entry["expected_profile"]
            result["strict_match"] = selection.selected_profile.value == entry["expected_profile"]
            strict_matches += int(result["strict_match"])
        else:
            expected = tuple(entry["expected_profiles"])
            top2 = tuple(item.profile.value for item in ranked[:2])
            result["expected_profiles"] = list(expected)
            result["top2_contains_expected_pair"] = set(expected).issubset(set(item.profile.value for item in ranked[:4]))
            ambiguity_hits += int(result["top2_contains_expected_pair"])
        results.append(result)
    report: dict[str, object] = {
        "schema_version": 1, "corpus_sha256": manifest["corpus_sha256"],
        "strict_profile_matches": strict_matches, "strict_profile_total": 27,
        "ambiguity_pair_hits_top4": ambiguity_hits, "ambiguity_total": 5,
        "results": results,
        "interpretation": (
            "Mismatches do not automatically prove a profile-selector defect: they locate corpus/profile boundaries. "
            "A code correction is authorized only when direct class-vector tests and repeated real-source evidence agree."
        ),
    }
    report["analysis_sha256"] = canonical_hash(report)
    write_json(output_path, report)
    return report


def _matrix_build_n(repo: Path, n: int):
    configure_repo_imports(repo)
    from dataclasses import replace as dc_replace
    from v8a_helpers import complete_build, metrics, samples
    from v8j_helpers import complete_v8i_analysis, complete_source, validated_empty_signature
    from w_mwxt_wavetable_tool import (
        WaveRole, GenerationMethod, WaveOrigin, consolidate_wavetable_build,
        analyze_xt_memory_inventory, build_code_v8j, build_code_v8k,
        UserWavetableDestination, DeviceAddress,
    )
    from w_mwxt_wavetable_tool.wavetable.consolidation import ConsolidationPolicy

    base = complete_build(f"v51-n-{n}")
    unique = [samples(5 + index * 11) for index in range(n)]
    slots = []
    for position, slot in enumerate(base.slots):
        group = min(n - 1, (position * n) // 61)
        slots.append(dc_replace(
            slot,
            stored_samples=unique[group],
            role=(WaveRole.ESSENTIAL if position == 0 else WaveRole.STABLE),
            origin=WaveOrigin.REAL_CYCLE,
            generation_method=GenerationMethod.SOURCE_CYCLE,
            structural=(position == 0), transition=False, redundant=False, locked=False,
            source_candidate_ids=(f"v51-n{n}-wave-{group:02d}",),
            metrics=metrics(group / 1000.0),
            reason=f"V5.1 N={n} deterministic logical group {group}.",
        ))
    build = dc_replace(base, slots=tuple(slots), reason=f"V5.1 deterministic N={n} consolidation fixture.")
    policy = ConsolidationPolicy(
        protect_locked=False, protect_essential=False, protect_breakpoint=False, protect_structural=False,
    )
    consolidation = consolidate_wavetable_build(build, policy)
    if consolidation.physical_wave_set is None or consolidation.physical_wave_set.physical_wave_count != n:
        raise RuntimeError(f"N={n}: consolidation produced unexpected physical count")
    base_v8i = complete_v8i_analysis()
    variant = dc_replace(
        base_v8i.variants[0], consolidation=consolidation, physical_wave_count=n,
        compression_ratio=round((61 - n) / 60.0, 12), reason=f"V5.1 N={n} matrix variant.",
    )
    v8i = dc_replace(base_v8i, variants=(variant,), primary_variant_id=variant.variant_id, reason=f"V5.1 N={n} matrix analysis.")
    inventory = analyze_xt_memory_inventory(
        (complete_source(empty_numbers=tuple(range(1100, 1100 + n))),),
        empty_wave_signature=validated_empty_signature(),
    )
    v8j = build_code_v8j(v8i, inventory, UserWavetableDestination(128))
    if not v8j.allocation_ready:
        raise RuntimeError(f"N={n}: V8-J allocation unexpectedly blocked")
    v8k = build_code_v8k(v8i, v8j, build.fixed_tail, DeviceAddress(0))
    if v8k.dense_package is None or v8k.sparse_package_candidate is None:
        raise RuntimeError(f"N={n}: V8-K did not produce dense and sparse candidate packages")
    return build, consolidation, v8i, v8j, v8k


def run_v8_offline_matrix(repo: Path, output_dir: Path, *, include_deep_250: bool = False) -> dict[str, object]:
    configure_repo_imports(repo)
    output_dir.mkdir(parents=True, exist_ok=True)
    from v8c_selection_helpers import corpus, selection_for
    from v8d_placement_helpers import ordered_context
    from v8h_helpers import v8h_context
    from w_mwxt_wavetable_tool import OrderingStrategy, PlacementBias

    selection_results = []
    candidate_counts = (1, 2, 8, 61, 62, 250) if include_deep_250 else (1, 2, 8, 61, 62)
    for count in candidate_counts:
        request, v8b, v8c = selection_for(corpus(count))
        selection_results.append({
            "candidate_count": count, "request_sha256": request.analysis_sha256,
            "v8b_sha256": v8b.analysis_sha256, "v8c_status": v8c.status.value,
            "selected_count": 0 if v8c.selection is None else len(v8c.selection.selected_candidate_ids),
            "blockers": [] if v8c.selection is None else list(v8c.selection.blockers),
        })

    placement_results = []
    for strategy in OrderingStrategy:
        for bias in PlacementBias:
            request, v8b, v8c, ordering, placement = ordered_context(8, strategy=strategy, bias=bias)
            placement_results.append({
                "strategy": strategy.value, "bias": bias.value,
                "ordering_status": ordering.status.value, "placement_status": placement.status.value,
                "positions": [item.position for item in placement.assignments],
                "ordering_sha256": ordering.analysis_sha256,
                "placement_sha256": placement.analysis_sha256,
            })

    factory_results = []
    for profile in PROFILE_NAMES:
        request, v8b, v8c, v8d, regions = v8h_context(profile=profile, requested_variants=3)
        from w_mwxt_wavetable_tool import build_code_v8h
        v8h = build_code_v8h(request, v8b, v8c, v8d, regions)
        factory_results.append({
            "profile": profile, "status": v8h.status.value,
            "variant_count": len(v8h.variants), "primary_variant": v8h.primary_variant_id,
            "analysis_sha256": v8h.analysis_sha256,
            "slot_positions": [slot.position for slot in v8h.variants[0].build.slots] if v8h.variants else [],
        })

    n_results = []
    for n in N_MATRIX:
        build, consolidation, v8i, v8j, v8k = _matrix_build_n(repo, n)
        case_dir = output_dir / f"N_{n:02d}"
        case_dir.mkdir(exist_ok=True)
        dense_syx, dense_manifest = v8k.dense_package.write(case_dir, stem=f"V51_OFFLINE_N_{n:02d}_DENSE_DO_NOT_SEND")
        sparse_syx, sparse_manifest = v8k.sparse_package_candidate.write(case_dir, stem=f"V51_OFFLINE_N_{n:02d}_SPARSE_CANDIDATE_DO_NOT_SEND")
        n_results.append({
            "n": n,
            "logical_positions": 61,
            "physical_wave_count": consolidation.physical_wave_set.physical_wave_count,
            "mapping": list(consolidation.mapping.logical_to_physical),
            "v8i_sha256": v8i.analysis_sha256,
            "v8j_sha256": v8j.analysis_sha256,
            "dense": {"path": str(dense_syx.relative_to(output_dir)), "sha256": file_hash(dense_syx), "message_count": v8k.dense_package.manifest.message_count},
            "sparse": {"path": str(sparse_syx.relative_to(output_dir)), "sha256": file_hash(sparse_syx), "message_count": v8k.sparse_package_candidate.manifest.message_count, "enabled": False},
            "dense_references": list(v8k.wctd_materialization.dense.references[:61]),
            "sparse_references": list(v8k.wctd_materialization.sparse_candidate.references[:61]),
        })

    report: dict[str, object] = {
        "schema_version": 1,
        "selection_matrix": selection_results,
        "deep_250_executed": include_deep_250,
        "ordering_placement_matrix": placement_results,
        "factory_profile_matrix": factory_results,
        "consolidation_materialization_package_matrix": n_results,
        "boundaries": {
            "offline_packages_are_synthetic_fixtures": True,
            "offline_packages_must_not_be_sent": True,
            "automatic_midi": False,
            "automatic_memory_write": False,
        },
    }
    report["analysis_sha256"] = canonical_hash(report)
    write_json(output_dir / "V8_OFFLINE_MATRIX_REPORT.json", report)
    return report


def build_fixed_position_midi(positions: Sequence[int], notes: Sequence[int] = (48, 60, 72), velocity: int = 100) -> tuple[bytes, dict[str, object]]:
    division = 480
    tempo = 500_000
    def varlen(value: int) -> bytes:
        buffer = value & 0x7F
        out = bytearray((buffer,))
        value >>= 7
        while value:
            out.insert(0, (value & 0x7F) | 0x80)
            value >>= 7
        return bytes(out)
    def ticks(seconds: float) -> int:
        return int(round(seconds * division * 1_000_000 / tempo))
    events = []
    blocks = []
    cursor = 2.0
    order = 0
    for position in positions:
        for note in notes:
            events.append((cursor, order, bytes((0xB0, 71, position)))); order += 1
            start = cursor + 0.1
            end = start + 1.5
            events.append((start, order, bytes((0x90, note, velocity)))); order += 1
            events.append((end, order, bytes((0x80, note, 0)))); order += 1
            blocks.append({"position": position, "midi_note": note, "start": start, "end": end})
            cursor = end + 0.5
    ordered = sorted(events, key=lambda item: (item[0], item[1]))
    track = bytearray()
    track += varlen(0) + b"\xFF\x51\x03" + tempo.to_bytes(3, "big")
    previous = 0
    for seconds, _, raw in ordered:
        tick = ticks(seconds)
        track += varlen(tick-previous) + raw
        previous = tick
    track += varlen(0) + b"\xFF\x2F\x00"
    midi = b"MThd" + struct.pack(">IHHH", 6, 0, 1, division) + b"MTrk" + struct.pack(">I", len(track)) + bytes(track)
    manifest = {"controller": 71, "positions": list(positions), "notes": list(notes), "velocity": velocity, "blocks": blocks, "contains_sysex": False, "allowed_cc": [71], "midi_sha256": sha256(midi).hexdigest()}
    return midi, manifest


def build_sweep_midi(step_seconds: float = 0.20, note: int = 60, velocity: int = 100) -> tuple[bytes, dict[str, object]]:
    division = 480; tempo = 500_000
    def varlen(value: int) -> bytes:
        buffer = value & 0x7F; out = bytearray((buffer,)); value >>= 7
        while value: out.insert(0, (value & 0x7F) | 0x80); value >>= 7
        return bytes(out)
    def ticks(seconds: float) -> int: return int(round(seconds * division * 1_000_000 / tempo))
    cursor = 2.0; order = 0; events=[]; schedule=[]
    events.append((cursor, order, bytes((0xB0,71,0)))); order += 1
    start = cursor + 0.1; events.append((start, order, bytes((0x90,note,velocity)))); order += 1; cursor=start
    for value in tuple(range(61)) + tuple(range(59,-1,-1)):
        events.append((cursor, order, bytes((0xB0,71,value)))); order += 1
        schedule.append({"time": cursor, "position": value}); cursor += step_seconds
    end=cursor+0.2; events.append((end,order,bytes((0x80,note,0))))
    track=bytearray(); track += varlen(0)+b"\xFF\x51\x03"+tempo.to_bytes(3,"big"); previous=0
    for seconds,_,raw in sorted(events,key=lambda item:(item[0],item[1])):
        tick=ticks(seconds); track += varlen(tick-previous)+raw; previous=tick
    track += varlen(0)+b"\xFF\x2F\x00"
    midi=b"MThd"+struct.pack(">IHHH",6,0,1,division)+b"MTrk"+struct.pack(">I",len(track))+bytes(track)
    return midi,{"controller":71,"positions":"0..60..0","note":note,"velocity":velocity,"step_seconds":step_seconds,"schedule":schedule,"contains_sysex":False,"allowed_cc":[71],"midi_sha256":sha256(midi).hexdigest()}


__all__ = [
    "PROFILE_NAMES", "CORPUS_VARIANTS", "N_MATRIX", "generate_profile_corpus",
    "analyze_profile_corpus", "run_v8_offline_matrix", "build_fixed_position_midi",
    "build_sweep_midi", "file_hash", "write_json", "canonical_hash", "configure_repo_imports",
]


def direct_profile_route_matrix(repo: Path, output_path: Path) -> dict[str, object]:
    """Exercise the nine explicit profile-selector routes and override behavior.

    This is a contract test of the selector. It is intentionally separate from
    audio classification: a synthetic WAV can be ambiguous even when the route
    from a confirmed musical class to a profile is correct.
    """
    configure_repo_imports(repo)
    from types import SimpleNamespace
    from w_mwxt_wavetable_tool import select_optimization_profile
    from w_mwxt_wavetable_tool.decision.models import MusicalClass, ConversionMode
    from w_mwxt_wavetable_tool.profiles import OptimizationProfile

    def classification(selected):
        return SimpleNamespace(
            analysis_sha256="1" * 64,
            scores=tuple(SimpleNamespace(musical_class=item, score=1.0 if item is selected else 0.0) for item in MusicalClass),
            selected_classes=(selected,),
        )

    def mode_decision():
        return SimpleNamespace(analysis_sha256="2" * 64, selected_mode=ConversionMode.STABLE_CYCLE)

    routes = (
        (MusicalClass.SUB, OptimizationProfile.BASS_SUB),
        (MusicalClass.LEAD, OptimizationProfile.LEAD),
        (MusicalClass.PAD, OptimizationProfile.PAD),
        (MusicalClass.BELL, OptimizationProfile.BELL_FM),
        (MusicalClass.VOCAL, OptimizationProfile.VOCAL_CHOIR),
        (MusicalClass.TEXTURE, OptimizationProfile.TEXTURE),
        (MusicalClass.DRONE, OptimizationProfile.DRONE),
        (MusicalClass.PERCUSSION, OptimizationProfile.PERCUSSIVE),
        (MusicalClass.FX, OptimizationProfile.EXPERIMENTAL),
    )
    rows = []
    for musical_class, expected in routes:
        result = select_optimization_profile(
            classification(musical_class), mode_decision(), mode_prior_cap=0.0
        )
        rows.append({
            "musical_class": musical_class.value,
            "expected_profile": expected.value,
            "selected_profile": result.selected_profile.value,
            "pass": result.selected_profile is expected,
            "analysis_sha256": result.analysis_sha256,
        })
    automatic = select_optimization_profile(
        classification(MusicalClass.SUB), mode_decision(),
        requested_override=OptimizationProfile.EXPERIMENTAL,
    )
    report = {
        "schema_version": 1,
        "routes": rows,
        "route_pass_count": sum(bool(item["pass"]) for item in rows),
        "route_total": len(rows),
        "override": {
            "automatic_evidence_class": MusicalClass.SUB.value,
            "requested": OptimizationProfile.EXPERIMENTAL.value,
            "selected": automatic.selected_profile.value,
            "pass": automatic.selected_profile is OptimizationProfile.EXPERIMENTAL,
        },
        "scope": "Confirmed-class to optimization-profile contract; this does not replace audio classification validation.",
    }
    report["analysis_sha256"] = canonical_hash(report)
    write_json(output_path, report)
    return report


def _group_mapping(n: int, style: str = "uniform") -> tuple[int, ...]:
    if not 1 <= n <= 61:
        raise ValueError("n must be in 1..61")
    if n == 1:
        return (0,) * 61
    if style == "uniform":
        anchors = np.linspace(0, 60, n)
    elif style == "early":
        anchors = 60.0 * np.linspace(0, 1, n) ** 2.2
    elif style == "late":
        anchors = 60.0 * (1.0 - (1.0 - np.linspace(0, 1, n)) ** 2.2)
    elif style == "center":
        x = np.linspace(-1, 1, n)
        anchors = 30.0 + 30.0 * np.sign(x) * (np.abs(x) ** 1.8)
    elif style == "asymmetric":
        base = np.linspace(0, 1, n)
        anchors = 60.0 * (0.65 * base**1.7 + 0.35 * base)
    elif style == "reverse":
        return tuple(reversed(_group_mapping(n, "uniform")))
    else:
        raise ValueError(f"unknown mapping style: {style}")
    anchors = np.asarray(np.rint(anchors), dtype=np.int64)
    anchors[0] = 0
    anchors[-1] = 60
    # Guarantee strictly increasing anchors by deterministic repair.
    for index in range(1, anchors.size):
        anchors[index] = max(anchors[index], anchors[index - 1] + 1)
    for index in range(anchors.size - 2, -1, -1):
        anchors[index] = min(anchors[index], anchors[index + 1] - 1)
    positions = np.arange(61, dtype=np.int64)
    distances = np.abs(positions[:, None] - anchors[None, :])
    mapping = np.argmin(distances, axis=1)
    return tuple(int(value) for value in mapping)


def _build_case_analysis(repo: Path, mapping: Sequence[int], label: str):
    configure_repo_imports(repo)
    from dataclasses import replace as dc_replace
    from v8a_helpers import complete_build, metrics, samples
    from v8j_helpers import complete_v8i_analysis
    from w_mwxt_wavetable_tool import WaveRole, GenerationMethod, WaveOrigin, consolidate_wavetable_build
    from w_mwxt_wavetable_tool.wavetable.consolidation import ConsolidationPolicy

    groups = tuple(int(value) for value in mapping)
    if len(groups) != 61 or min(groups) != 0:
        raise ValueError("mapping must cover 61 positions and start at group 0")
    used = tuple(sorted(set(groups)))
    if used != tuple(range(len(used))):
        raise ValueError("mapping physical groups must be canonical 0..N-1")
    n = len(used)
    unique = [samples(5 + index * 11) for index in range(n)]
    base = complete_build(label)
    slots = []
    for position, (slot, group) in enumerate(zip(base.slots, groups, strict=True)):
        first = groups.index(group)
        role = WaveRole.ESSENTIAL if position in {0, 60} else (WaveRole.STRUCTURAL if position == first else WaveRole.REDUNDANT)
        slots.append(dc_replace(
            slot,
            stored_samples=unique[group],
            role=role,
            origin=WaveOrigin.REAL_CYCLE,
            generation_method=GenerationMethod.SOURCE_CYCLE,
            structural=role in {WaveRole.ESSENTIAL, WaveRole.STRUCTURAL},
            transition=False,
            redundant=role is WaveRole.REDUNDANT,
            locked=False,
            source_candidate_ids=(f"{label}-wave-{group:02d}",),
            metrics=metrics(group / 1000.0),
            reason=f"V5.1 hardware validation case {label}; logical position {position}, physical group {group}.",
        ))
    build = dc_replace(base, slots=tuple(slots), reason=f"V5.1 hardware validation case {label}.")
    policy = ConsolidationPolicy(
        protect_locked=False,
        protect_essential=False,
        protect_breakpoint=False,
        protect_structural=False,
    )
    consolidation = consolidate_wavetable_build(build, policy)
    if consolidation.physical_wave_set is None or consolidation.mapping is None:
        raise RuntimeError(f"{label}: consolidation rejected")
    if consolidation.physical_wave_set.physical_wave_count != n:
        raise RuntimeError(f"{label}: expected {n} physical waves, got {consolidation.physical_wave_set.physical_wave_count}")
    actual = tuple(consolidation.mapping.logical_to_physical)
    # Exact group IDs may be canonicalized by first appearance; compare equality pattern.
    expected_equivalence = tuple(tuple(index for index, value in enumerate(groups) if value == group) for group in used)
    actual_equivalence = tuple(consolidation.mapping.physical_to_logical)
    if set(expected_equivalence) != set(actual_equivalence):
        raise RuntimeError(f"{label}: consolidation groups differ from requested mapping")

    base_v8i = complete_v8i_analysis()
    variant = dc_replace(
        base_v8i.variants[0],
        consolidation=consolidation,
        physical_wave_count=n,
        compression_ratio=round((61 - n) / 60.0, 12),
        reason=f"V5.1 hardware case {label}.",
    )
    v8i = dc_replace(
        base_v8i,
        variants=(variant,),
        primary_variant_id=variant.variant_id,
        reason=f"V5.1 hardware case {label} V8-I analysis.",
    )
    return build, consolidation, v8i


def build_actual_hardware_case_matrix(
    repo: Path,
    backup_everything: Path,
    foundation_dense_package: Path,
    output_dir: Path,
    *,
    user_wave_start: int,
    wavetable_display_number: int = 126,
    device_id: int = 0,
    include_n_and_placement: bool = True,
    profile_names: Sequence[str] = (),
) -> dict[str, object]:
    """Build real-address V8-K N+1 packages and N+2 diagnostic carriers.

    The N+1 files are the actual V8-K product contract. The N+2 files append the
    already controlled neutral SNDD from the foundation campaign only for audio
    measurement. They are explicitly labelled diagnostic and do not claim V9.
    """
    configure_repo_imports(repo)
    if not 1000 <= user_wave_start <= 1189:
        raise ValueError("user_wave_start must allow a 61-wave block inside 1000..1249")
    output_dir.mkdir(parents=True, exist_ok=True)
    from w_mwxt_wavetable_tool import (
        DumpFile, DumpType, InventoryDumpSource, InventorySourceKind,
        analyze_xt_memory_inventory, UserWavetable, FixedTailContract,
        SafeAllocationPolicy, UserWavetableDestination, DeviceAddress,
        build_code_v8j, build_code_v8k, CodeV8KPolicy,
    )

    baseline = DumpFile.from_path(backup_everything)
    source = InventoryDumpSource(
        source_id="v51-current-everything",
        source_kind=InventorySourceKind.BACKUP_EVERYTHING,
        dump=baseline,
        captured_current_state=True,
    )
    inventory = analyze_xt_memory_inventory((source,))
    if not inventory.evidence_status.user_wave_coverage_complete or not inventory.evidence_status.user_wavetable_coverage_complete:
        raise RuntimeError("Backup Everything does not prove complete 250-wave / 32-wavetable coverage")

    wt_internal = wavetable_display_number - 1
    wt_messages = [m for m in baseline.messages if int(m.dump_type) == int(DumpType.USER_WAVETABLE) and m.address == wt_internal]
    if len(wt_messages) != 1:
        raise RuntimeError("Original WCTD destination not found uniquely in Backup Everything")
    original_wt = UserWavetable.from_message(wt_messages[0])
    fixed_tail = FixedTailContract(
        schema_version=1,
        source_wctd_sha256=sha256(wt_messages[0].to_bytes()).hexdigest(),
        references=tuple(original_wt.references[61:64]),
        reason="Preserve the exact three fixed-tail references from the initial hardware backup.",
    )

    foundation = DumpFile.from_path(foundation_dense_package)
    sound_messages = [m for m in foundation.messages if int(m.dump_type) == int(DumpType.SOUND)]
    if len(sound_messages) != 1:
        raise RuntimeError("Foundation package must contain exactly one controlled SNDD")
    sound_message = sound_messages[0]
    if len(sound_message.payload) <= 25 or sound_message.payload[25] != wt_internal:
        raise RuntimeError("Foundation SNDD does not select the requested User Wavetable")

    all_numbers = tuple(range(user_wave_start, user_wave_start + 61))
    cases: list[tuple[str, tuple[int, ...], str]] = []
    if include_n_and_placement:
        for n in N_MATRIX:
            cases.append((f"N_{n:02d}_UNIFORM", _group_mapping(n, "uniform"), "n_matrix"))
        for style in ("early", "late", "center", "asymmetric", "reverse"):
            cases.append((f"PLACEMENT_08_{style.upper()}", _group_mapping(8, style), "placement"))

    rows = []
    for label, mapping, family in cases:
        n = len(set(mapping))
        build, consolidation, v8i = _build_case_analysis(repo, mapping, label)
        authorized = tuple(range(user_wave_start, user_wave_start + n))
        policy = SafeAllocationPolicy(
            authorized_overwrite_numbers=authorized,
            reason=(
                "V5.1 operator-authorized exact overwrite block. Every destination is restored byte-identically at campaign end."
            ),
        )
        v8j = build_code_v8j(
            v8i,
            inventory,
            UserWavetableDestination(wavetable_display_number),
            policy,
        )
        if not v8j.allocation_ready:
            blockers = [] if v8j.allocation is None else list(v8j.allocation.blockers)
            raise RuntimeError(f"{label}: allocation blocked: {blockers}")
        v8k = build_code_v8k(
            v8i,
            v8j,
            fixed_tail,
            DeviceAddress(device_id),
            CodeV8KPolicy(package_stem=f"V51_{label}", reason="V5.1 dense active; sparse retained as candidate until hardware evidence."),
        )
        case_dir = output_dir / label
        case_dir.mkdir(exist_ok=True)
        dense_path, dense_manifest_path = v8k.dense_package.write(case_dir, stem=f"{label}_V8K_NPLUS1_DENSE")
        sparse_path, sparse_manifest_path = v8k.sparse_package_candidate.write(case_dir, stem=f"{label}_V8K_NPLUS1_SPARSE_CANDIDATE")
        diagnostic_dense = case_dir / f"{label}_DIAGNOSTIC_NPLUS2_DENSE_WITH_SNDD.syx"
        diagnostic_sparse = case_dir / f"{label}_DIAGNOSTIC_NPLUS2_SPARSE_WITH_SNDD.syx"
        diagnostic_dense.write_bytes(DumpFile(tuple(v8k.dense_package.dump.messages) + (sound_message,)).to_bytes())
        diagnostic_sparse.write_bytes(DumpFile(tuple(v8k.sparse_package_candidate.dump.messages) + (sound_message,)).to_bytes())
        fixed_midi, fixed_manifest = build_fixed_position_midi((0, 10, 20, 30, 40, 50, 60))
        sweep_midi, sweep_manifest = build_sweep_midi()
        (case_dir / "FIXED_POSITIONS_CC71.mid").write_bytes(fixed_midi)
        (case_dir / "SWEEP_0_60_0_CC71.mid").write_bytes(sweep_midi)
        write_json(case_dir / "FIXED_POSITIONS_CC71.json", fixed_manifest)
        write_json(case_dir / "SWEEP_0_60_0_CC71.json", sweep_manifest)
        case_report = {
            "label": label,
            "family": family,
            "n": n,
            "logical_to_physical": list(consolidation.mapping.logical_to_physical),
            "physical_to_logical": [list(x) for x in consolidation.mapping.physical_to_logical],
            "authorized_wave_numbers": list(authorized),
            "wavetable_display_number": wavetable_display_number,
            "sound_address": sound_message.address,
            "dense_nplus1": {"path": dense_path.name, "sha256": file_hash(dense_path), "message_count": len(v8k.dense_package.dump.messages)},
            "sparse_nplus1_candidate": {"path": sparse_path.name, "sha256": file_hash(sparse_path), "message_count": len(v8k.sparse_package_candidate.dump.messages), "send_only_after_foundation_sparse_pass": True},
            "diagnostic_dense_nplus2": {"path": diagnostic_dense.name, "sha256": file_hash(diagnostic_dense), "message_count": len(v8k.dense_package.dump.messages) + 1},
            "diagnostic_sparse_nplus2": {"path": diagnostic_sparse.name, "sha256": file_hash(diagnostic_sparse), "message_count": len(v8k.sparse_package_candidate.dump.messages) + 1, "send_only_after_foundation_sparse_pass": True},
            "v8i_sha256": v8i.analysis_sha256,
            "v8j_sha256": v8j.analysis_sha256,
            "v8k_sha256": v8k.analysis_sha256,
            "boundaries": {"product_contract": "N WAVD + 1 WCTD", "diagnostic_carrier": "N WAVD + 1 WCTD + controlled SNDD", "v9_claim": False},
        }
        case_report["case_sha256"] = canonical_hash(case_report)
        write_json(case_dir / "CASE.json", case_report)
        rows.append(case_report)

    # Nine V8-H profile-policy consequences use the repository's actual profile-driven
    # placement/interpolation path. They are deterministic policy fixtures, not claims
    # that a synthetic WAV was classified perfectly.
    from v8h_helpers import v8h_context
    from w_mwxt_wavetable_tool import build_code_v8h, build_code_v8i
    selected_profiles = tuple(profile_names)
    if any(item not in PROFILE_NAMES for item in selected_profiles):
        raise ValueError("profile_names contains an unknown profile")
    for profile_name in selected_profiles:
        label = f"PROFILE_POLICY_{profile_name.upper()}"
        request, v8b, v8c, v8d, regions = v8h_context(profile=profile_name, requested_variants=1)
        v8h = build_code_v8h(request, v8b, v8c, v8d, regions)
        v8i = build_code_v8i(v8h)
        if not v8i.variants or v8i.primary_variant is None:
            raise RuntimeError(f"{label}: V8-I did not produce a primary variant")
        n = v8i.primary_variant.physical_wave_count
        if user_wave_start + n - 1 > 1249:
            raise RuntimeError(f"{label}: reservation does not fit {n} physical waves")
        policy = SafeAllocationPolicy(
            authorized_overwrite_numbers=tuple(range(user_wave_start, user_wave_start + n)),
            reason="V5.1 profile-policy fixture using the operator-authorized exact overwrite block.",
        )
        v8j = build_code_v8j(v8i, inventory, UserWavetableDestination(wavetable_display_number), policy)
        if not v8j.allocation_ready:
            raise RuntimeError(f"{label}: V8-J allocation blocked")
        v8k = build_code_v8k(
            v8i, v8j, fixed_tail, DeviceAddress(device_id),
            CodeV8KPolicy(package_stem=f"V51_{label}", reason="V5.1 V8-H profile-policy hardware consequence fixture."),
        )
        case_dir = output_dir / label
        case_dir.mkdir(exist_ok=True)
        dense_path, _ = v8k.dense_package.write(case_dir, stem=f"{label}_V8K_NPLUS1_DENSE")
        sparse_path, _ = v8k.sparse_package_candidate.write(case_dir, stem=f"{label}_V8K_NPLUS1_SPARSE_CANDIDATE")
        diagnostic_dense = case_dir / f"{label}_DIAGNOSTIC_NPLUS2_DENSE_WITH_SNDD.syx"
        diagnostic_sparse = case_dir / f"{label}_DIAGNOSTIC_NPLUS2_SPARSE_WITH_SNDD.syx"
        diagnostic_dense.write_bytes(DumpFile(tuple(v8k.dense_package.dump.messages) + (sound_message,)).to_bytes())
        diagnostic_sparse.write_bytes(DumpFile(tuple(v8k.sparse_package_candidate.dump.messages) + (sound_message,)).to_bytes())
        fixed_midi, fixed_manifest = build_fixed_position_midi((0, 10, 20, 30, 40, 50, 60))
        sweep_midi, sweep_manifest = build_sweep_midi()
        (case_dir / "FIXED_POSITIONS_CC71.mid").write_bytes(fixed_midi)
        (case_dir / "SWEEP_0_60_0_CC71.mid").write_bytes(sweep_midi)
        write_json(case_dir / "FIXED_POSITIONS_CC71.json", fixed_manifest)
        write_json(case_dir / "SWEEP_0_60_0_CC71.json", sweep_manifest)
        case_report = {
            "label": label, "family": "profile_policy", "profile": profile_name, "n": n,
            "authorized_wave_numbers": list(range(user_wave_start, user_wave_start + n)),
            "wavetable_display_number": wavetable_display_number, "sound_address": sound_message.address,
            "dense_nplus1": {"path": dense_path.name, "sha256": file_hash(dense_path), "message_count": len(v8k.dense_package.dump.messages)},
            "sparse_nplus1_candidate": {"path": sparse_path.name, "sha256": file_hash(sparse_path), "message_count": len(v8k.sparse_package_candidate.dump.messages), "send_only_after_foundation_sparse_pass": True},
            "diagnostic_dense_nplus2": {"path": diagnostic_dense.name, "sha256": file_hash(diagnostic_dense), "message_count": len(v8k.dense_package.dump.messages)+1},
            "diagnostic_sparse_nplus2": {"path": diagnostic_sparse.name, "sha256": file_hash(diagnostic_sparse), "message_count": len(v8k.sparse_package_candidate.dump.messages)+1, "send_only_after_foundation_sparse_pass": True},
            "v8h_sha256": v8h.analysis_sha256, "v8i_sha256": v8i.analysis_sha256,
            "v8j_sha256": v8j.analysis_sha256, "v8k_sha256": v8k.analysis_sha256,
            "boundaries": {"policy_fixture": True, "source_audio_classification": False, "v9_claim": False},
        }
        case_report["case_sha256"] = canonical_hash(case_report)
        write_json(case_dir / "CASE.json", case_report)
        rows.append(case_report)

    restore_messages = []
    for number in all_numbers:
        matches = [m for m in baseline.messages if int(m.dump_type) == int(DumpType.USER_WAVE) and m.address == number]
        if len(matches) != 1:
            raise RuntimeError(f"Original WAVD {number} not found uniquely")
        restore_messages.append(matches[0])
    restore_messages.append(wt_messages[0])
    original_sound_matches = [m for m in baseline.messages if int(m.dump_type) == int(DumpType.SOUND) and m.address == sound_message.address]
    if len(original_sound_matches) != 1:
        raise RuntimeError("Original Sound destination not found uniquely")
    restore_messages.append(original_sound_matches[0])
    restore_path = output_dir / "RESTORE_EXACT_61_WAVD_WCTD_SNDD.syx"
    restore_path.write_bytes(DumpFile(tuple(restore_messages)).to_bytes())

    report = {
        "schema_version": 1,
        "backup_everything": {"path": str(backup_everything), "sha256": file_hash(backup_everything)},
        "foundation_dense_package": {"path": str(foundation_dense_package), "sha256": file_hash(foundation_dense_package)},
        "reservation": {"user_wave_start": user_wave_start, "user_wave_end": user_wave_start + 60, "wavetable_display_number": wavetable_display_number, "sound_address": sound_message.address},
        "case_count": len(rows),
        "include_n_and_placement": include_n_and_placement,
        "profile_names": list(selected_profiles),
        "cases": rows,
        "restore": {"path": restore_path.name, "sha256": file_hash(restore_path), "message_count": len(restore_messages)},
        "safety": {"automatic_midi": False, "automatic_write": False, "explicit_overwrite_authorization_required": True, "restore_required": True},
    }
    report["analysis_sha256"] = canonical_hash(report)
    write_json(output_dir / "HARDWARE_CASE_MATRIX.json", report)
    return report


# Extend the public list without changing earlier exports.
__all__ += [
    "direct_profile_route_matrix", "build_actual_hardware_case_matrix",
]
