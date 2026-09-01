import json

import pytest

from coach.roadmap import available_roadmaps, load_roadmap


def test_bundled_roadmap_is_available():
    assert "neetcode-150" in available_roadmaps()


def test_load_bundled_roadmap():
    rm = load_roadmap("neetcode-150")
    assert rm.id == "neetcode-150"
    assert len(rm.problems) > 0
    assert rm.problems[0].order == 0
    assert rm.problems[-1].order == len(rm.problems) - 1
    assert rm.by_title(rm.problems[0].title) is rm.problems[0]
    assert rm.by_title("not a real problem") is None
    assert len(rm.topics()) > 1


def test_unknown_roadmap_raises_with_available_ids_in_message():
    with pytest.raises(FileNotFoundError) as exc_info:
        load_roadmap("does-not-exist")
    assert "neetcode-150" in str(exc_info.value)


def test_custom_roadmap_dir_adds_new_ids(monkeypatch, tmp_path):
    custom_dir = tmp_path / "roadmaps"
    custom_dir.mkdir()
    (custom_dir / "mini.json").write_text(
        json.dumps(
            {
                "id": "mini",
                "name": "Mini Roadmap",
                "description": "A tiny roadmap for tests.",
                "topics": [
                    {
                        "name": "Basics",
                        "problems": [{"title": "Two Sum", "difficulty": "Easy"}],
                    }
                ],
            }
        )
    )
    monkeypatch.setenv("LEETCODE_COACH_ROADMAPS", str(custom_dir))

    ids = available_roadmaps()
    assert "mini" in ids
    assert "neetcode-150" in ids

    rm = load_roadmap("mini")
    assert rm.name == "Mini Roadmap"
    assert [p.title for p in rm.problems] == ["Two Sum"]


def test_custom_roadmap_overrides_bundled_id(monkeypatch, tmp_path):
    custom_dir = tmp_path / "roadmaps"
    custom_dir.mkdir()
    (custom_dir / "neetcode-150.json").write_text(
        json.dumps(
            {
                "id": "neetcode-150",
                "name": "Overridden",
                "description": "Replaces the bundled roadmap.",
                "topics": [
                    {
                        "name": "Only Topic",
                        "problems": [{"title": "Only Problem", "difficulty": "Easy"}],
                    }
                ],
            }
        )
    )
    monkeypatch.setenv("LEETCODE_COACH_ROADMAPS", str(custom_dir))

    rm = load_roadmap("neetcode-150")
    assert rm.name == "Overridden"
    assert len(rm.problems) == 1


def test_missing_custom_dir_is_ignored(monkeypatch):
    monkeypatch.setenv("LEETCODE_COACH_ROADMAPS", "/does/not/exist")
    assert "neetcode-150" in available_roadmaps()
    rm = load_roadmap("neetcode-150")
    assert rm.id == "neetcode-150"