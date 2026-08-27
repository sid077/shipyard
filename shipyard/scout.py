"""Opportunity scouting: survey a space, come back with a ranked shortlist.

Stage 10 judges an idea the operator already chose. This is what runs when
nobody has chosen yet - the same `analyst` role, the same standard of evidence,
a different question.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .config import Settings, load_settings
from .contracts import Shortlist
from .ledger import Ledger
from .runner import RoleRequest, Runner
from .tasks import compose, existing

#: What this studio can actually build and ship, stated honestly. A candidate
#: that needs anything outside this is a candidate for a different studio.
CAPABILITIES = """\
- A React Native app built with Expo, shipping to both the App Store and Google
  Play from one codebase.
- Works offline by default. A backend is possible but every dependency on one is
  a liability, because there is nobody on call.
- Paid with a one-time unlock or a subscription through RevenueCat, with a free
  tier that meters usage.
- On-device camera, local notifications, local storage, and the platform vision
  and speech APIs.
- Roughly three to six weeks of build effort, executed by AI engineers against a
  written specification. Scope must be small enough to specify completely.

What this studio cannot do:

- Two-sided marketplaces, or anything needing liquidity before it is useful.
- Anything needing content licensing, a seeded data set the studio does not own,
  or a partnership to launch.
- Hardware, or anything depending on point-of-sale or retailer distribution.
- Regulated advice: medical diagnosis, financial advice, legal advice.
- Anything with a heavy support burden. There is one operator and no support desk.
- Anything that needs paid acquisition to work. Distribution is organic store
  search plus a landing page.
"""


def scout_dir(settings: Settings, slug: str) -> Path:
    return settings.scouting_dir / slug


def default_slug() -> str:
    return "scout-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")


SWEEP_FILE = "scouting/sweep.md"
#: Below this a sweep file is a stub, not something phase two can build on.
MIN_SWEEP_BYTES = 800


def sweep_path(project_dir: Path) -> Path:
    return Path(project_dir) / SWEEP_FILE


def has_sweep(project_dir: Path) -> bool:
    path = sweep_path(project_dir)
    return path.is_file() and path.stat().st_size >= MIN_SWEEP_BYTES


def _focus_line(focus: str) -> str:
    if focus.strip():
        return f"Search within this focus: {focus.strip()}"
    return (
        "No category has been chosen. Range widely before you narrow, and record "
        "which spaces you looked at and rejected."
    )


def build_sweep_task(focus: str, count: int, project_dir: Path) -> str:
    """Phase one: range wide, write down what you find as you find it."""
    notes = sweep_path(project_dir)
    return compose(
        objective=(
            f"Survey the market for mobile-app opportunities this studio could "
            f"build next. This is the first of two passes: range wide now, and "
            f"gather roughly {count * 2} leads worth a closer look. Do not try to "
            f"reach a final answer yet.\n\n{_focus_line(focus)}"
        ),
        project_dir=project_dir,
        guidance=f"""\
## What this studio can build

{CAPABILITIES}

## Write as you go, not at the end

Write your findings to `{notes}` **incrementally, as you find them** - append a
short section for each lead the moment you have something on it, before moving
to the next search. Do not hold everything in your head and write the file last.

This matters: a previous pass researched for twelve minutes, ran out of usage
window, and produced nothing at all because it had written nothing down. A file
with six half-finished leads is worth more than a perfect one that never lands.

## What a lead looks like

For each one, record: what the product is in a sentence, who it is for, and the
**demand signal** you actually saw - an install count, a review count, a price
someone is charging, a complaint pattern, a search volume, a forum thread. Note
the URL beside it.

Also keep a running list of what you looked at and rejected, with the reason.
That list is worth as much as the leads, especially if none of the leads survive
the second pass.

Do not verify exhaustively yet. Breadth now, depth next. Stop once you have
enough leads or you sense the window tightening, and make sure the file is
complete enough for someone else to continue from.""",
    )


def build_shortlist_task(focus: str, count: int, project_dir: Path) -> str:
    """Phase two: verify the leads and commit to a ranking."""
    notes = sweep_path(project_dir)
    return compose(
        objective=(
            f"Turn the leads already gathered into a ranked shortlist of at most "
            f"{count} candidates, verified properly.\n\n{_focus_line(focus)}"
        ),
        project_dir=project_dir,
        inputs=existing(notes),
        outputs=[Shortlist],
        guidance=f"""\
## What this studio can build

{CAPABILITIES}

## Verify before you rank

`{notes}` holds the leads from the first pass. Work from it. For each lead you
intend to shortlist, confirm the things a reader would check: real competitors
with real prices, real install or review volume, and whether anyone credible has
already tried and failed.

Keep appending to `{notes}` as you verify, so this pass also survives being cut
short.

`demand_evidence` must contain numbers you actually found, with the source in
`sources`. "Lots of people struggle with this" is not evidence, and a candidate
whose demand section reads that way should be ranked below one whose does not.

`fit_rationale` must say why the candidate suits *these* constraints - not why
it is a nice idea. A candidate that needs a backend, a content library or a
retail partnership belongs in `also_considered` with that reason, not in the
shortlist.

Ground `monetization` in what comparable apps actually charge today.

## The reject pile is part of the answer

Fill `also_considered` properly: every space you examined and set aside, each
with the reason. If nothing clears the bar, that list *is* the deliverable and
leaving `recommended` empty is the right call. The last brief this studio
commissioned came back `no-go`, and that was the right answer.""",
    )


async def _call(runner: Runner, project_dir: Path, task: str) -> None:
    await runner.invoke(
        RoleRequest(
            role="analyst",
            stage="scout",
            cwd=project_dir,
            allowed_roots=[project_dir],
            task=task,
        )
    )


async def scout(
    runner: Runner,
    ledger: Ledger,
    project_dir: Path,
    focus: str = "",
    count: int = 5,
) -> Shortlist:
    """Run a scouting pass in two phases and return the validated shortlist.

    Split deliberately. A single call has to survive from the first search to
    the final JSON, and when it does not, everything it learned is lost. The
    sweep lands durable notes first, so a pass cut short by an exhausted usage
    window resumes from those notes instead of starting over.
    """
    project_dir = Path(project_dir)
    (project_dir / "scouting").mkdir(parents=True, exist_ok=True)

    if has_sweep(project_dir):
        ledger.event("scout.sweep_reused", bytes=sweep_path(project_dir).stat().st_size)
    else:
        await _call(runner, project_dir, build_sweep_task(focus, count, project_dir))
        if not has_sweep(project_dir):
            raise RuntimeError(
                f"the sweep produced no usable notes at {sweep_path(project_dir)}; "
                f"nothing for the shortlist pass to build on"
            )
        ledger.event("scout.sweep_done", bytes=sweep_path(project_dir).stat().st_size)

    await _call(runner, project_dir, build_shortlist_task(focus, count, project_dir))
    shortlist = Shortlist.load(project_dir)
    ledger.event(
        "scout.completed",
        candidates=len(shortlist.candidates),
        pursue=len(shortlist.pursue),
        recommended=shortlist.recommended or "(none)",
    )
    return shortlist


def prepare(settings: Settings | None = None, slug: str | None = None) -> tuple[Path, Ledger]:
    settings = settings or load_settings()
    slug = slug or default_slug()
    directory = scout_dir(settings, slug)
    (directory / "scouting").mkdir(parents=True, exist_ok=True)
    ledger = Ledger.create(directory, slug, "Opportunity scouting")
    return directory, ledger
