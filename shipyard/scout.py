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
from .tasks import compose

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


def build_task(focus: str, count: int, project_dir: Path) -> str:
    objective = (
        f"Survey the market and come back with the {count} best mobile-app "
        f"opportunities this studio could build next, ranked by the strength of "
        f"the demand evidence behind them."
    )
    if focus.strip():
        objective += f"\n\nSearch within this focus: {focus.strip()}"
    else:
        objective += (
            "\n\nNo category has been chosen. Range widely before you narrow, and "
            "say in `also_considered` which spaces you looked at and rejected."
        )

    return compose(
        objective=objective,
        project_dir=project_dir,
        outputs=[Shortlist],
        guidance=f"""\
## What this studio can build

{CAPABILITIES}

## What earns a place on the shortlist

Demand you can point at. Concrete forms that count: an existing paid app in the
space with real install volume or review counts; a free incumbent with visible
complaints that a paid product could answer; search or forum evidence that
people are actively looking; a recent platform or regulatory change that just
made something possible or necessary.

`demand_evidence` must contain numbers you actually found, with the source in
`sources`. "Lots of people struggle with this" is not evidence, and a candidate
whose demand section reads that way should be ranked below one whose does not.

`fit_rationale` must say why the candidate suits *these* constraints - not why
it is a nice idea. A candidate that needs a backend, a content library or a
retail partnership belongs in `also_considered` with that reason, not in the
shortlist.

Ground `monetization` in what comparable apps actually charge today.

Be sceptical of your own shortlist. If fewer than {count} candidates genuinely
clear the bar, return the ones that do plus honest `reject` entries for the rest
of what you examined, and leave `recommended` empty rather than promoting
something you do not believe in. The last brief this studio commissioned came
back `no-go`, and that was the right answer.""",
    )


async def scout(
    runner: Runner,
    ledger: Ledger,
    project_dir: Path,
    focus: str = "",
    count: int = 5,
) -> Shortlist:
    """Run one scouting pass and return the validated shortlist."""
    await runner.invoke(
        RoleRequest(
            role="analyst",
            stage="scout",
            cwd=project_dir,
            allowed_roots=[project_dir],
            task=build_task(focus, count, project_dir),
        )
    )
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
