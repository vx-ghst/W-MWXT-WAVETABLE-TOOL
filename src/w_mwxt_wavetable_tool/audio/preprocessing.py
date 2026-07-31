from __future__ import annotations

import numpy as np
import numpy.typing as npt

from .models import InvalidSamplePolicy
from ..errors import InvalidAudioDataError


def normalize_float_samples(
    samples: npt.ArrayLike,
    *,
    policy: InvalidSamplePolicy | str = InvalidSamplePolicy.REJECT,
) -> npt.NDArray[np.float64]:
    try:
        selected_policy = InvalidSamplePolicy(policy)
    except ValueError as exc:
        raise InvalidAudioDataError(f"Unknown invalid-sample policy: {policy!r}") from exc

    data = np.asarray(samples, dtype=np.float64)
    if data.ndim == 1:
        data = data[:, np.newaxis]
    if data.ndim != 2:
        raise InvalidAudioDataError(
            "Decoded audio must be one- or two-dimensional with channels on the last axis"
        )
    if data.shape[0] == 0 or data.shape[1] == 0:
        raise InvalidAudioDataError("Decoded audio must contain at least one frame and one channel")

    finite = np.isfinite(data)
    if not bool(np.all(finite)):
        if selected_policy is InvalidSamplePolicy.REJECT:
            invalid_count = int(data.size - np.count_nonzero(finite))
            raise InvalidAudioDataError(
                f"Decoded audio contains {invalid_count} NaN or infinite sample value(s)"
            )
        data = data.copy()
        data[~finite] = 0.0

    return np.ascontiguousarray(data, dtype=np.float64)
