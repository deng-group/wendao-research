"""The website: the graph, the node editor, and the chat agent, served by Flask."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request, send_from_directory, stream_with_context

from litgraph import __version__, literature
from litgraph.agent import make_agent
from litgraph.store import EDGE_TYPES, NODE_TYPES, GraphError, GraphFile
from litgraph.workspace import Workspace

STATIC_DIR = Path(__file__).parent / "static"


def render_index(workspace: Workspace) -> str:
    page = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for placeholder, value in {"{{TITLE}}": workspace.title, "{{VERSION}}": __version__}.items():
        page = page.replace(placeholder, html.escape(value))
    return page


def export_page(workspace: Workspace, graph_file: GraphFile) -> str:  # noqa: D401
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
    proposals: dict[str, dict] = {}
    index_page = render_index(workspace)
    app = Flask(__name__, static_folder=None)
    files: dict[str, GraphFile] = {}  # one GraphFile per topic, kept so edits serialise

    # Every graph and chat route works on one topic: `topic` in the query string or the JSON body, else the first.
    def current():
        slug = request.args.get("topic") or ((request.get_json(silent=True) or {}).get("topic") if request.is_json else None)
        topic = workspace.topic(slug)
        if topic is None:
            abort(404, description=f"No topic `{slug}`." if slug else "This workspace has no topic yet: create one.")
        key = str(topic.graph_path)
        if key not in files:
            files[key] = GraphFile(topic.graph_path)
        return topic, files[key], make_agent(workspace, files[key], client=client)

    def graph_payload(graph_file: GraphFile, topic=None):
        return {"graph": graph_file.graph.to_dict(), "node_types": NODE_TYPES, "edge_types": EDGE_TYPES, "topic": topic.describe() if topic else None}

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"ok": False, "message": getattr(error, "description", "Not found.")}), 404

    @app.get("/api/topics")
    def list_topics():
        return jsonify({"ok": True, "topics": [t.describe() for t in workspace.topics()]})

    @app.post("/api/topics")
    def open_or_create_topic():
        payload = request.get_json(force=True) or {}
        title = str(payload.get("title", "")).strip()
        if not title:
            return jsonify({"ok": False, "message": "Give the topic a name."}), 400
        existing = workspace.find_topic(title)
        if existing and not payload.get("force_new"):
            return jsonify({"ok": True, "created": False, "topic": existing.describe()})
        try:
            topic = workspace.create_topic(title, str(payload.get("description", "")))
        except ValueError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        return jsonify({"ok": True, "created": True, "topic": topic.describe()})

    @app.get("/api/topics/<slug>/review")
    def get_review(slug: str):
        topic = workspace.topic(slug)
        if topic is None:
            abort(404, description=f"No topic `{slug}`.")
        if not topic.review_path.exists():
            return jsonify({"ok": False, "message": "No review written yet."}), 404
        if request.args.get("download"):
            return Response(topic.review_path.read_text(encoding="utf-8"), content_type="text/markdown; charset=utf-8",
                            headers={"Content-Disposition": f'attachment; filename="{slug}-review.md"'})
        return jsonify({"ok": True, "markdown": topic.review_path.read_text(encoding="utf-8"), "topic": topic.describe()})

    @app.post("/api/topics/<slug>/review")
    def write_review(slug: str):
        topic = workspace.topic(slug)
        if topic is None:
            abort(404, description=f"No topic `{slug}`.")
        ready, why = workspace.ai_ready()
        if not ready:
            return jsonify({"ok": False, "message": why}), 503
        graph_file = files.setdefault(str(topic.graph_path), GraphFile(topic.graph_path))
        if not graph_file.graph.nodes:
            return jsonify({"ok": False, "message": "The graph is empty; nothing to write."}), 400
        try:
            markdown = make_agent(workspace, graph_file, client=client).write_review()
        except Exception as exc:
            return jsonify({"ok": False, "message": f"{type(exc).__name__}: {exc}"}), 500
        topic.review_path.write_text(markdown, encoding="utf-8")
        return jsonify({"ok": True, "markdown": markdown, "topic": topic.describe()})

    @app.post("/api/graph/keep_all")
    def keep_all():
        topic, graph_file, _agent = current()
        changed = graph_file.edit(lambda g: g.set_status([n["id"] for n in g.nodes if n["status"] == "proposed"], "confirmed"))
        return jsonify({"ok": True, "changed": changed, **graph_payload(graph_file, topic)})

    @app.get("/")
    def index():
        return Response(index_page, content_type="text/html; charset=utf-8")

    @app.get("/static/<path:filename>")
    def static_files(filename: str):
        return send_from_directory(STATIC_DIR, filename)

    @app.get("/api/health")
    def health():
        ready, why = workspace.ai_ready()
        topics = [t.describe() for t in workspace.topics()]
        return jsonify({"ok": True, "version": __version__, "title": workspace.title, "model": workspace.model_label(),
                        "provider": workspace.provider, "ai": ready, "ai_message": why, "web_search": workspace.web_search,
                        "literature_search": workspace.literature_search, "auto_apply": workspace.auto_apply,
                        "topics": topics, "nodes": sum(t["nodes"] for t in topics), "edges": sum(t["edges"] for t in topics)})

    @app.get("/api/graph")
    def get_graph():
        topic, graph_file, _agent = current()
        return jsonify(graph_payload(graph_file, topic))

    @app.post("/api/graph/nodes")
    def upsert_node():
        topic, graph_file, _agent = current()
        payload = request.get_json(force=True) or {}
        try:
            node, created = graph_file.edit(lambda g: g.upsert_node(payload, status=payload.get("status", "confirmed"), source="manual"))
        except GraphError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        return jsonify({"ok": True, "node": node, "created": created, **graph_payload(graph_file, topic)})

    @app.delete("/api/graph/nodes/<path:node_id>")
    def delete_node(node_id: str):
        topic, graph_file, _agent = current()
        removed = graph_file.edit(lambda g: g.remove_node(node_id))
        return jsonify({"ok": removed, **graph_payload(graph_file, topic)}), 200 if removed else 404

    @app.post("/api/graph/edges")
    def add_edge():
        topic, graph_file, _agent = current()
        payload = request.get_json(force=True) or {}
        try:
            edge, created = graph_file.edit(lambda g: g.add_edge(payload, status="confirmed", source="manual"))
        except GraphError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        return jsonify({"ok": True, "edge": edge, "created": created, **graph_payload(graph_file, topic)})

    @app.delete("/api/graph/edges")
    def delete_edge():
        topic, graph_file, _agent = current()
        payload = request.get_json(force=True) or {}
        removed = graph_file.edit(lambda g: g.remove_edge(str(payload.get("source", "")), str(payload.get("target", "")), payload.get("type")))
        return jsonify({"ok": removed, **graph_payload(graph_file, topic)}), 200 if removed else 404

    @app.post("/api/graph/status")
    def set_status():
        topic, graph_file, _agent = current()
        payload = request.get_json(force=True) or {}
        try:
            changed = graph_file.edit(lambda g: g.set_status([str(i) for i in payload.get("ids", [])], str(payload.get("status", "confirmed"))))
        except GraphError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        return jsonify({"ok": True, "changed": changed, **graph_payload(graph_file, topic)})

    @app.post("/api/graph/apply")
    def apply_change():
        topic, graph_file, _agent = current()
        payload = request.get_json(force=True) or {}
        status = payload.get("status", "confirmed")
        report = graph_file.edit(lambda g: g.apply(payload.get("change") or {}, status=status, source=payload.get("source", "manual")))
        return jsonify({"ok": not report["errors"], "report": report, **graph_payload(graph_file, topic)})

    @app.post("/api/proposals/<proposal_id>/<action>")
    def decide_proposal(proposal_id: str, action: str):
        proposal = proposals.get(proposal_id)
        if not proposal:
            return jsonify({"ok": False, "message": "Unknown proposal (the server was restarted?). Use the node's own Confirm or Delete."}), 404
        graph_file = files.get(proposal["_graph"]) or GraphFile(Path(proposal["_graph"]))
        topic = next((t for t in workspace.topics() if str(t.graph_path) == proposal["_graph"]), None)
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
        return jsonify({"ok": True, "proposal": {k: v for k, v in proposal.items() if not k.startswith("_")}, **graph_payload(graph_file, topic)})

    @app.get("/api/search")
    def search_papers():
        query = request.args.get("q", "").strip()
        if not query:
            return jsonify({"ok": False, "message": "q is required."}), 400
        return jsonify({"ok": True, **literature.search(query, int(request.args.get("limit", 8)))})

    @app.post("/api/complete")
    def complete_node():
        _topic, _graph_file, agent = current()
        payload = request.get_json(force=True) or {}
        ready, why = workspace.ai_ready()
        if not ready:
            return jsonify({"ok": False, "message": why}), 503
        draft = payload.get("node") or {}
        if not str(draft.get("label", "")).strip():
            return jsonify({"ok": False, "message": "Give at least a label."}), 400
        try:
            return jsonify(agent.complete_node(draft, payload.get("links") or []))
        except Exception as exc:
            return jsonify({"ok": False, "message": f"{type(exc).__name__}: {exc}"}), 500

    @app.post("/api/answer/stream")
    def answer_stream():
        topic, graph_file, agent = current()
        payload = request.get_json(force=True) or {}
        query = str(payload.get("query", "")).strip()
        if not query:
            return jsonify({"ok": False, "message": "query is required."}), 400
        ready, why = workspace.ai_ready()
        if not ready:
            return jsonify({"ok": False, "message": why}), 503

        def events():
            try:
                mode = "build" if payload.get("mode") == "build" else "chat"
                for event in agent.stream_answer(query, payload.get("history") or [], payload.get("context_ids") or [], mode=mode):
                    if event.get("type") == "proposal":
                        proposals[event["proposal"]["id"]] = {**event["proposal"], "_graph": str(graph_file.path)}
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            except Exception as exc:
                yield json.dumps({"type": "error", "message": str(exc), "error": type(exc).__name__}, ensure_ascii=False) + "\n"

        response = Response(stream_with_context(events()), content_type="application/x-ndjson; charset=utf-8")
        response.headers["Cache-Control"] = "no-cache, no-transform"
        response.headers["X-Accel-Buffering"] = "no"
        return response

    return app
