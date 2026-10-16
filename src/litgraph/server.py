"""The website: the graph, the node editor, and the chat agent, served by Flask."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

from litgraph import __version__, literature
from litgraph.agent import Agent
from litgraph.store import EDGE_TYPES, NODE_TYPES, GraphError, GraphFile
from litgraph.workspace import Workspace

STATIC_DIR = Path(__file__).parent / "static"


def render_index(workspace: Workspace) -> str:
    page = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for placeholder, value in {"{{TITLE}}": workspace.title, "{{VERSION}}": __version__}.items():
        page = page.replace(placeholder, html.escape(value))
    return page


def export_page(workspace: Workspace, graph_file: GraphFile) -> str:
    """The graph as one HTML file that opens without a server (read-only: no chat, no editing)."""
    page = render_index(workspace)
    css = (STATIC_DIR / "style.css").read_text(encoding="utf-8")
    code = (STATIC_DIR / "app.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
    data = json.dumps({"graph": graph_file.graph.to_dict(), "node_types": NODE_TYPES, "edge_types": EDGE_TYPES},
                      ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = re.sub(r'<link rel="stylesheet" href="\./static/style\.css[^"]*" />', lambda _: f"<style>\n{css}\n</style>", page, count=1)
    page = re.sub(r'<script src="\./static/app\.js[^"]*"></script>',
                  lambda _: f"<script>window.LITGRAPH_EXPORT = {data};</script>\n<script>\n{code}\n</script>", page, count=1)
    return page


def create_app(workspace: Workspace | None = None, client=None) -> Flask:
    workspace = workspace or Workspace.load()
    graph_file = GraphFile(workspace.graph_path)
    agent = Agent(workspace, graph_file, client=client)
    proposals: dict[str, dict] = {}
    index_page = render_index(workspace)
    app = Flask(__name__, static_folder=None)

    def graph_payload():
        return {"graph": graph_file.graph.to_dict(), "node_types": NODE_TYPES, "edge_types": EDGE_TYPES}

    @app.get("/")
    def index():
        return Response(index_page, content_type="text/html; charset=utf-8")

    @app.get("/static/<path:filename>")
    def static_files(filename: str):
        return send_from_directory(STATIC_DIR, filename)

    @app.get("/api/health")
    def health():
        graph = graph_file.graph
        return jsonify({"ok": True, "version": __version__, "title": workspace.title, "model": workspace.model,
                        "ai": bool(workspace.api_key()), "web_search": workspace.web_search,
                        "literature_search": workspace.literature_search, "auto_apply": workspace.auto_apply,
                        "nodes": len(graph.nodes), "edges": len(graph.edges)})

    @app.get("/api/graph")
    def get_graph():
        return jsonify(graph_payload())

    @app.post("/api/graph/nodes")
    def upsert_node():
        payload = request.get_json(force=True) or {}
        try:
            node, created = graph_file.edit(lambda g: g.upsert_node(payload, status=payload.get("status", "confirmed"), source="manual"))
        except GraphError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        return jsonify({"ok": True, "node": node, "created": created, **graph_payload()})

    @app.delete("/api/graph/nodes/<path:node_id>")
    def delete_node(node_id: str):
        removed = graph_file.edit(lambda g: g.remove_node(node_id))
        return jsonify({"ok": removed, **graph_payload()}), 200 if removed else 404

    @app.post("/api/graph/edges")
    def add_edge():
        payload = request.get_json(force=True) or {}
        try:
            edge, created = graph_file.edit(lambda g: g.add_edge(payload, status="confirmed", source="manual"))
        except GraphError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        return jsonify({"ok": True, "edge": edge, "created": created, **graph_payload()})

    @app.delete("/api/graph/edges")
    def delete_edge():
        payload = request.get_json(force=True) or {}
        removed = graph_file.edit(lambda g: g.remove_edge(str(payload.get("source", "")), str(payload.get("target", "")), payload.get("type")))
        return jsonify({"ok": removed, **graph_payload()}), 200 if removed else 404

    @app.post("/api/graph/status")
    def set_status():
        payload = request.get_json(force=True) or {}
        try:
            changed = graph_file.edit(lambda g: g.set_status([str(i) for i in payload.get("ids", [])], str(payload.get("status", "confirmed"))))
        except GraphError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        return jsonify({"ok": True, "changed": changed, **graph_payload()})

    @app.post("/api/graph/apply")
    def apply_change():
        payload = request.get_json(force=True) or {}
        status = payload.get("status", "confirmed")
        report = graph_file.edit(lambda g: g.apply(payload.get("change") or {}, status=status, source=payload.get("source", "manual")))
        return jsonify({"ok": not report["errors"], "report": report, **graph_payload()})

    @app.post("/api/proposals/<proposal_id>/<action>")
    def decide_proposal(proposal_id: str, action: str):
        proposal = proposals.get(proposal_id)
        if not proposal:
            return jsonify({"ok": False, "message": "Unknown proposal (the server was restarted?). Use the node's own Confirm or Delete."}), 404
        if action == "accept":
            graph_file.edit(lambda g: g.set_status(proposal["added_nodes"], "confirmed"))
            proposal["status"] = "confirmed"
        elif action == "discard":
            def discard(g):
                for source, target, edge_type in proposal["added_edges"]:
                    g.remove_edge(source, target, edge_type)
                for node_id in proposal["added_nodes"]:
                    g.remove_node(node_id)
            graph_file.edit(discard)
            proposal["status"] = "discarded"
        else:
            return jsonify({"ok": False, "message": "Unknown action."}), 400
        return jsonify({"ok": True, "proposal": proposal, **graph_payload()})

    @app.get("/api/search")
    def search_papers():
        query = request.args.get("q", "").strip()
        if not query:
            return jsonify({"ok": False, "message": "q is required."}), 400
        return jsonify({"ok": True, **literature.search(query, int(request.args.get("limit", 8)))})

    @app.post("/api/answer/stream")
    def answer_stream():
        payload = request.get_json(force=True) or {}
        query = str(payload.get("query", "")).strip()
        if not query:
            return jsonify({"ok": False, "message": "query is required."}), 400
        if not workspace.api_key():
            return jsonify({"ok": False, "message": "No ANTHROPIC_API_KEY: put it in the workspace's .env file."}), 503

        def events():
            try:
                for event in agent.stream_answer(query, payload.get("history") or [], payload.get("context_ids") or []):
                    if event.get("type") == "proposal":
                        proposals[event["proposal"]["id"]] = event["proposal"]
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            except Exception as exc:
                yield json.dumps({"type": "error", "message": str(exc), "error": type(exc).__name__}, ensure_ascii=False) + "\n"

        response = Response(stream_with_context(events()), content_type="application/x-ndjson; charset=utf-8")
        response.headers["Cache-Control"] = "no-cache, no-transform"
        response.headers["X-Accel-Buffering"] = "no"
        return response

    return app
