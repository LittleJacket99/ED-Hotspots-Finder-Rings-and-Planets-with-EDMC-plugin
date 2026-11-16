"""Policy for the Finder's Reference System / Max Ly setting and filter."""
import math

DEFAULT_MAX_DISTANCE_LY = 50.0
MAX_ALLOWED_DISTANCE_LY = 100.0


def validate_max_distance(value):
    try:
        if isinstance(value, bool):
            raise ValueError
        distance = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Max Ly must be a number greater than 0 and no more than 100.") from None
    if not math.isfinite(distance) or not 0 < distance <= MAX_ALLOWED_DISTANCE_LY:
        raise ValueError("Max Ly must be a number greater than 0 and no more than 100.")
    return distance


def normalize_saved_distance(value):
    """Keep old configurations usable, without writing during load."""
    try:
        if isinstance(value, bool):
            raise ValueError
        distance = float(str(value).strip().replace(",", "."))
        if not math.isfinite(distance) or distance <= 0:
            raise ValueError
        return min(distance, MAX_ALLOWED_DISTANCE_LY)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_MAX_DISTANCE_LY
