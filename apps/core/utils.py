"""Small, dependency-free helpers shared across apps."""
import hashlib
import math

# Level n starts at 100 * (n - 1)^2 points:
#   L1: 0   L2: 100   L3: 400   L4: 900   L5: 1600 ...
LEVEL_POINTS_UNIT = 100

LEVEL_TITLES = [
    "Seedling",
    "Sprout",
    "Sapling",
    "Grove Keeper",
    "Forest Guardian",
    "Earth Hero",
]


def calculate_level(points: int) -> int:
    """Return the level (>= 1) for a given number of points."""
    return math.isqrt(max(int(points), 0) // LEVEL_POINTS_UNIT) + 1


def points_required_for_level(level: int) -> int:
    """Minimum total points needed to reach ``level``."""
    return LEVEL_POINTS_UNIT * (max(int(level), 1) - 1) ** 2


def describe_level(points: int) -> dict:
    """Human-friendly level information for API responses."""
    points = max(int(points), 0)
    level = calculate_level(points)
    floor_points = points_required_for_level(level)
    next_level_points = points_required_for_level(level + 1)
    span = next_level_points - floor_points
    return {
        "level_title": LEVEL_TITLES[min(level - 1, len(LEVEL_TITLES) - 1)],
        "points_to_next_level": next_level_points - points,
        "level_progress_percent": round((points - floor_points) / span * 100, 1),
    }


def compute_sha256(file) -> str:
    """SHA-256 of an uploaded file; the file pointer is reset afterwards."""
    digest = hashlib.sha256()
    for chunk in file.chunks():
        digest.update(chunk)
    file.seek(0)
    return digest.hexdigest()
