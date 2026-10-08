from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

from v8i_helpers import identical_build
from v8j_helpers import complete_source, complete_v8i_analysis, validated_empty_signature

from w_mwxt_wavetable_tool import (
    DeviceAddress,
    UserWavetableDestination,
    V8K_REQUIRED_HARDWARE_STEPS,
    analyze_xt_memory_inventory,
    build_code_v8j,
    build_code_v8k,
    consolidate_wavetable_build,
    load_v8k_hardware_campaign,
)


def single_wave_v8i_analysis():
    base = complete_v8i_analysis()
    consolidation = consolidate_wavetable_build(identical_build())
    variant = replace(
        base.variants[0],
        consolidation=consolidation,
        physical_wave_count=1,
        compression_ratio=round(1.0 / 61.0, 12),
        reason="Synthetic one-wave V8-I variant for repeated-reference V8-K tests.",
    )
    return replace(
        base,
        variants=(variant,),
        primary_variant_id=variant.variant_id,
        reason="Synthetic one-wave V8-I analysis for V8-K tests.",
    )


def v8k_inputs():
    v8i = single_wave_v8i_analysis()
    inventory = analyze_xt_memory_inventory(
        (complete_source(empty_numbers=tuple(range(1100, 1161))),),
        empty_wave_signature=validated_empty_signature(),
    )
    v8j = build_code_v8j(v8i, inventory, UserWavetableDestination(128))
    fixed_tail = identical_build().fixed_tail
    return v8i, v8j, fixed_tail, DeviceAddress(0)


def pending_v8k():
    return build_code_v8k(*v8k_inputs())


def write_campaign(root: Path, result=None, *, fail_step: str | None = None, wrong_dense_hash: bool = False):
    result = pending_v8k() if result is None else result
    assert result.dense_package is not None
    assert result.sparse_package_candidate is not None
    assert result.hardware_plan is not None
    artifacts = []
    steps = []
    for index, step in enumerate(V8K_REQUIRED_HARDWARE_STEPS, start=1):
        relative = f"evidence/{index:02d}_{step.value}.txt"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = f"{step.value}\nreal-artifact-fixture\n".encode()
        path.write_bytes(payload)
        artifacts.append({"path": relative, "sha256": sha256(payload).hexdigest()})
        steps.append(
            {
                "step": step.value,
                "passed": step.value != fail_step,
                "evidence_paths": [relative],
                "reason": "Fixture artifact for V8-K campaign verification.",
            }
        )
    plan = result.hardware_plan
    manifest = {
        "schema_version": 1,
        "campaign_id": "v8k-hardware-fixture",
        "device_model": "Waldorf Microwave XT",
        "os_version": "2.33",
        "dense_package_sha256": "0" * 64 if wrong_dense_hash else plan.dense_package_sha256,
        "sparse_package_sha256": plan.sparse_package_sha256,
        "inventory_sha256": plan.inventory_sha256,
        "empty_signature_sha256": plan.empty_signature_sha256,
        "artifacts": artifacts,
        "steps": steps,
        "reason": "File-backed synthetic fixture exercising the real-artifact loader; not a project hardware claim.",
    }
    (root / "campaign.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return load_v8k_hardware_campaign(root)


__all__ = [
    "single_wave_v8i_analysis",
    "v8k_inputs",
    "pending_v8k",
    "write_campaign",
]
