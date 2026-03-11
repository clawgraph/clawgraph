"""LobsterGym Eval Runner — Orchestrates evaluation pipeline.

Sends tasks to an OpenClaw instance, waits for completion, then checks
the mock service state endpoints to score pass/fail.

Usage:
    python -m lobstergym.eval.runner --profile clawgraph
    python -m lobstergym.eval.runner --profile default --task browser-todo-add
    python -m lobstergym.eval.runner --profile clawgraph --category api
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from .tasks import TASKS, Category, Check, Difficulty, Task, get_tasks

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WEB_BASE = os.getenv("LOBSTERGYM_WEB_BASE", "http://lobstergym-web:8080")
API_BASE = os.getenv("LOBSTERGYM_API_BASE", "http://lobstergym-api:8090")

# How long to wait for the agent to finish a task (seconds)
TASK_TIMEOUT = 120
# Pause between polling checks
POLL_INTERVAL = 5


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Result of a single verification check."""

    description: str
    passed: bool
    expected: Any = None
    actual: Any = None
    error: str | None = None


@dataclass
class TaskResult:
    """Result of a single task evaluation."""

    task_id: str
    task_name: str
    category: str
    difficulty: str
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)
    duration_seconds: float = 0.0
    error: str | None = None
    agent_response: str | None = None


@dataclass
class EvalReport:
    """Full evaluation report."""

    profile: str
    started_at: str = ""
    finished_at: str = ""
    total: int = 0
    passed: int = 0
    failed: int = 0
    score: float = 0.0
    results: list[TaskResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# State inspection
# ---------------------------------------------------------------------------


def _resolve_field(data: Any, path: str) -> Any:
    """Navigate a dot-separated field path into JSON data.

    Supports:
        - ``items`` — plain key access
        - ``items.[0]`` — array index
        - ``items.[].text`` — collect field from all items
        - ``items.[?done=true]`` — filter array items
        - ``items.[?id='note-001'].content`` — filter then access

    Args:
        data: Parsed JSON data.
        path: Dot-separated path.

    Returns:
        Resolved value.
    """
    parts = path.split(".")
    current = data

    for part in parts:
        if current is None:
            return None

        # Array filter: [?field=value]
        if part.startswith("[?") and part.endswith("]"):
            expr = part[2:-1]
            key, val = expr.split("=", 1)
            # Strip quotes from value
            val = val.strip("'\"")
            # Try bool / int coercion
            if val.lower() == "true":
                val = True
            elif val.lower() == "false":
                val = False
            else:
                try:
                    val = int(val)
                except ValueError:
                    pass
            if isinstance(current, list):
                current = [item for item in current if item.get(key) == val]
            continue

        # Array collect: []
        if part == "[]":
            continue  # next part will collect from list items

        # Array index: [0]
        if part.startswith("[") and part.endswith("]"):
            try:
                idx = int(part[1:-1])
                current = current[idx]
            except (IndexError, TypeError):
                return None
            continue

        # Normal key access
        if isinstance(current, list):
            # Collect field from all list items
            current = [item.get(part) if isinstance(item, dict) else None for item in current]
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None

    return current


def run_check(check: Check) -> CheckResult:
    """Execute a single verification check.

    Args:
        check: The check to run.

    Returns:
        CheckResult with pass/fail.
    """
    try:
        if check.service == "web":
            url = f"{WEB_BASE}{check.endpoint}"
        elif check.service == "api":
            url = f"{API_BASE}{check.endpoint}"
        elif check.service == "clawgraph":
            # Special: run clawgraph export
            result = subprocess.run(
                ["clawgraph", "export", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            data = json.loads(result.stdout) if result.stdout else {}
            actual = _resolve_field(data, check.field_path)
            return _evaluate_assertion(check, actual)
        else:
            return CheckResult(
                description=check.description,
                passed=False,
                error=f"Unknown service: {check.service}",
            )

        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        actual = _resolve_field(data, check.field_path)
        return _evaluate_assertion(check, actual)

    except Exception as exc:
        return CheckResult(
            description=check.description,
            passed=False,
            error=str(exc),
        )


def _evaluate_assertion(check: Check, actual: Any) -> CheckResult:
    """Evaluate an assertion against an actual value.

    Args:
        check: The check definition.
        actual: The resolved value from the state endpoint.

    Returns:
        CheckResult.
    """
    passed = False

    if check.assertion == "exists":
        passed = actual is not None

    elif check.assertion == "equals":
        passed = actual == check.expected

    elif check.assertion == "contains":
        if isinstance(actual, list):
            passed = any(
                check.expected in str(item) if isinstance(item, str) else check.expected == item
                for item in actual
            )
        elif isinstance(actual, str):
            passed = str(check.expected) in actual
        else:
            passed = False

    elif check.assertion == "length_gte":
        passed = isinstance(actual, list) and len(actual) >= check.expected

    elif check.assertion == "length_eq":
        passed = isinstance(actual, list) and len(actual) == check.expected

    elif check.assertion == "not_empty":
        passed = bool(actual)

    return CheckResult(
        description=check.description,
        passed=passed,
        expected=check.expected,
        actual=_summarize(actual),
    )


def _summarize(val: Any, max_len: int = 200) -> Any:
    """Truncate large values for display."""
    if isinstance(val, list):
        return f"list[{len(val)}]"
    if isinstance(val, str) and len(val) > max_len:
        return val[:max_len] + "..."
    return val


# ---------------------------------------------------------------------------
# Agent interaction
# ---------------------------------------------------------------------------


def send_task_to_agent(instruction: str) -> str:
    """Send a task instruction to the OpenClaw agent.

    Connects to the running OpenClaw gateway so the agent has full tool
    support (browser, HTTP, memory).  A local gateway must be started
    before the eval runner is invoked.

    Args:
        instruction: Natural-language instruction.

    Returns:
        Agent response text.
    """
    try:
        result = subprocess.run(
            ["openclaw", "agent", "--json", "--message", instruction],
            capture_output=True,
            text=True,
            timeout=TASK_TIMEOUT,
        )
        return result.stdout or result.stderr or "(no output)"
    except subprocess.TimeoutExpired:
        return "(timeout)"
    except FileNotFoundError:
        return "(openclaw not found)"


def reset_services() -> None:
    """Reset both mock services to clean state."""
    try:
        requests.post(f"{WEB_BASE}/reset", timeout=5)
    except Exception:
        pass
    try:
        requests.post(f"{API_BASE}/reset", timeout=5)
    except Exception:
        pass


def wait_for_services(timeout: int = 60) -> bool:
    """Wait for both mock services to be ready.

    Args:
        timeout: Max wait time in seconds.

    Returns:
        True if services are ready.
    """
    start = time.time()
    ready = {"web": False, "api": False}

    while time.time() - start < timeout:
        if not ready["web"]:
            try:
                r = requests.get(f"{WEB_BASE}/health", timeout=3)
                ready["web"] = r.status_code == 200
            except Exception:
                pass
        if not ready["api"]:
            try:
                r = requests.get(f"{API_BASE}/health", timeout=3)
                ready["api"] = r.status_code == 200
            except Exception:
                pass
        if all(ready.values()):
            return True
        time.sleep(2)

    return False


# ---------------------------------------------------------------------------
# Evaluation runner
# ---------------------------------------------------------------------------


def run_task(task: Task) -> TaskResult:
    """Run a single evaluation task.

    Args:
        task: The task to evaluate.

    Returns:
        TaskResult with pass/fail and check details.
    """
    print(f"  [{task.id}] {task.name} ({task.difficulty.value})...", end=" ", flush=True)

    if task.setup_reset:
        reset_services()
        time.sleep(1)

    start = time.time()
    try:
        response = send_task_to_agent(task.instruction)
    except Exception as exc:
        duration = time.time() - start
        print("ERROR")
        return TaskResult(
            task_id=task.id,
            task_name=task.name,
            category=task.category.value,
            difficulty=task.difficulty.value,
            passed=False,
            duration_seconds=duration,
            error=str(exc),
        )

    # Small delay for state to settle
    time.sleep(2)

    # Run all checks
    check_results = [run_check(check) for check in task.checks]
    all_passed = all(cr.passed for cr in check_results)
    duration = time.time() - start

    status = "PASS" if all_passed else "FAIL"
    print(f"{status} ({duration:.1f}s)")

    if not all_passed:
        for cr in check_results:
            if not cr.passed:
                print(f"    ✗ {cr.description}: expected={cr.expected}, actual={cr.actual}")
                if cr.error:
                    print(f"      error: {cr.error}")

    return TaskResult(
        task_id=task.id,
        task_name=task.name,
        category=task.category.value,
        difficulty=task.difficulty.value,
        passed=all_passed,
        checks=check_results,
        duration_seconds=duration,
        agent_response=response[:500] if response else None,
    )


def run_eval(
    profile: str,
    category: Category | None = None,
    difficulty: Difficulty | None = None,
    task_id: str | None = None,
    tags: list[str] | None = None,
    output_file: str | None = None,
) -> EvalReport:
    """Run the full evaluation pipeline.

    Args:
        profile: Name of the eval profile (e.g. ``clawgraph``, ``default``).
        category: Optional category filter.
        difficulty: Optional difficulty filter.
        task_id: Optional single task ID to run.
        tags: Optional tag filter.
        output_file: Optional path to write JSON report.

    Returns:
        EvalReport with results.
    """
    report = EvalReport(
        profile=profile,
        started_at=datetime.utcnow().isoformat(),
    )

    # Select tasks
    if task_id:
        tasks = [t for t in TASKS if t.id == task_id]
        if not tasks:
            print(f"Task '{task_id}' not found.")
            sys.exit(1)
    else:
        tasks = get_tasks(category=category, difficulty=difficulty, tags=tags)

    if not tasks:
        print("No tasks match the filters.")
        sys.exit(1)

    print(f"\n🦞 LobsterGym Eval — profile: {profile}")
    print(f"   Running {len(tasks)} task(s)\n")

    # Wait for services
    print("Waiting for services...", end=" ", flush=True)
    if not wait_for_services():
        print("TIMEOUT — services not ready")
        sys.exit(1)
    print("ready\n")

    # Run tasks
    for task in tasks:
        result = run_task(task)
        report.results.append(result)

    # Summary
    report.finished_at = datetime.utcnow().isoformat()
    report.total = len(report.results)
    report.passed = sum(1 for r in report.results if r.passed)
    report.failed = report.total - report.passed
    report.score = report.passed / report.total if report.total > 0 else 0.0

    print(f"\n{'=' * 50}")
    print(f"Profile: {profile}")
    print(f"Score:   {report.passed}/{report.total} ({report.score:.0%})")
    print(f"Passed:  {report.passed}")
    print(f"Failed:  {report.failed}")
    print(f"{'=' * 50}\n")

    # Write report
    if output_file:
        report_dict = asdict(report)
        Path(output_file).write_text(json.dumps(report_dict, indent=2))
        print(f"Report written to: {output_file}")

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="LobsterGym Evaluation Runner")
    parser.add_argument(
        "--profile",
        default="default",
        help="Eval profile name (e.g. 'clawgraph', 'default')",
    )
    parser.add_argument("--task", help="Run a single task by ID")
    parser.add_argument(
        "--category",
        choices=[c.value for c in Category],
        help="Filter by category",
    )
    parser.add_argument(
        "--difficulty",
        choices=[d.value for d in Difficulty],
        help="Filter by difficulty",
    )
    parser.add_argument("--tags", nargs="*", help="Filter by tags")
    parser.add_argument("--output", help="Output JSON report path")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available tasks and exit",
    )

    args = parser.parse_args()

    if args.list:
        print("\n🦞 LobsterGym — Available Tasks\n")
        for task in TASKS:
            print(
                f"  {task.id:<30} {task.category.value:<8} "
                f"{task.difficulty.value:<6} {task.name}"
            )
        print(f"\n  Total: {len(TASKS)} tasks\n")
        return

    cat = Category(args.category) if args.category else None
    diff = Difficulty(args.difficulty) if args.difficulty else None

    report = run_eval(
        profile=args.profile,
        category=cat,
        difficulty=diff,
        task_id=args.task,
        tags=args.tags,
        output_file=args.output,
    )

    sys.exit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()
