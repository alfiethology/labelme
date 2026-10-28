from typing import Final

MIN_CROSSHAIR_WIDTH: Final[int] = 1
MAX_CROSSHAIR_WIDTH: Final[int] = 5
DEFAULT_CROSSHAIR_WIDTH: Final[int] = 2
DEFAULT_CROSSHAIR_COLOR: Final[tuple[int, int, int, int]] = (255, 235, 0, 255)


def clamp_crosshair_width(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("canvas.crosshair_width must be an integer")
    return max(MIN_CROSSHAIR_WIDTH, min(MAX_CROSSHAIR_WIDTH, value))
