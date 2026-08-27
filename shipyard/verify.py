"""Verification by execution.

No stage advances because an agent said it works. It advances because a command
exited zero. Command output is captured, truncated, and fed back into the repair
loop verbatim, which is what lets a `dev` role fix its own build.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .ledger import Ledger

MAX_CAPTURE = 8000  # characters of each stream kept for feedback


def _tail(text: str, limit: int = MAX_CAPTURE) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return "...(truncated)...\n" + text[-limit:]


@dataclass(frozen=True)
class Check:
    name: str
    cmd: str
    cwd: Path
    timeout: int = 900
    #: An optional check that fails is reported but does not block the stage.
    optional: bool = False


@dataclass
class CheckResult:
    name: str
    cmd: str
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    optional: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    @property
    def blocking_failure(self) -> bool:
        return not self.ok and not self.optional


@dataclass
class CheckReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(r.blocking_failure for r in self.results)

    @property
    def failures(self) -> list[CheckResult]:
        return [r for r in self.results if not r.ok]

    def summary(self) -> str:
        if not self.results:
            return "no checks run"
        parts = [
            f"{'PASS' if r.ok else ('WARN' if r.optional else 'FAIL')} {r.name} ({r.duration_s:.1f}s)"
            for r in self.results
        ]
        return "; ".join(parts)

    def as_feedback(self) -> str:
        """Failure text shaped for a repair prompt."""
        lines: list[str] = []
        for r in self.failures:
            lines.append(f"### Check failed: {r.name}")
            lines.append(f"Command: {r.cmd}")
            lines.append(f"Exit code: {r.exit_code}")
            if r.error:
                lines.append(f"Runner error: {r.error}")
            if r.stdout:
                lines.append("stdout:\n" + _tail(r.stdout, 4000))
            if r.stderr:
                lines.append("stderr:\n" + _tail(r.stderr, 4000))
            lines.append("")
        return "\n".join(lines).strip() or "all checks passed"


def run_check(check: Check) -> CheckResult:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            check.cmd,
            shell=True,
            cwd=str(check.cwd),
            capture_output=True,
            text=True,
            timeout=check.timeout,
        )
        return CheckResult(
            name=check.name,
            cmd=check.cmd,
            exit_code=proc.returncode,
            stdout=_tail(proc.stdout),
            stderr=_tail(proc.stderr),
            duration_s=time.monotonic() - started,
            optional=check.optional,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            check.name, check.cmd, 124, "", "", time.monotonic() - started,
            check.optional, error=f"timed out after {check.timeout}s",
        )
    except OSError as exc:
        return CheckResult(
            check.name, check.cmd, 127, "", "", time.monotonic() - started,
            check.optional, error=str(exc),
        )


def run_checks(
    checks: list[Check], ledger: Ledger | None = None, stage: str = ""
) -> CheckReport:
    report = CheckReport()
    for check in checks:
        result = run_check(check)
        report.results.append(result)
        if ledger:
            ledger.event(
                "check",
                stage=stage,
                name=check.name,
                cmd=check.cmd,
                exit_code=result.exit_code,
                ok=result.ok,
                duration_s=round(result.duration_s, 2),
            )
    return report


def app_checks(app_dir: Path, timeout: int = 900) -> list[Check]:
    """The baseline gate every ticket and the trunk must pass."""
    return [
        Check("typecheck", "npm run --silent typecheck", app_dir, timeout),
        Check("lint", "npm run --silent lint", app_dir, timeout),
        Check("format", "npm run --silent format:check", app_dir, timeout),
        Check("unit", "npm run --silent test -- --ci --silent", app_dir, timeout),
    ]


def json_valid_check(name: str, path: Path, cwd: Path) -> Check:
    return Check(
        name,
        f"python3 -c \"import json,sys; json.load(open({str(path)!r}))\"",
        cwd,
        60,
    )


def files_exist(paths: list[Path], cwd: Path, name: str = "artifacts-exist") -> Check:
    quoted = " ".join(shlex.quote(str(p)) for p in paths)
    return Check(name, f"for f in {quoted}; do test -s \"$f\" || exit 1; done", cwd, 60)
