from datetime import date

import coach.llm as llm
from coach.coach import Coach
from coach.store import Store


def _coach(tmp_path, today=date(2026, 9, 1)) -> Coach:
    c = Coach(store=Store(tmp_path / "state.json"), today=today)
    c.initialize("neetcode-150")
    return c


def test_is_initialized_before_and_after_init(tmp_path):
    c = Coach(store=Store(tmp_path / "state.json"))
    assert c.is_initialized() is False
    c.initialize("neetcode-150")
    assert c.is_initialized() is True


def test_plan_today_materializes_known_items_and_drops_unknown(tmp_path, monkeypatch):
    c = _coach(tmp_path)

    def fake_generate_plan(context):
        assert context["available_minutes"] == 45
        return {
            "focus": "balanced",
            "coach_note": "Let's go.",
            "items": [
                {
                    "title": "Two Sum",
                    "kind": "new",
                    "estimated_minutes": 10,
                    "reason": "warm up",
                },
                {
                    "title": "Not A Real Problem",
                    "kind": "new",
                    "estimated_minutes": 20,
                    "reason": "should be dropped",
                },
            ],
        }

    monkeypatch.setattr(llm, "generate_plan", fake_generate_plan)
    plan = c.plan_today(45)

    assert plan.focus == "balanced"
    assert plan.coach_note == "Let's go."
    assert [i.title for i in plan.items] == ["Two Sum"]
    assert plan.items[0].topic == "Arrays & Hashing"
    assert plan.total_minutes == 10


def test_record_feedback_updates_history_and_schedules_review(tmp_path, monkeypatch):
    c = _coach(tmp_path)

    def fake_parse_feedback(context):
        assert context["feedback"] == "Two Sum was easy."
        return {
            "updates": [
                {
                    "title": "Two Sum",
                    "outcome": "solved_independently",
                    "minutes": 8,
                    "used_hint": False,
                    "viewed_solution": False,
                    "notes": "instant",
                }
            ],
            "coach_note": "Nice work.",
            "unmatched": [],
        }

    monkeypatch.setattr(llm, "parse_feedback", fake_parse_feedback)
    result = c.record_feedback("Two Sum was easy.")

    assert result["coach_note"] == "Nice work."
    assert result["unmatched"] == []
    assert len(result["applied"]) == 1
    applied = result["applied"][0]
    assert applied["title"] == "Two Sum"
    assert applied["outcome"] == "solved_independently"
    assert applied["next_review"] == "2026-09-04"

    state = c.store.load()
    rec = state.records["Two Sum"]
    assert rec.solved is True
    assert rec.attempts[0].minutes == 8


def test_record_feedback_reports_titles_not_on_the_roadmap(tmp_path, monkeypatch):
    c = _coach(tmp_path)

    def fake_parse_feedback(context):
        return {
            "updates": [
                {
                    "title": "Some Made Up Problem",
                    "outcome": "solved_independently",
                    "minutes": None,
                    "used_hint": False,
                    "viewed_solution": False,
                    "notes": "",
                }
            ],
            "coach_note": "",
            "unmatched": [],
        }

    monkeypatch.setattr(llm, "parse_feedback", fake_parse_feedback)
    result = c.record_feedback("something")

    assert result["applied"] == []
    assert result["unmatched"] == ["Some Made Up Problem"]


def test_progress_counts_solved_attempted_and_due(tmp_path, monkeypatch):
    c = _coach(tmp_path)

    def fake_parse_feedback(context):
        return {
            "updates": [
                {
                    "title": "Two Sum",
                    "outcome": "solved_independently",
                    "minutes": 8,
                    "used_hint": False,
                    "viewed_solution": False,
                    "notes": "",
                },
                {
                    "title": "Contains Duplicate",
                    "outcome": "gave_up",
                    "minutes": 15,
                    "used_hint": False,
                    "viewed_solution": False,
                    "notes": "",
                },
            ],
            "coach_note": "",
            "unmatched": [],
        }

    monkeypatch.setattr(llm, "parse_feedback", fake_parse_feedback)
    c.record_feedback("did two problems")

    p = c.progress()
    assert p["solved"] == 1
    assert p["attempted"] == 2
    assert p["due_reviews"] == 0  # both scheduled a few days out, not due yet
    topic = next(t for t in p["by_topic"] if t["topic"] == "Arrays & Hashing")
    assert topic["solved"] == 1


def test_undo_last_delegates_to_the_store(tmp_path, monkeypatch):
    c = _coach(tmp_path)

    def fake_parse_feedback(context):
        return {
            "updates": [
                {
                    "title": "Two Sum",
                    "outcome": "solved_independently",
                    "minutes": 8,
                    "used_hint": False,
                    "viewed_solution": False,
                    "notes": "",
                }
            ],
            "coach_note": "",
            "unmatched": [],
        }

    monkeypatch.setattr(llm, "parse_feedback", fake_parse_feedback)
    assert c.undo_last() is False  # nothing to undo before any feedback
    c.record_feedback("solved it")
    assert "Two Sum" in c.store.load().records
    assert c.undo_last() is True
    assert "Two Sum" not in c.store.load().records