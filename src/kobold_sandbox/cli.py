from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
import uvicorn

from .kobold_client import KoboldClient, KoboldGenerationConfig
from .llm_continue import llm_call_with_continue
from .logic_manifest import (
    build_logic_manifest_prompt,
    load_first_thoughts_example,
    parse_logic_manifest,
    prepare_reasoning_excerpt,
    verify_logic,
)
from .mcp_stdio import run_stdio_session
from .normalize_case_artifacts import normalize_case_artifacts
from .orchestrator import export_graph_json, run_task
from .server import create_app
from .storage import Sandbox

app = typer.Typer(no_args_is_help=True, help="Local iterative sandbox for KoboldCpp.")


def sandbox_from_root(root: Path) -> Sandbox:
    sandbox = Sandbox(root)
    if not sandbox.exists():
        raise typer.BadParameter(f"Sandbox is not initialized in {root}")
    return sandbox


def _read_prompt_input(prompt: str | None, prompt_file: Path | None) -> str:
    if prompt is not None:
        return prompt
    if prompt_file is not None:
        return prompt_file.read_text(encoding="utf-8")
    stdin_text = sys.stdin.read()
    if stdin_text.strip():
        return stdin_text
    raise typer.BadParameter("Provide prompt text, --prompt-file, or stdin input.")


@app.command()
def init(
    root: Path = typer.Option(Path("."), help="Sandbox root directory."),
    name: str = typer.Option("kobold-sandbox", help="Sandbox name."),
    kobold_url: str = typer.Option("http://localhost:5001", help="KoboldCpp base URL."),
    model: str | None = typer.Option(None, help="Default model name."),
    root_title: str = typer.Option("Root hypothesis", help="Human title for the root node."),
) -> None:
    sandbox = Sandbox(root)
    state = sandbox.init(sandbox_name=name, kobold_url=kobold_url, default_model=model, root_title=root_title)
    typer.echo(f"Initialized sandbox '{state.sandbox_name}' in {root.resolve()}")


@app.command("branch")
def branch_node(
    title: str,
    parent_id: str = typer.Option("root", help="Parent node id."),
    summary: str = typer.Option("", help="Short node summary."),
    tag: list[str] = typer.Option(None, "--tag", help="Tag for the node."),
    root: Path = typer.Option(Path("."), help="Sandbox root directory."),
) -> None:
    sandbox = sandbox_from_root(root)
    node = sandbox.create_node(parent_id=parent_id, title=title, summary=summary, tags=tag or [])
    typer.echo(json.dumps(node.model_dump(), ensure_ascii=False, indent=2))


@app.command()
def graph(root: Path = typer.Option(Path("."), help="Sandbox root directory.")) -> None:
    sandbox = sandbox_from_root(root)
    typer.echo(export_graph_json(sandbox))


@app.command()
def models(root: Path = typer.Option(Path("."), help="Sandbox root directory.")) -> None:
    if Sandbox(root).exists():
        sandbox = sandbox_from_root(root)
        state = sandbox.load_state()
        client = KoboldClient(state.kobold_url)
    else:
        client = KoboldClient("http://localhost:5001")
    typer.echo(json.dumps(client.list_models(), ensure_ascii=False, indent=2))


@app.command()
def notes(
    node_id: str = typer.Argument(...),
    content: str = typer.Option(..., help="Markdown notes content."),
    root: Path = typer.Option(Path("."), help="Sandbox root directory."),
) -> None:
    sandbox = sandbox_from_root(root)
    sandbox.update_notes(node_id, content)
    typer.echo(f"Updated notes for {node_id}")


@app.command()
def table(
    node_id: str = typer.Argument(...),
    name: str = typer.Option(..., help="File name, for example clues.csv."),
    content: str = typer.Option(..., help="CSV or Markdown content."),
    root: Path = typer.Option(Path("."), help="Sandbox root directory."),
) -> None:
    sandbox = sandbox_from_root(root)
    path = sandbox.write_table(node_id, name, content)
    typer.echo(f"Saved {path}")


@app.command()
def run(
    task: str = typer.Argument(...),
    node_id: str = typer.Option("root", help="Node id."),
    model: str | None = typer.Option(None, help="Override model."),
    commit: bool = typer.Option(False, help="Commit workspace changes before returning."),
    root: Path = typer.Option(Path("."), help="Sandbox root directory."),
) -> None:
    sandbox = sandbox_from_root(root)
    result = run_task(sandbox, node_id=node_id, task=task, model=model, commit=commit)
    typer.echo(result.response_text)
    typer.echo(f"\nSaved: {result.saved_to}")


@app.command()
def serve(
    root: Path = typer.Option(Path("."), help="Sandbox root directory."),
    host: str = typer.Option("127.0.0.1", help="Host."),
    port: int = typer.Option(8060, help="Port."),
) -> None:
    uvicorn.run(create_app(str(root.resolve())), host=host, port=port)


@app.command("mcp-stdio")
def mcp_stdio(
    root: Path = typer.Option(Path("."), help="Sandbox root directory."),
) -> None:
    run_stdio_session(str(root.resolve()), sys.stdin, sys.stdout)


@app.command("normalize-case")
def normalize_case(
    case_dir: Path = typer.Argument(..., help="Case directory with example JSON artifacts."),
) -> None:
    normalize_case_artifacts(case_dir.resolve())
    typer.echo(f"Normalized source_ref fields in {case_dir.resolve()}")


@app.command("logic-example")
def logic_example(
    root: Path = typer.Option(Path("."), help="Sandbox root directory."),
    model: str | None = typer.Option(None, help="Override model."),
) -> None:
    sandbox = Sandbox(root)
    client = KoboldClient(sandbox.load_state().kobold_url) if sandbox.exists() else KoboldClient("http://localhost:5001")
    example = load_first_thoughts_example(root / "examples" / "thoughts example.txt")
    raw = client.chat(
        prompt=build_logic_manifest_prompt(prepare_reasoning_excerpt(example.reasoning_text)),
        model=model or (sandbox.load_state().default_model if sandbox.exists() else None),
        system_prompt="Return only the requested manifest format.",
        config=KoboldGenerationConfig(max_tokens=768),
    )
    manifest = parse_logic_manifest(client.extract_text(raw))
    typer.echo(
        json.dumps(
            {
                "source_text": example.source_text,
                "manifest": manifest.model_dump(),
                "verification": verify_logic(manifest).model_dump(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("continue-generate")
def continue_generate(
    prompt: str | None = typer.Argument(None, help="Prompt text. If omitted, uses --prompt-file or stdin."),
    prompt_file: Path | None = typer.Option(None, help="Read prompt text from a UTF-8 file."),
    base_url: str = typer.Option("http://127.0.0.1:5001", help="Worker base URL."),
    temperature: float = typer.Option(0.2, help="Sampling temperature."),
    max_tokens: int = typer.Option(256, help="Per-call max token length."),
    max_continue: int = typer.Option(4, help="Maximum number of continue attempts."),
    stop: list[str] = typer.Option(None, "--stop", help="Stop token. Repeat to pass multiple stop tokens."),
    prompt_mode: str = typer.Option("instruct", help="Prompt mode: instruct, chat, or auto."),
    no_think: bool = typer.Option(True, help="Prefill no-think mode for chat calls."),
    json_output: bool = typer.Option(False, "--json", help="Print result bundle as JSON."),
) -> None:
    prompt_text = _read_prompt_input(prompt, prompt_file)
    result = llm_call_with_continue(
        base_url,
        [{"role": "user", "content": prompt_text}],
        temperature=temperature,
        max_tokens=max_tokens,
        no_think=no_think,
        max_continue=max_continue,
        continue_on_length=True,
        stop=stop or None,
        prompt_mode=prompt_mode,
    )
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "answer": result.answer,
                    "finish_reason": result.finish_reason,
                    "continues": result.continues,
                    "prompt_mode": result.prompt_mode,
                    "latency_ms": result.latency_ms,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    typer.echo(result.answer)


if __name__ == "__main__":
    app()
