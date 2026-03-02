"""CLI entry point for ClawGraph."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from clawgraph import __version__

app = typer.Typer(
    name="clawgraph",
    help="Graph-based memory abstraction layer for AI agents.",
    no_args_is_help=True,
)

console = Console(stderr=True)
out_console = Console()


class OutputFormat(str, Enum):
    """Output format options."""

    human = "human"
    json = "json"


def _output(data: dict[str, Any], fmt: OutputFormat) -> None:
    """Output data in the selected format.

    Args:
        data: The data payload to output.
        fmt: Output format (human or json).
    """
    if fmt == OutputFormat.json:
        out_console.print_json(json.dumps(data))
    else:
        # For human output, data should have already been printed via rich
        pass


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version and exit."
    ),
) -> None:
    """ClawGraph — Graph-based memory layer for AI agents."""
    if version:
        out_console.print(f"clawgraph {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        out_console.print(ctx.get_help())
        raise typer.Exit()


@app.command()
def add(
    statement: str = typer.Argument(..., help="Natural language statement to store."),
    output: OutputFormat = typer.Option(
        OutputFormat.human, "--output", "-o", help="Output format."
    ),
    model: str | None = typer.Option(
        None, "--model", "-m", help="Override LLM model."
    ),
) -> None:
    """Add a fact or relationship to the graph memory."""
    from clawgraph.cypher import sanitize_cypher, validate_cypher
    from clawgraph.db import DatabaseError, GraphDB
    from clawgraph.llm import LLMError, build_merge_cypher, infer_ontology
    from clawgraph.ontology import Ontology

    console.print(f"[bold blue]Adding:[/bold blue] {statement}")

    # Step 1: Infer ontology (entities + relationships)
    ontology = Ontology()
    console.print("[dim]  Inferring entities...[/dim]")
    try:
        inferred = infer_ontology(
            statement,
            existing_ontology=ontology.to_context_string(),
            model=model,
        )
    except LLMError as e:
        console.print(f"[bold red]LLM Error:[/bold red] {e}")
        raise typer.Exit(1)

    entities = inferred.get("entities", [])
    relationships = inferred.get("relationships", [])

    if not entities:
        console.print("[yellow]No entities found in the statement.[/yellow]")
        raise typer.Exit(1)

    console.print(f"[dim]  Found {len(entities)} entities, {len(relationships)} relationships[/dim]")

    # Step 2: Build Cypher MERGE statements
    cypher = build_merge_cypher(entities, relationships)
    console.print("[dim]  Generated Cypher:[/dim]")

    # Step 3: Execute each statement
    db = GraphDB()
    db.ensure_base_schema()

    executed: list[str] = []
    errors: list[str] = []

    for line in cypher.split("\n"):
        line = line.strip()
        if not line:
            continue

        clean = sanitize_cypher(line)
        validation = validate_cypher(clean)

        if not validation:
            errors.append(f"Validation failed for: {clean} — {validation.errors}")
            continue

        try:
            db.execute(clean)
            executed.append(clean)
            console.print(f"[green]  ✓[/green] {clean}")
        except DatabaseError as e:
            errors.append(f"DB error: {e}")
            console.print(f"[red]  ✗[/red] {e}")

    # Step 4: Update ontology
    for entity in entities:
        ontology.add_node_label(entity.get("label", "Unknown"), {"name": "STRING"})
    for rel in relationships:
        from_label = _find_label(rel.get("from", ""), entities)
        to_label = _find_label(rel.get("to", ""), entities)
        ontology.add_relationship_type(rel.get("type", "RELATED_TO"), from_label, to_label)

    result = {
        "status": "ok" if not errors else "partial",
        "entities": entities,
        "relationships": relationships,
        "executed": len(executed),
        "errors": errors,
    }

    if output == OutputFormat.human:
        if not errors:
            console.print("[bold green]Done![/bold green]")
        else:
            console.print(f"[bold yellow]Completed with {len(errors)} error(s)[/bold yellow]")
    else:
        _output(result, output)


def _find_label(name: str, entities: list[dict[str, str]]) -> str:
    """Find the label for an entity by name."""
    for entity in entities:
        if entity.get("name") == name:
            return entity.get("label", "Unknown")
    return "Unknown"


@app.command("add-batch")
def add_batch(
    statements: list[str] = typer.Argument(..., help="Multiple statements to store."),
    output: OutputFormat = typer.Option(
        OutputFormat.human, "--output", "-o", help="Output format."
    ),
    model: str | None = typer.Option(
        None, "--model", "-m", help="Override LLM model."
    ),
) -> None:
    """Add multiple facts in a single LLM call (faster for batch operations)."""
    from clawgraph.memory import Memory

    console.print(f"[bold blue]Batch adding {len(statements)} statements...[/bold blue]")

    try:
        mem = Memory(model=model)
        result = mem.add_batch(statements)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    if output == OutputFormat.human:
        console.print(f"[dim]  Entities: {len(result.entities)}[/dim]")
        console.print(f"[dim]  Relationships: {len(result.relationships)}[/dim]")
        console.print(f"[dim]  Executed: {result.executed} statements[/dim]")
        if result.ok:
            console.print("[bold green]Done![/bold green]")
        else:
            console.print(f"[bold yellow]Completed with {len(result.errors)} error(s)[/bold yellow]")
    else:
        _output(result.to_dict(), output)


@app.command()
def query(
    question: str = typer.Argument(..., help="Natural language question to query."),
    output: OutputFormat = typer.Option(
        OutputFormat.human, "--output", "-o", help="Output format."
    ),
    model: str | None = typer.Option(
        None, "--model", "-m", help="Override LLM model."
    ),
) -> None:
    """Query the graph memory with natural language."""
    from clawgraph.cypher import sanitize_cypher, validate_cypher
    from clawgraph.db import DatabaseError, GraphDB
    from clawgraph.llm import LLMError, generate_cypher
    from clawgraph.ontology import Ontology

    console.print(f"[bold blue]Querying:[/bold blue] {question}")

    ontology = Ontology()
    context = ontology.to_context_string()

    # Generate read Cypher
    console.print("[dim]  Generating query...[/dim]")
    try:
        raw_cypher = generate_cypher(
            question,
            ontology_context=context,
            model=model,
            mode="read",
        )
    except LLMError as e:
        console.print(f"[bold red]LLM Error:[/bold red] {e}")
        raise typer.Exit(1)

    cypher = sanitize_cypher(raw_cypher)
    validation = validate_cypher(cypher)

    if not validation:
        console.print(f"[bold red]Invalid Cypher:[/bold red] {validation.errors}")
        console.print(f"[dim]Raw query: {cypher}[/dim]")
        raise typer.Exit(1)

    console.print(f"[dim]  Cypher: {cypher}[/dim]")

    # Execute
    db = GraphDB()
    try:
        rows = db.execute(cypher)
    except DatabaseError as e:
        console.print(f"[bold red]Query Error:[/bold red] {e}")
        raise typer.Exit(1)

    if output == OutputFormat.json:
        _output({"query": cypher, "results": rows, "count": len(rows)}, output)
        return

    # Human output
    if not rows:
        console.print("[yellow]No results found.[/yellow]")
        return

    table = Table(title="Query Results")
    columns = list(rows[0].keys())
    for col in columns:
        table.add_column(col, style="cyan")
    for row in rows:
        table.add_row(*[str(row.get(c, "")) for c in columns])
    out_console.print(table)


@app.command()
def ontology(
    output: OutputFormat = typer.Option(
        OutputFormat.human, "--output", "-o", help="Output format."
    ),
    clear: bool = typer.Option(False, "--clear", help="Clear the ontology."),
) -> None:
    """Show the current graph ontology (node labels, relationship types)."""
    from clawgraph.ontology import Ontology

    ont = Ontology()

    if clear:
        ont.clear()
        console.print("[green]Ontology cleared.[/green]")
        return

    if output == OutputFormat.json:
        _output(ont.to_dict(), output)
        return

    context = ont.to_context_string()
    if context == "No ontology defined yet.":
        console.print("[dim]No ontology defined yet.[/dim]")
    else:
        out_console.print(Panel(context, title="Ontology", border_style="blue"))


@app.command()
def export(
    path: Path | None = typer.Argument(
        None, help="Output file path. Defaults to stdout."
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.json, "--output", "-o", help="Output format."
    ),
) -> None:
    """Export the graph memory to JSON."""
    from clawgraph.db import GraphDB

    db = GraphDB()
    entities = db.get_all_entities()
    relationships = db.get_all_relationships()

    data = {
        "entities": entities,
        "relationships": relationships,
    }

    json_str = json.dumps(data, indent=2)

    if path:
        path.write_text(json_str, encoding="utf-8")
        console.print(f"[green]Exported to {path}[/green]")
    else:
        out_console.print(json_str)


@app.command()
def config(
    key: str | None = typer.Argument(None, help="Config key (e.g., llm.model)."),
    value: str | None = typer.Argument(None, help="Config value to set."),
) -> None:
    """Get or set configuration values."""
    from clawgraph.config import get_config_value, load_config, set_config_value

    if key and value:
        set_config_value(key, value)
        console.print(f"[green]Set {key} = {value}[/green]")
    elif key:
        val = get_config_value(key)
        if val is None:
            console.print(f"[yellow]{key} is not set[/yellow]")
        else:
            out_console.print(str(val))
    else:
        cfg = load_config()
        out_console.print_json(json.dumps(cfg, indent=2))


if __name__ == "__main__":
    app()
