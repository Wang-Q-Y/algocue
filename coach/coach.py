"""The Coach: orchestrates roadmap, memory, scheduler, and the LLM.

This is the single place the CLI talks to. It assembles the context the model
needs, calls it, and writes the results back to the store.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from . import llm, review
from .roadmap import Roadmap, load_roadmap
from .store import Attempt, State, Store


@dataclass
class PlanItem:
    title: str
    kind: str  # "new" | "review"
    difficulty: str
    topic: str
    estimated_minutes: int
    reason: str


@dataclass
class Plan:
    focus: str
    coach_note: str
    items: list[PlanItem]

    @property
    def total_minutes(self) -> int:
        return sum(i.estimated_minutes for i in self.items)


class Coach:
    def __init__(self, store: Store | None = None, today: date | None = None):
        self.store = store or Store()
        self.today = today or date.today()

    # ---- setup ---------------------------------------------------------- #

    def is_initialized(self) -> bool:
        state = self.store.load()
        return state.roadmap_id is not None

    def initialize(self, roadmap_id: str) -> Roadmap:
        """Choose a roadmap and start a fresh (or re-pointed) history."""
        roadmap = load_roadmap(roadmap_id)  # validates it exists
        state = self.store.load()
        state.roadmap_id = roadmap_id
        if not state.created:
            state.created = self.today.isoformat()
        self.store.save(state)
        return roadmap

    def _require_state(self) -> tuple[State, Roadmap]:
        state = self.store.load()
        if state.roadmap_id is None:
            raise RuntimeError(
                "No roadmap selected yet. Run `leetcode-coach init` first."
            )
        return state, load_roadmap(state.roadmap_id)

    # ---- daily planning ------------------------------------------------- #

    def plan_today(self, minutes: int) -> Plan:
        state, roadmap = self._require_state()
        context = self._build_plan_context(state, roadmap, minutes)
        raw = llm.generate_plan(context)
        return self._materialize_plan(raw, roadmap)

    def _build_plan_context(
        self, state: State, roadmap: Roadmap, minutes: int
    ) -> dict[str, Any]:
        history = []
        for p in roadmap.problems:
            rec = state.records.get(p.title)
            if rec is None:
                continue
            last = rec.last_attempt
            history.append(
                {
                    "title": p.title,
                    "topic": p.topic,
                    "attempts": len(rec.attempts),
                    "solved": rec.solved,
                    "last_outcome": last.outcome if last else None,
                    "last_date": last.date if last else None,
                    "next_review": rec.next_review,
                    "due_for_review": review.is_due(rec, self.today),
                }
            )

        roadmap_view = [
            {
                "title": p.title,
                "topic": p.topic,
                "difficulty": p.difficulty,
                "order": p.order,
                "status": _status(state, p.title),
            }
            for p in roadmap.problems
        ]

        return {
            "today": self.today.isoformat(),
            "available_minutes": minutes,
            "roadmap": {
                "name": roadmap.name,
                "description": roadmap.description,
                "problems": roadmap_view,
            },
            "history": history,
        }

    def _materialize_plan(self, raw: dict[str, Any], roadmap: Roadmap) -> Plan:
        items: list[PlanItem] = []
        for entry in raw.get("items", []):
            prob = roadmap.by_title(entry["title"])
            if prob is None:
                # Model referenced something not in the roadmap — skip defensively.
                continue
            items.append(
                PlanItem(
                    title=prob.title,
                    kind=entry.get("kind", "new"),
                    difficulty=prob.difficulty,
                    topic=prob.topic,
                    estimated_minutes=int(entry.get("estimated_minutes", 0)),
                    reason=entry.get("reason", ""),
                )
            )
        return Plan(
            focus=raw.get("focus", "balanced"),
            coach_note=raw.get("coach_note", ""),
            items=items,
        )

    # ---- daily feedback ------------------------------------------------- #

    def record_feedback(
        self, feedback: str, plan: Plan | None = None
    ) -> dict[str, Any]:
        """Parse the user's recap, update history + schedule, and persist.

        Returns a summary dict the CLI can render:
        ``{"applied": [...], "unmatched": [...], "coach_note": str}``.
        """
        state, roadmap = self._require_state()

        reference = {
            "todays_plan": (
                [{"title": i.title, "kind": i.kind} for i in plan.items]
                if plan
                else []
            ),
            "roadmap_titles": [p.title for p in roadmap.problems],
        }
        raw = llm.parse_feedback({"reference": reference, "feedback": feedback})

        applied: list[dict[str, Any]] = []
        for update in raw.get("updates", []):
            prob = roadmap.by_title(update["title"])
            if prob is None:
                raw.setdefault("unmatched", []).append(update["title"])
                continue
            attempt = Attempt(
                date=self.today.isoformat(),
                minutes=update.get("minutes"),
                outcome=update.get("outcome", "solved_independently"),
                used_hint=bool(update.get("used_hint", False)),
                viewed_solution=bool(update.get("viewed_solution", False)),
                notes=update.get("notes", ""),
            )
            record = state.record_for(prob.title, prob.topic)
            review.apply_attempt(record, attempt, self.today)
            applied.append(
                {
                    "title": prob.title,
                    "outcome": attempt.outcome,
                    "next_review": record.next_review,
                }
            )

        self.store.save(state)
        return {
            "applied": applied,
            "unmatched": raw.get("unmatched", []),
            "coach_note": raw.get("coach_note", ""),
        }

    def undo_last(self) -> bool:
        """Revert the most recent save (typically a `done` that got misread)."""
        return self.store.restore_backup()

    # ---- progress summary (lightweight dashboard) ----------------------- #

    def progress(self) -> dict[str, Any]:
        state, roadmap = self._require_state()
        total = len(roadmap.problems)
        solved = sum(
            1
            for p in roadmap.problems
            if (rec := state.records.get(p.title)) and rec.solved
        )
        attempted = sum(1 for p in roadmap.problems if p.title in state.records)
        due = sum(
            1
            for p in roadmap.problems
            if (rec := state.records.get(p.title)) and review.is_due(rec, self.today)
        )

        by_topic = []
        for topic in roadmap.topics():
            probs = [p for p in roadmap.problems if p.topic == topic]
            t_solved = sum(
                1
                for p in probs
                if (rec := state.records.get(p.title)) and rec.solved
            )
            by_topic.append(
                {"topic": topic, "solved": t_solved, "total": len(probs)}
            )

        return {
            "roadmap": roadmap.name,
            "solved": solved,
            "attempted": attempted,
            "total": total,
            "due_reviews": due,
            "by_topic": by_topic,
        }


def _status(state: State, title: str) -> str:
    rec = state.records.get(title)
    if rec is None:
        return "new"
    if rec.solved:
        return "solved"
    return "in_progress"