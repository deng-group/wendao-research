"""litgraph commands: init, serve, check, extract, export."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path
from threading import Timer

from litgraph import __version__
from litgraph.store import Graph, GraphError, GraphFile
from litgraph.workspace import Workspace, init_workspace


def cmd_init(args) -> int:
    written = init_workspace(Path(args.directory), args.title)
    for path in written:
        print(f"  wrote {path}")
    print(f"\nNext: cd {args.directory}; litgraph serve  (uses your Claude Code sign-in; see litgraph.toml for an API key instead)")
    return 0


def cmd_check(args) -> int:
    workspace = Workspace.load(args.workspace)
    ok = True
    try:
        graph = Graph.load(workspace.graph_path)
        print(f"graph.json: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
        proposed = [n["id"] for n in graph.nodes if n["status"] == "proposed"]
        if proposed:
            print(f"  {len(proposed)} proposed nodes await confirmation: {', '.join(proposed[:8])}{'…' if len(proposed) > 8 else ''}")
        lonely = [n["id"] for n in graph.nodes if not graph.edges_of(n["id"])]
        if lonely:
            print(f"  {len(lonely)} nodes have no links: {', '.join(lonely[:8])}")
    except (GraphError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"graph.json: {exc}")
        ok = False
    print(f"model: {workspace.model_label()} via {workspace.provider} (effort {workspace.effort})")
    ready, why = workspace.ai_ready()
    if not ready:
        print(f"  {why} The website works, the chat does not.")
    elif not args.no_model:
        try:
            if workspace.provider == "claude-code":
                from litgraph.claude_code import ClaudeCodeAgent
                from litgraph.store import GraphFile
                agent = ClaudeCodeAgent(workspace, GraphFile(workspace.graph_path))
                events = list(agent.stream_answer("Reply with the single word ok, and use no tools."))
                errors = [e["message"] for e in events if e["type"] == "error"]
                if errors:
                    raise RuntimeError(errors[0])
                print("  Claude Code answered:", events[-1].get("answer", "")[:40])
            else:
                import anthropic
                client = anthropic.Anthropic()
                reply = client.messages.create(model=workspace.model, max_tokens=20, messages=[{"role": "user", "content": "Say ok."}])
                print("  model answered:", "".join(b.text for b in reply.content if b.type == "text").strip()[:40])
        except Exception as exc:
            print(f"  model check failed: {exc}")
            ok = False
    return 0 if ok else 1


def cmd_serve(args) -> int:
    from litgraph.server import create_app
    workspace = Workspace.load(args.workspace)
    if not workspace.graph_path.exists():
        print(f"No graph.json in {workspace.root}. Run `litgraph init` first, or pick the workspace with --workspace.")
        return 1
    app = create_app(workspace)
    host, port = args.host or workspace.host, args.port or workspace.port
    url = f"http://{host}:{port}/"
    print(f"litgraph {__version__}: {workspace.title} at {url}  (Ctrl+C stops)")
    ready, why = workspace.ai_ready()
    if not ready:
        print(f"{why} The graph works, the chat is off.")
    if not args.no_open:
        Timer(0.8, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=port, debug=False, threaded=True)
    return 0


def cmd_extract(args) -> int:
    from litgraph.agent import make_agent
    workspace = Workspace.load(args.workspace)
    ready, why = workspace.ai_ready()
    if not ready:
        print(why)
        return 1
    graph_file = GraphFile(workspace.graph_path)
    agent = make_agent(workspace, graph_file)
    for file in args.files:
        path = Path(file)
        print(f"Reading {path} …")
        change = agent.extract(path.read_text(encoding="utf-8"), title=path.stem)
        status = "confirmed" if args.confirm else "proposed"
        report = graph_file.edit(lambda g: g.apply(change, status=status, source="extract"))
        print(f"  {len(report['added_nodes'])} new nodes, {len(report['updated_nodes'])} updated, {len(report['added_edges'])} new edges ({status})")
        for message in report["errors"]:
            print(f"  skipped: {message}")
    return 0


def cmd_export(args) -> int:
    from litgraph.server import export_page
    workspace = Workspace.load(args.workspace)
    out = Path(args.output or (workspace.root / "build" / "graph.html"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(export_page(workspace, GraphFile(workspace.graph_path)), encoding="utf-8")
    print(f"wrote {out}")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="litgraph", description="A research knowledge graph that grows as you read, search and chat.")
    parser.add_argument("--version", action="version", version=f"litgraph {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create a new workspace")
    p.add_argument("directory")
    p.add_argument("--title", default="My research graph")
    p.set_defaults(run=cmd_init)

    for name, func, help_text in (("serve", cmd_serve, "run the website"), ("check", cmd_check, "check the graph and the model"),
                                  ("extract", cmd_extract, "turn documents into graph nodes and edges"), ("export", cmd_export, "one HTML file of the graph")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--workspace", "-w", default=None, help="workspace folder (default: current folder)")
        p.set_defaults(run=func)
        if name == "serve":
            p.add_argument("--host"); p.add_argument("--port", type=int); p.add_argument("--no-open", action="store_true")
        if name == "check":
            p.add_argument("--no-model", action="store_true", help="skip the model call")
        if name == "extract":
            p.add_argument("files", nargs="+"); p.add_argument("--confirm", action="store_true", help="add as confirmed, not proposed")
        if name == "export":
            p.add_argument("--output", "-o")
    args = parser.parse_args(argv)
    sys.exit(args.run(args))
