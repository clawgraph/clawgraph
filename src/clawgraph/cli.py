"""CLI entry point for ClawGraph."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from clawgraph import __version__

app = typer.Typer(
    name="clawgraph",
    help="Graph-based memory abstraction layer for AI agents.",
    no_args_is_help=True,
)

console = Console()


class OutputFormat(str, Enum):
    """Output format options."""

    human = "human"
    json = "json"


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version and exit."
    ),
) -> None:
    """ClawGraph — Graph-based memory layer for AI agents."""
    if version:
        console.print(f"clawgraph {__version__}")
        raise typer.Exit()


@app.command()
def add(
    statement: str = typer.Argument(..., help="Natural language statement to store."),
    output: OutputFormat = typer.Option(
        OutputFormat.human, "--output", "-o", help="Output format."
    ),
) -> None:
    """Add a fact or relationship to the graph memory."""
    # TODO: Implement LLM → Cypher → DB pipeline
    console.print(f"[dim]Adding:[/dim] {statement}")


@app.command()
def query(
    question: str = typer.Argument(..., help="Natural language question to query."),
    output: OutputFormat = typer.Option(
        OutputFormat.human, "--output", "-o", help="Output format."
    ),
) -> None:
    """Query the graph memory with natural language."""
    # TODO: Implement LLM → Cypher query → result pipeline
    console.print(f"[dim]Querying:[/dim] {question}")


@app.command()
def ontology(
    output: OutputFormat = typer.Option(
        OutputFormat.human, "--output", "-o", help="Output format."
    ),
) -> None:
    """Show the current graph ontology (node labels, relationship types)."""
    # TODO: Implement ontology display
    console.print("[dim]No ontology defined yet.[/dim]")


@app.command()
def export(
    path: Optional[Path] = typer.Argument(
        None, help="Output file path. Defaults to stdout."
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.json, "--output", "-o", help="Output format."
    ),
) -> None:
    """Export the graph memory to JSON."""
    # TODO: Implement export
    console.print("[dim]Nothing to export yet.[/dim]")


@app.command()
def config(
    key: Optional[str] = typer.Argument(None, help="Config key (e.g., llm.model)."),
    value: Optional[str] = typer.Argument(None, help="Config value to set."),
) -> None:
    """Get or set configuration values."""
    # TODO: Implement config management
    if key and value:
        console.print(f"[dim]Set {key} = {value}[/dim]")
    elif key:
        console.print(f"[dim]Get {key}[/dim]")
    else:
        console.print("[dim]No config set yet.[/dim]")


if __name__ == "__main__":
    app()
