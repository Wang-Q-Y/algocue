"""Command-line interface for the AI Daily LeetCode Coach.

The whole product answers one question — "what should I practice today?" — so
the CLI is intentionally tiny:

    leetcode-coach init          choose a roadmap (once)
    leetcode-coach plan          "I have 45 minutes" -> today's plan
    leetcode-coach done          tell the coach how it went (plain English)
    leetcode-coach progress      a quick look at where you are
    leetcode-coach undo          walk back the last `done` if it got misread

`plan` then `done` is the whole daily loop.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import llm
from .coach import Coach, Plan, PlanItem
from .roadmap import available_roadmaps, load_roadmap
from .store import Store, default_state_path

# --- small terminal helpers ------------------------------------------------ #

_USE_COLOR = sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(t: str) -> str:
    return _c(t, "1")


def dim(t: str) -> str:
    return _c(t, "2")


def green(t: str) -> str:
    return _c(t, "32")


def cyan(t: str) -> str:
    return _c(t, "36")


def yellow(t: str) -> str:
    return _c(t, "33")


def _plan_cache_path(store: Store) -> Path:
    return store.path.parent / "last_plan.json"


def _save_plan(store: Store, plan: Plan) -> None:
    payload = {
        "focus": plan.focus,
        "coach_note": plan.coach_note,
        "items": [
            {
                "title": i.title,
                "kind": i.kind,
                "difficulty": i.difficulty,
                "topic": i.topic,
                "estimated_minutes": i.estimated_minutes,
                "reason": i.reason,
            }
            for i in plan.items
        ],
    }
    path = _plan_cache_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def _load_plan(store: Store) -> Plan | None:
    path = _plan_cache_path(store)
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    items = [
        PlanItem(
            title=i["title"],
            kind=i["kind"],
            difficulty=i["difficulty"],
            topic=i["topic"],
            estimated_minutes=i["estimated_minutes"],
            reason=i["reason"],
        )
        for i in raw.get("items", [])
    ]
    return Plan(focus=raw.get("focus", "balanced"), coach_note=raw.get("coach_note", ""), items=items)


def _parse_minutes(tokens: list[str]) -> int | None:
    """Accept things like '45', '45m', '1h', '1 hour', 'I have 90 minutes'."""
    text = " ".join(tokens).lower()
    hours = re.search(r"(\d+)\s*(?:h|hour|hours)", text)
    mins = re.search(r"(\d+)\s*(?:m|min|mins|minute|minutes)", text)
    total = 0
    if hours:
        total += int(hours.group(1)) * 60
    if mins:
        total += int(mins.group(1))
    if total:
        return total
    bare = re.search(r"\b(\d+)\b", text)
    if bare:
        return int(bare.group(1))
    return None


# --- commands -------------------------------------------------------------- #


def cmd_init(args: argparse.Namespace) -> int:
    coach = Coach(store=Store(args.state))
    roadmaps = available_roadmaps()

    roadmap_id = args.roadmap
    if roadmap_id is None:
        if len(roadmaps) == 1:
            roadmap_id = roadmaps[0]
        else:
            print(bold("Choose a roadmap:"))
            for i, rid in enumerate(roadmaps, 1):
                rm = load_roadmap(rid)
                print(f"  {i}. {rm.name}  {dim('(' + str(len(rm.problems)) + ' problems)')}")
            choice = input("> ").strip()
            try:
                roadmap_id = roadmaps[int(choice) - 1]
            except (ValueError, IndexError):
                roadmap_id = choice  # allow typing the id directly

    try:
        rm = coach.initialize(roadmap_id)
    except FileNotFoundError as exc:
        print(yellow(str(exc)))
        return 1

    print()
    print(green(f"✓ Coaching you through {bold(rm.name)}."))
    print(dim(f"  {len(rm.problems)} problems across {len(rm.topics())} topics."))
    print()
    print("Tomorrow (or now), just tell me how much time you have:")
    print(cyan("    leetcode-coach plan 45"))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    store = Store(args.state)
    coach = Coach(store=store)
    if not coach.is_initialized():
        print(yellow("No roadmap yet. Run `leetcode-coach init` first."))
        return 1

    minutes = _parse_minutes(args.time)
    if minutes is None:
        print(yellow("How much time do you have? e.g. `leetcode-coach plan 45`"))
        return 1
    if minutes <= 0:
        print(yellow("That's no time at all — come back when you've got a few minutes!"))
        return 1

    print(dim(f"Thinking about your best {minutes} minutes today..."))
    try:
        plan = coach.plan_today(minutes)
    except llm.LLMError as exc:
        print(yellow(f"\n{exc}"))
        return 2

    _save_plan(store, plan)
    _render_plan(plan, minutes)
    return 0


def _render_plan(plan: Plan, minutes: int) -> None:
    print()
    if plan.coach_note:
        print(bold(plan.coach_note))
        print()
    if not plan.items:
        print(dim("Nothing to practice right now — enjoy the break."))
        return

    focus_label = {"new": "new material", "review": "review", "balanced": "a mix of new & review"}
    print(dim(f"Focus: {focus_label.get(plan.focus, plan.focus)}"))
    print()
    for i, item in enumerate(plan.items, 1):
        tag = green("review") if item.kind == "review" else cyan("new")
        print(f"  {bold(str(i) + '.')} {bold(item.title)}  [{tag}]")
        print(
            dim(
                f"     {item.topic} · {item.difficulty} · ~{item.estimated_minutes} min"
            )
        )
        if item.reason:
            print(dim(f"     {item.reason}"))
    print()
    print(dim(f"Estimated total: ~{plan.total_minutes} of your {minutes} minutes."))
    print()
    print("When you're done, tell me how it went:")
    print(cyan('    leetcode-coach done "..."'))


def cmd_done(args: argparse.Namespace) -> int:
    store = Store(args.state)
    coach = Coach(store=store)
    if not coach.is_initialized():
        print(yellow("No roadmap yet. Run `leetcode-coach init` first."))
        return 1

    feedback = " ".join(args.feedback).strip()
    if not feedback:
        print("Tell me how today's practice went (just type it out):")
        try:
            feedback = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
    if not feedback:
        print(yellow("Nothing to record."))
        return 1

    plan = _load_plan(store)
    print(dim("Updating your history..."))
    try:
        result = coach.record_feedback(feedback, plan=plan)
    except llm.LLMError as exc:
        print(yellow(f"\n{exc}"))
        return 2

    _render_feedback(result)
    return 0


def _render_feedback(result: dict) -> None:
    print()
    applied = result.get("applied", [])
    if applied:
        print(bold("Recorded:"))
        for a in applied:
            outcome = a["outcome"].replace("_", " ")
            nxt = a.get("next_review")
            when = dim(f"  → review around {nxt}") if nxt else ""
            print(f"  {green('✓')} {a['title']}  {dim('(' + outcome + ')')}{when}")
        print()
    if result.get("coach_note"):
        print(result["coach_note"])
        print()
    unmatched = result.get("unmatched", [])
    if unmatched:
        print(yellow("Couldn't match these to roadmap problems:"))
        for u in unmatched:
            print(f"  · {u}")
        print()
    if not applied and not unmatched:
        print(dim("Nothing to record from that."))


def cmd_undo(args: argparse.Namespace) -> int:
    coach = Coach(store=Store(args.state))
    if coach.undo_last():
        print(green("Reverted your last recorded update."))
        return 0
    print(yellow("Nothing to undo."))
    return 1


def cmd_progress(args: argparse.Namespace) -> int:
    coach = Coach(store=Store(args.state))
    if not coach.is_initialized():
        print(yellow("No roadmap yet. Run `leetcode-coach init` first."))
        return 1

    p = coach.progress()
    print()
    print(bold(p["roadmap"]))
    pct = (p["solved"] / p["total"] * 100) if p["total"] else 0
    print(f"  Solved: {green(str(p['solved']))}/{p['total']}  ({pct:.0f}%)")
    print(f"  Attempted: {p['attempted']}/{p['total']}")
    if p["due_reviews"]:
        print(f"  Reviews due: {yellow(str(p['due_reviews']))}")
    print()
    print(dim("By topic:"))
    for t in p["by_topic"]:
        if t["solved"] == 0:
            continue
        bar = _bar(t["solved"], t["total"])
        print(f"  {bar}  {t['topic']}  {dim(str(t['solved']) + '/' + str(t['total']))}")
    print()
    return 0


def _bar(done: int, total: int, width: int = 12) -> str:
    filled = round(done / total * width) if total else 0
    return green("█" * filled) + dim("░" * (width - filled))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="leetcode-coach",
        description="An AI coach that decides what you should practice each day.",
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=None,
        help=f"Path to state file (default: {default_state_path()}).",
    )
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Choose a roadmap (do this once).")
    p_init.add_argument("roadmap", nargs="?", help="Roadmap id (e.g. neetcode-150).")
    p_init.set_defaults(func=cmd_init)

    p_plan = sub.add_parser("plan", help='Get today\'s plan, e.g. `plan 45`.')
    p_plan.add_argument("time", nargs="*", help="How much time you have, e.g. 45 or '1 hour'.")
    p_plan.set_defaults(func=cmd_plan)

    p_done = sub.add_parser("done", help="Tell the coach how the session went.")
    p_done.add_argument("feedback", nargs="*", help="Plain-English recap of your session.")
    p_done.set_defaults(func=cmd_done)

    p_prog = sub.add_parser("progress", help="See where you are on the roadmap.")
    p_prog.set_defaults(func=cmd_progress)

    p_undo = sub.add_parser("undo", help="Revert the last recorded update.")
    p_undo.set_defaults(func=cmd_undo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())