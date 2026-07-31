"""Public API for W-MWXT-WAVETABLE-TOOL CODE V1."""

from .constants import DumpType
from .dump import DumpFile, split_sysex_stream
from .identity import IdentityReply
from .message import SysExMessage
from .models import (
    GlobalParameters,
    MultiProgram,
    SoundProgram,
    UserWave,
    UserWavetable,
    decode_typed,
)

__version__ = "0.1.0"

__all__ = [
    "DumpFile",
    "DumpType",
    "GlobalParameters",
    "IdentityReply",
    "MultiProgram",
    "SoundProgram",
    "SysExMessage",
    "UserWave",
    "UserWavetable",
    "__version__",
    "decode_typed",
    "split_sysex_stream",
]
