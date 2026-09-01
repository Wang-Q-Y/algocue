from pathlib import Path

from coach.store import Attempt, ProblemRecord, State, Store, default_state_path


def test_default_state_path_respects_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("LEETCODE_COACH_HOME", str(tmp_path / "custom"))
    assert default_state_path() == tmp_path / "custom" / "state.json"


def test_default_state_path_falls_back_to_home(monkeypatch):
    monkeypatch.delenv("LEETCODE_COACH_HOME", raising=False)
    assert default_state_path() == Path.home() / ".leetcode-coach" / "state.json"


def test_load_missing_file_returns_empty_state(tmp_path):
    store = Store(tmp_path / "state.json")
    state = store.load()
    assert state.roadmap_id is None
    assert state.records == {}


def test_save_and_load_round_trip(tmp_path):
    store = Store(tmp_path / "state.json")
    state = State(roadmap_id="neetcode-150", created="2026-09-01")
    rec = state.record_for("Two Sum", "Arrays & Hashing")
    rec.attempts.append(Attempt(date="2026-09-01", minutes=8, outcome="solved_independently"))
    rec.next_review = "2026-09-04"
    rec.interval_days = 3
    rec.review_streak = 1
    store.save(state)

    reloaded = store.load()
    assert reloaded.roadmap_id == "neetcode-150"
    assert reloaded.created == "2026-09-01"
    assert set(reloaded.records) == {"Two Sum"}
    reloaded_rec = reloaded.records["Two Sum"]
    assert reloaded_rec.next_review == "2026-09-04"
    assert reloaded_rec.interval_days == 3
    assert len(reloaded_rec.attempts) == 1
    assert reloaded_rec.attempts[0].minutes == 8


def test_save_is_atomic_and_leaves_no_tmp_file(tmp_path):
    path = tmp_path / "state.json"
    store = Store(path)
    store.save(State(roadmap_id="neetcode-150"))
    assert path.exists()
    assert not path.with_suffix(".json.tmp").exists()


def test_record_for_reuses_existing_record():
    state = State()
    first = state.record_for("Two Sum", "Arrays & Hashing")
    second = state.record_for("Two Sum", "Arrays & Hashing")
    assert first is second


def test_solved_reflects_a_successful_outcome():
    rec = ProblemRecord(title="Two Sum", topic="Arrays & Hashing")
    assert rec.solved is False
    rec.attempts.append(Attempt(date="2026-09-01", outcome="gave_up"))
    assert rec.solved is False
    rec.attempts.append(Attempt(date="2026-09-02", outcome="solved_with_hints"))
    assert rec.solved is True


def test_no_backup_before_first_save(tmp_path):
    store = Store(tmp_path / "state.json")
    assert store.restore_backup() is False
    assert not store.backup_path.exists()


def test_second_save_backs_up_the_first(tmp_path):
    store = Store(tmp_path / "state.json")
    store.save(State(roadmap_id="neetcode-150"))
    store.save(State(roadmap_id="neetcode-150", created="2026-09-02"))
    assert store.backup_path.exists()
    import json

    backed_up = json.loads(store.backup_path.read_text())
    assert backed_up["created"] != "2026-09-02"


def test_restore_backup_reverts_and_consumes_the_backup(tmp_path):
    store = Store(tmp_path / "state.json")
    state = State(roadmap_id="neetcode-150")
    state.record_for("Two Sum", "Arrays & Hashing")
    store.save(state)

    state.record_for("Group Anagrams", "Arrays & Hashing")
    store.save(state)
    assert set(store.load().records) == {"Two Sum", "Group Anagrams"}

    assert store.restore_backup() is True
    assert set(store.load().records) == {"Two Sum"}
    # a single level of undo — the backup is consumed once used
    assert store.restore_backup() is False