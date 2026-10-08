from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

CROSS_SOURCE_SCHEMA_VERSION = 1
_NON_ALGORITHM_CLASSES = {"transport_or_state", "capture_or_sound_setup"}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _canonical_hash(value: Mapping[str, object]) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _classification_map(report: Mapping[str, object]) -> dict[str, list[Mapping[str, object]]]:
    result: dict[str, list[Mapping[str, object]]] = {}
    raw = report.get("repository_change_recommendations", [])
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError("repository_change_recommendations must be a sequence")
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("repository recommendation must be an object")
        classification = str(item.get("classification", "")).strip()
        if not classification:
            raise ValueError("repository recommendation has no classification")
        result.setdefault(classification, []).append(item)
    return result


def aggregate_calibration_reports(
    reference_report_path: str | Path,
    user_report_path: str | Path,
    output_directory: str | Path,
) -> tuple[Path, Path]:
    """Build a cross-source change plan without mutating repository code.

    A core-algorithm candidate is emitted only when the same algorithmic failure
    class is independently present in the deterministic reference source and in
    a user source. Transport/setup failures block interpretation. A finding that
    occurs in only one source remains source-specific evidence.
    """

    reference_path = Path(reference_report_path).expanduser().resolve(strict=True)
    user_path = Path(user_report_path).expanduser().resolve(strict=True)
    output = Path(output_directory).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    reference = _read_json(reference_path)
    user = _read_json(user_path)
    for label, report in (("reference", reference), ("user", user)):
        if int(report.get("schema_version", -1)) != 1:
            raise ValueError(f"unsupported {label} capture report schema")
        if not report.get("analysis_sha256"):
            raise ValueError(f"{label} report lacks analysis_sha256")

    reference_map = _classification_map(reference)
    user_map = _classification_map(user)
    blocking = sorted(
        classification
        for classification in set(reference_map) | set(user_map)
        if classification in _NON_ALGORITHM_CLASSES
    )
    shared = sorted(
        (set(reference_map) & set(user_map)) - _NON_ALGORITHM_CLASSES - {"measured_path_consistent"}
    )
    reference_only = sorted(
        set(reference_map) - set(user_map) - _NON_ALGORITHM_CLASSES - {"measured_path_consistent"}
    )
    user_only = sorted(
        set(user_map) - set(reference_map) - _NON_ALGORITHM_CLASSES - {"measured_path_consistent"}
    )

    candidates: list[dict[str, object]] = []
    for classification in shared:
        ref_items = reference_map[classification]
        user_items = user_map[classification]
        ref_modules = {str(module) for item in ref_items for module in item.get("modules", [])}
        user_modules = {str(module) for item in user_items for module in item.get("modules", [])}
        candidates.append(
            {
                "classification": classification,
                "status": "eligible_for_controlled_code_experiment",
                "shared_modules": sorted(ref_modules & user_modules),
                "all_modules": sorted(ref_modules | user_modules),
                "reference_actions": [str(item.get("action", "")) for item in ref_items],
                "user_actions": [str(item.get("action", "")) for item in user_items],
                "required_next_step": (
                    "Add both report/package/source hashes as private regression fixtures, "
                    "change one algorithmic variable, rebuild both campaigns, and require "
                    "improvement on both sources without a new regression."
                ),
            }
        )

    if blocking:
        status = "blocked"
        decision = "Transport or capture setup must be corrected before interpreting DSP evidence."
    elif candidates:
        status = "candidate_changes"
        decision = "Repeated cross-source evidence supports controlled repository experiments; no automatic edit is applied."
    elif str(reference.get("status")) == "pass" and str(user.get("status")) == "pass":
        status = "baseline_consistent"
        decision = "Both measured paths pass; no core-algorithm change is justified by this campaign."
    else:
        status = "source_specific_review"
        decision = "Findings are not repeated across both sources; retain them as source-specific evidence."

    document: dict[str, object] = {
        "schema_version": CROSS_SOURCE_SCHEMA_VERSION,
        "status": status,
        "decision": decision,
        "reference": {
            "path": str(reference_path),
            "analysis_sha256": reference["analysis_sha256"],
            "campaign_sha256": reference.get("campaign_sha256"),
            "source_sha256": reference.get("source_sha256"),
            "status": reference.get("status"),
        },
        "user": {
            "path": str(user_path),
            "analysis_sha256": user["analysis_sha256"],
            "campaign_sha256": user.get("campaign_sha256"),
            "source_sha256": user.get("source_sha256"),
            "status": user.get("status"),
        },
        "blocking_classes": blocking,
        "shared_algorithmic_classes": shared,
        "reference_only_classes": reference_only,
        "user_only_classes": user_only,
        "code_change_candidates": candidates,
        "change_policy": {
            "automatic_repository_edit": False,
            "minimum_independent_sources": 2,
            "one_variable_per_experiment": True,
            "repeat_hardware_capture_required": True,
            "both_sources_must_improve_or_remain_within_tolerance": True,
            "restore_and_readback_required": True,
        },
    }
    document["aggregate_sha256"] = _canonical_hash(document)

    json_path = output / "CROSS_SOURCE_REPOSITORY_CHANGE_PLAN.json"
    markdown_path = output / "CROSS_SOURCE_REPOSITORY_CHANGE_PLAN.md"
    _write_json(json_path, document)

    lines = [
        "# Plan de modification du dépôt — validation croisée",
        "",
        f"- Statut : **{status.upper()}**",
        f"- Décision : {decision}",
        f"- Rapport référence : `{reference['analysis_sha256']}`",
        f"- Rapport utilisateur : `{user['analysis_sha256']}`",
        "",
    ]
    if blocking:
        lines.extend(["## Blocages", "", *[f"- `{item}`" for item in blocking], ""])
    if candidates:
        lines.extend(["## Expériences de code admissibles", ""])
        for candidate in candidates:
            lines.extend(
                [
                    f"### {candidate['classification']}",
                    "",
                    "Modules communs : " + (
                        ", ".join(f"`{module}`" for module in candidate["shared_modules"])
                        or "aucun module commun explicite"
                    ),
                    "",
                    str(candidate["required_next_step"]),
                    "",
                ]
            )
    if reference_only or user_only:
        lines.extend(["## Résultats spécifiques à une source", ""])
        lines.append("- Référence seulement : " + (", ".join(reference_only) or "aucun"))
        lines.append("- Sample utilisateur seulement : " + (", ".join(user_only) or "aucun"))
        lines.append("")
    lines.extend(
        [
            "## Règle",
            "",
            "Aucune modification automatique du dépôt. Une modification de fond doit être testée sur les deux sources, avec nouveaux packages, read-backs et captures.",
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return json_path, markdown_path


__all__ = ["CROSS_SOURCE_SCHEMA_VERSION", "aggregate_calibration_reports"]
