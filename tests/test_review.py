from datetime import date

from coach.review import apply_attempt, is_due
from coach.store import Attempt, ProblemRecord

TODAY = date(2026, 9, 1)


def _record() -> ProblemRecord:
    return ProblemRecord(title="Two Sum", topic="Arrays & Hashing")


def test_first_good_attempt_starts_the_streak():
    rec = _record()
    apply_attempt(rec, Attempt(date=TODAY.isoformat(), outcome="solved_independently"), TODAY)
    assert rec.review_streak == 1
    assert rec.interval_days == 3  # ladder: [1, 3, 7, 16, 35, 90], index 1
    assert rec.next_review == "2026-09-04"


def test_streak_climbs_the_interval_ladder_on_repeated_success():
    rec = _record()
    for _ in range(3):
        apply_attempt(rec, Attempt(date=TODAY.isoformat(), outcome="reviewed_easily"), TODAY)
    assert rec.review_streak == 3
    assert rec.interval_days == 16
    assert rec.next_review == "2026-09-17"


def test_streak_caps_at_the_top_of_the_ladder():
    rec = _record()
    for _ in range(10):
        apply_attempt(rec, Attempt(date=TODAY.isoformat(), outcome="solved_independently"), TODAY)
    assert rec.review_streak == 10
    assert rec.interval_days == 90  # last rung, doesn't keep growing


def test_hints_from_scratch_use_the_floor_interval():
    rec = _record()
    apply_attempt(rec, Attempt(date=TODAY.isoformat(), outcome="solved_with_hints"), TODAY)
    assert rec.review_streak == 1
    assert rec.interval_days == 2


def test_hints_after_a_streak_dont_shrink_the_interval():
    rec = _record()
    apply_attempt(rec, Attempt(date=TODAY.isoformat(), outcome="solved_independently"), TODAY)
    apply_attempt(rec, Attempt(date=TODAY.isoformat(), outcome="solved_with_hints"), TODAY)
    assert rec.review_streak == 1  # unchanged, hints don't grow it
    assert rec.interval_days == 3  # kept, since it was already above the floor


def test_poor_outcome_resets_the_streak():
    rec = _record()
    apply_attempt(rec, Attempt(date=TODAY.isoformat(), outcome="reviewed_easily"), TODAY)
    apply_attempt(rec, Attempt(date=TODAY.isoformat(), outcome="reviewed_easily"), TODAY)
    assert rec.review_streak == 2
    apply_attempt(rec, Attempt(date=TODAY.isoformat(), outcome="struggled"), TODAY)
    assert rec.review_streak == 0
    assert rec.interval_days == 1
    assert rec.next_review == "2026-09-02"


def test_gave_up_and_viewed_solution_also_reset():
    for outcome in ("gave_up", "viewed_solution"):
        rec = _record()
        apply_attempt(rec, Attempt(date=TODAY.isoformat(), outcome="reviewed_easily"), TODAY)
        apply_attempt(rec, Attempt(date=TODAY.isoformat(), outcome=outcome), TODAY)
        assert rec.review_streak == 0
        assert rec.interval_days == 1


def test_attempts_are_appended_in_order():
    rec = _record()
    apply_attempt(rec, Attempt(date="2026-09-01", outcome="solved_independently"), TODAY)
    apply_attempt(rec, Attempt(date="2026-09-04", outcome="reviewed_easily"), date(2026, 9, 4))
    assert [a.date for a in rec.attempts] == ["2026-09-01", "2026-09-04"]
    assert rec.last_attempt.date == "2026-09-04"
    assert rec.first_seen == "2026-09-01"


def test_is_due_with_no_schedule():
    rec = _record()
    assert is_due(rec, TODAY) is False


def test_is_due_on_or_after_scheduled_date():
    rec = _record()
    rec.next_review = "2026-09-01"
    assert is_due(rec, date(2026, 9, 1)) is True
    assert is_due(rec, date(2026, 9, 5)) is True


def test_not_due_before_scheduled_date():
    rec = _record()
    rec.next_review = "2026-09-10"
    assert is_due(rec, TODAY) is False