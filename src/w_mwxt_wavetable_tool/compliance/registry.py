from __future__ import annotations

from importlib.resources import files
import json
from pathlib import Path
from typing import Any

from .models import ComplianceFormatError, ComplianceRegistry, canonical_json_bytes


REGISTRY_RESOURCE = "data/cdc_traceability_v1.json"


def load_compliance_registry() -> ComplianceRegistry:
    resource = files(__package__).joinpath("data").joinpath("cdc_traceability_v1.json")
    try:
        payload = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ComplianceFormatError(f"Cannot load bundled compliance registry: {exc}") from exc
    return ComplianceRegistry.from_dict(payload)


def load_compliance_registry_file(path: str | Path) -> ComplianceRegistry:
    source = Path(path)
    try:
        payload: Any = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ComplianceFormatError(f"Cannot load compliance registry {source}: {exc}") from exc
    return ComplianceRegistry.from_dict(payload)


def write_compliance_registry(
    registry: ComplianceRegistry, path: str | Path, *, overwrite: bool = False
) -> Path:
    destination = Path(path)
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(canonical_json_bytes(registry.to_dict()))
    return destination
