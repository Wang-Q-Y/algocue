"""Roadmap loading and querying.

A roadmap is a fixed, ordered curriculum: topics in learning order, and
candidate problems within each topic in progression order. The MVP ships the
NeetCode 150 roadmap. The AI always knows where the user is and what comes next.

Roadmaps are looked up by id (the JSON filename without ``.json``) across two
directories: the bundled ``coach/data/`` and, if set, ``LEETCODE_COACH_ROADMAPS``
— a user-supplied directory of the same format. A file in the custom directory
takes precedence over a bundled one with the same id, so users can add or
override roadmaps without touching the package.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

_BUNDLED_DIR = Path(__file__).parent / "data"


def _custom_dir() -> Path | None:
    override = os.environ.get("LEETCODE_COACH_ROADMAPS")
    return Path(override) if override else None


def _search_dirs() -> list[Path]:
    """Directories to look for roadmap files in, custom dir first."""
    dirs = []
    custom = _custom_dir()
    if custom is not None and custom.is_dir():
        dirs.append(custom)
    dirs.append(_BUNDLED_DIR)
    return dirs


@dataclass(frozen=True)
class Problem:
    title: str
    topic: str
    difficulty: str
    # Global position in the roadmap's recommended order (0-based).
    order: int


@dataclass(frozen=True)
class Roadmap:
    id: str
    name: str
    description: str
    problems: list[Problem]

    def by_title(self, title: str) -> Problem | None:
        for p in self.problems:
            if p.title == title:
                return p
        return None

    def topics(self) -> list[str]:
        seen: list[str] = []
        for p in self.problems:
            if p.topic not in seen:
                seen.append(p.topic)
        return seen


def available_roadmaps() -> list[str]:
    """Return the ids of all roadmaps that can currently be loaded."""
    ids: list[str] = []
    for d in _search_dirs():
        for p in sorted(d.glob("*.json")):
            if p.stem not in ids:
                ids.append(p.stem)
    return sorted(ids)


def _find_roadmap_path(roadmap_id: str) -> Path | None:
    for d in _search_dirs():
        path = d / f"{roadmap_id}.json"
        if path.exists():
            return path
    return None


def load_roadmap(roadmap_id: str) -> Roadmap:
    """Load a roadmap by id (e.g. ``neetcode-150``)."""
    path = _find_roadmap_path(roadmap_id)
    if path is None:
        raise FileNotFoundError(
            f"Unknown roadmap {roadmap_id!r}. Available: {', '.join(available_roadmaps())}"
        )
    raw = json.loads(path.read_text())

    problems: list[Problem] = []
    order = 0
    for topic in raw["topics"]:
        for prob in topic["problems"]:
            problems.append(
                Problem(
                    title=prob["title"],
                    topic=topic["name"],
                    difficulty=prob["difficulty"],
                    order=order,
                )
            )
            order += 1

    return Roadmap(
        id=raw["id"],
        name=raw["name"],
        description=raw["description"],
        problems=problems,
    )