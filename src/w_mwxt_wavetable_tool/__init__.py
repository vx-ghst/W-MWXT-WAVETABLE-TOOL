"""Public API for W-MWXT-WAVETABLE-TOOL."""

from .allocation import UserWaveAllocation, allocate_user_waves
from .audio import (
    AudioContainerFormat,
    AudioMeasurements,
    AudioMetadata,
    AudioSource,
    InvalidSamplePolicy,
    MonoConversionReport,
    MonoPolicy,
    MonoStrategy,
    convert_to_mono,
    fingerprint_file,
    import_audio,
    measure_mono,
    normalize_float_samples,
    supported_extensions,
)
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
    "AudioContainerFormat",
    "AudioMeasurements",
    "AudioMetadata",
    "AudioSource",
    "ComparisonStatus",
    "CollisionReport",
    "DeviceAddress",
    "DumpFile",
    "DumpType",
    "GlobalParameters",
    "HardwarePackageProfile",
    "HardwarePreparation",
    "HardwarePreflightReport",
    "HardwareReadbackReport",
    "HardwareReadbackResult",
    "HardwareTestBuild",
    "HardwareTestBuildOutputPaths",
    "HardwareValidationStatus",
    "IdentityReply",
    "InvalidSamplePolicy",
    "MemoryTarget",
    "MemoryTargetKind",
    "MonoConversionReport",
    "MonoPolicy",
    "MonoStrategy",
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
    "build_hardware_test_from_backup",
    "build_package",
    "compare_hardware_readback",
    "convert_to_mono",
    "decode_typed",
    "encode_sound_name",
    "fingerprint_file",
    "import_audio",
    "inspect_hardware_package",
    "measure_mono",
    "normalize_float_samples",
    "plan_package",
    "prepare_hardware_validation",
    "split_sysex_stream",
    "supported_extensions",
]
