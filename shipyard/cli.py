"""Operator interface.

Six verbs: create a project, run it, see where it is, decide a gate, see what it
cost, and check the harness itself.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .config import load_settings
from .contracts import Idea
from .gates import GATE_INFO, Gate, decide
from .ledger import GateStatus, Ledger, StageStatus, TicketStatus
from .pipeline import build_context, run_pipeline
from .pipeline.registry import STAGE_KEYS, STAGES, validate_graph
from .roles import ROLES
from .runner import SDKRunner

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="An AI agent organization that ships deployable mobile apps.",
)
gate_app = typer.Typer(no_args_is_help=True, help="Approve or reject a human gate.")
app.add_typer(gate_app, name="gate")

console = Console()
STATUS_STYLE = {
    StageStatus.DONE: "green",
    StageStatus.RUNNING: "yellow",
    StageStatus.BLOCKED: "red",
    StageStatus.PENDING: "dim",
}


def _open(slug: str) -> tuple[Ledger, Path]:
    settings = load_settings()
    project_dir = settings.project_dir(slug)
    try:
        return Ledger.open(project_dir), project_dir
    except FileNotFoundError:
        console.print(f"[red]No project '{slug}' at {project_dir}[/red]")
        raise typer.Exit(1) from None


@app.command()
def new(
    slug: Annotated[str, typer.Argument(help="Short kebab-case project id.")],
    title: Annotated[str, typer.Option("--title", "-t", help="Human-readable name.")],
    brief: Annotated[str, typer.Option("--brief", "-b", help="What to build, in prose.")] = "",
    brief_file: Annotated[Path | None, typer.Option(help="Read the brief from a file.")] = None,
    one_liner: Annotated[str, typer.Option(help="One sentence pitch.")] = "",
    platforms: Annotated[str, typer.Option(help="Comma-separated: ios,android.")] = "ios,android",
    constraint: Annotated[list[str] | None, typer.Option(help="Repeatable hard constraint.")] = None,
) -> None:
    """Create a project and record its brief."""
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
        console.print("[red]slug must be lowercase kebab-case[/red]")
        raise typer.Exit(1)
    if brief_file:
        brief = brief_file.read_text(encoding="utf-8")
    if not brief.strip():
        console.print("[red]provide --brief or --brief-file[/red]")
        raise typer.Exit(1)

    settings = load_settings()
    project_dir = settings.project_dir(slug)
    if (project_dir / ".shipyard" / "state.json").exists():
        console.print(f"[red]project '{slug}' already exists[/red]")
        raise typer.Exit(1)

    from .workspace import create_project

    create_project(settings.projects_dir, slug)
    idea = Idea(
        slug=slug,
        title=title,
        one_liner=one_liner or brief.strip().splitlines()[0][:200],
        brief=brief.strip(),
        platforms=[p.strip() for p in platforms.split(",") if p.strip()],  # type: ignore[arg-type]
        constraints=list(constraint or []),
    )
    idea.save(project_dir)
    Ledger.create(project_dir, slug, title)
    console.print(f"[green]Created[/green] {project_dir}")
    console.print(f"Next: [bold]shipyard run {slug}[/bold]")


@app.command()
def run(
    slug: str,
    until: Annotated[str, typer.Option(help=f"Stop after this stage. One of: {', '.join(STAGE_KEYS)}")] = "",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate without calling any model.")] = False,
) -> None:
    """Run the pipeline from wherever it left off."""
    ledger, project_dir = _open(slug)
    settings = load_settings()

    if until and until not in STAGE_KEYS:
        console.print(f"[red]unknown stage '{until}'[/red]. Known: {', '.join(STAGE_KEYS)}")
        raise typer.Exit(1)

    if dry_run:
        problems = validate_graph()
        for stage in STAGES:
            missing = [c.rel_path for c in stage.requires if not c.exists(project_dir)]
            state = ledger.state.stage(stage.key).status
            mark = "done" if state == StageStatus.DONE else ("blocked-on " + ", ".join(missing) if missing else "ready")
            console.print(f"  {stage.key:20} {stage.title:16} {mark}")
        console.print(f"\n[bold]graph:[/bold] {'; '.join(problems) if problems else 'valid'}")
        raise typer.Exit(1 if problems else 0)

    runner = SDKRunner(ledger, settings)
    ctx = build_context(project_dir, ledger, runner, settings)
    outcome = asyncio.run(run_pipeline(STAGES, ctx, until=until or None))

    colour = {"complete": "green", "awaiting_gate": "cyan", "blocked": "red", "budget_exceeded": "red"}
    console.print(f"\n[{colour[outcome.status]}]{outcome.status}[/]: {outcome.message}")
    console.print(f"Spent ${ledger.state.cost_usd:.2f} of ${settings.project_budget_usd:.2f}")
    if outcome.status == "awaiting_gate" and outcome.gate:
        console.print(f"\nRead: [bold]{ledger.inbox / (outcome.gate + '.md')}[/bold]")
    raise typer.Exit(0 if outcome.ok else 1)


@app.command()
def resume(slug: str) -> None:
    """Continue a run after a gate decision or a fix. Same as `run`."""
    run(slug, until="", dry_run=False)


@app.command()
def status(slug: str) -> None:
    """Show where a project is."""
    ledger, project_dir = _open(slug)
    state = ledger.state
    console.print(f"\n[bold]{state.title}[/bold]  ([dim]{state.slug}[/dim])")
    console.print(f"{project_dir}\n")

    table = Table("Stage", "Title", "Status", "Attempts", "Note", box=None)
    for stage in STAGES:
        rec = state.stages.get(stage.key)
        st = rec.status if rec else StageStatus.PENDING
        table.add_row(
            stage.key,
            stage.title,
            f"[{STATUS_STYLE[st]}]{st}[/]",
            str(rec.attempts if rec else 0),
            (rec.note if rec else "")[:60],
        )
    console.print(table)

    gates = Table("Gate", "What it asks", "Status", box=None)
    for gate in Gate:
        rec = state.gates.get(gate.value)
        st = rec.status if rec else GateStatus.NOT_REACHED
        style = {"approved": "green", "pending": "cyan", "rejected": "red"}.get(str(st), "dim")
        gates.add_row(gate.value, GATE_INFO[gate][0], f"[{style}]{st}[/]")
    console.print(gates)

    if state.tickets:
        merged = sum(1 for st in state.tickets.values() if st == TicketStatus.MERGED)
        tickets = Table("Ticket", "Status", box=None)
        for tid, st in sorted(state.tickets.items()):
            style = {"merged": "green", "in_progress": "yellow", "blocked": "red"}.get(
                str(st), "dim"
            )
            tickets.add_row(tid, f"[{style}]{st}[/]")
        console.print(f"\n[bold]Tickets[/bold]  ({merged}/{len(state.tickets)} merged)")
        console.print(tickets)

    console.print(f"\nSpent: [bold]${state.cost_usd:.2f}[/bold]")
    if state.blocked_reason:
        console.print(f"[red]Blocked:[/red] {state.blocked_reason}")
    pending = sorted(p.name for p in ledger.inbox.glob("*.md")) if ledger.inbox.is_dir() else []
    if pending:
        console.print(f"Inbox: {', '.join(pending)}")


@app.command()
def cost(slug: str) -> None:
    """Break down spend by stage and role."""
    ledger, _ = _open(slug)
    rows = ledger.cost_rows()
    if not rows:
        console.print("No spend recorded yet.")
        return
    by: dict[tuple[str, str], list[float]] = {}
    for row in rows:
        by.setdefault((row["stage"], row["role"]), []).append(row["usd"])
    table = Table("Stage", "Role", "Calls", "USD", box=None)
    for (stage, role), amounts in sorted(by.items()):
        table.add_row(stage, role, str(len(amounts)), f"${sum(amounts):.4f}")
    console.print(table)
    console.print(f"\n[bold]Total: ${ledger.state.cost_usd:.2f}[/bold]")


@app.command("ls")
def list_projects() -> None:
    """List every project in this workspace."""
    settings = load_settings()
    if not settings.projects_dir.is_dir():
        console.print("No projects yet.")
        return
    table = Table("Slug", "Title", "Stage", "Spent", box=None)
    found = False
    for path in sorted(settings.projects_dir.iterdir()):
        if not (path / ".shipyard" / "state.json").is_file():
            continue
        found = True
        state = Ledger.open(path).state
        table.add_row(state.slug, state.title, state.current_stage or "-", f"${state.cost_usd:.2f}")
    console.print(table if found else "No projects yet.")


@app.command()
def doctor() -> None:
    """Check the harness itself: stage graph, role prompts, template."""
    settings = load_settings()
    problems: list[str] = list(validate_graph())

    for role in ROLES.values():
        path = role.prompt_path(settings)
        if not path.is_file():
            problems.append(f"role '{role.name}' has no system prompt at {path}")
        elif len(path.read_text(encoding="utf-8").strip()) < 200:
            problems.append(f"role '{role.name}' has a suspiciously short prompt")

    template = settings.templates_dir / "expo-app"
    if not template.is_dir():
        problems.append(f"app template missing at {template}")
    elif not (template / "package.json").is_file():
        problems.append(f"app template at {template} has no package.json")

    if problems:
        for p in problems:
            console.print(f"[red]x[/red] {p}")
        raise typer.Exit(1)
    console.print(f"[green]ok[/green] {len(STAGES)} stages, {len(ROLES)} roles, template present")


@gate_app.command("approve")
def gate_approve(slug: str, gate: str, notes: Annotated[str, typer.Option(help="Optional context for later stages.")] = "") -> None:
    """Approve a gate and let the run continue."""
    ledger, _ = _open(slug)
    decide(ledger, Gate(gate.upper()), True, notes)
    console.print(f"[green]{gate.upper()} approved.[/green] Continue with: [bold]shipyard resume {slug}[/bold]")


@gate_app.command("reject")
def gate_reject(slug: str, gate: str, notes: Annotated[str, typer.Option(help="What to change. Injected verbatim into the re-run.")] = "") -> None:
    """Reject a gate. The owning stage re-runs with your notes."""
    if not notes.strip():
        console.print("[red]--notes is required: the re-run needs to know what to change[/red]")
        raise typer.Exit(1)
    ledger, _ = _open(slug)
    decide(ledger, Gate(gate.upper()), False, notes)
    console.print(f"[yellow]{gate.upper()} rejected.[/yellow] Re-run with: [bold]shipyard resume {slug}[/bold]")


if __name__ == "__main__":
    app()
