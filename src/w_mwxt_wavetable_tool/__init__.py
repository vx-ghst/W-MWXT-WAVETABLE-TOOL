"""Public API for W-MWXT-WAVETABLE-TOOL."""

from .allocation import UserWaveAllocation, allocate_user_waves
from .constants import DumpType
from .destinations import (
    DeviceAddress,
    SoundBank,
    SoundDestination,
    SoundNamePolicy,
    UserWavetableDestination,
    encode_sound_name,
)
from .dump import DumpFile, split_sysex_stream
from .hardware_test import (
    HardwareTestBuild,
    HardwareTestBuildOutputPaths,
    build_hardware_test_from_backup,
)
from .hardware_validation import (
    ComparisonStatus,
    HardwarePackageProfile,
    HardwarePreparation,
    HardwarePreflightReport,
    HardwareReadbackReport,
    HardwareReadbackResult,
    HardwareValidationStatus,
    compare_hardware_readback,
    inspect_hardware_package,
    prepare_hardware_validation,
)
from .identity import IdentityReply
from .manifest import PackageManifest
from .message import SysExMessage
from .models import (
    GlobalParameters,
    MultiProgram,
    SoundProgram,
    UserWave,
    UserWavetable,
    decode_typed,
)
from .package import (
    PackageBuildResult,
    PackageOutputPaths,
    PackagePlan,
    PackageRequest,
    build_package,
    plan_package,
)
from .safety import (
    CollisionReport,
    MemoryTarget,
    MemoryTargetKind,
    OverwritePlan,
    analyze_collisions,
)

__version__ = "0.2.0"

__all__ = [
    "HardwareTestBuild",
    "HardwareTestBuildOutputPaths",
    "HardwareValidationStatus",
    "HardwareReadbackResult",
    "HardwareReadbackReport",
    "HardwarePreflightReport",
    "HardwarePreparation",
    "HardwarePackageProfile",
    "ComparisonStatus",
    "CollisionReport",
    "DeviceAddress",
    "DumpFile",
    "DumpType",
    "GlobalParameters",
    "IdentityReply",
    "MemoryTarget",
    "MemoryTargetKind",
    "MultiProgram",
    "OverwritePlan",
    "PackageBuildResult",
    "PackageManifest",
    "PackageOutputPaths",
    "PackagePlan",
    "PackageRequest",
    "SoundBank",
    "SoundDestination",
    "SoundNamePolicy",
    "SoundProgram",
    "SysExMessage",
    "UserWave",
    "UserWaveAllocation",
    "UserWavetable",
    "UserWavetableDestination",
    "__version__",
    "allocate_user_waves",
    "analyze_collisions",
    "build_package",
    "prepare_hardware_validation",
    "inspect_hardware_package",
    "build_hardware_test_from_backup",
    "compare_hardware_readback",
    "decode_typed",
    "encode_sound_name",
    "plan_package",
    "split_sysex_stream",
]
