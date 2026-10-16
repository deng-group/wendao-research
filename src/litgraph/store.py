"""The knowledge graph on disk: graph.json, its schema, validation, and edits.

A graph has nodes (papers, methods, concepts, ...) and edges (typed, labelled links).
Every node and edge records where it came from (`source`: the review, a chat, a search,
or a manual edit) and whether it has been confirmed by the researcher (`status`).
"""

from __future__ import annotations

import json
import re
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

GRAPH_SCHEMA = "1.0"

NODE_TYPES = {
    "question": "Research question",
    "goal": "Goal",
    "category": "Method family",
    "paper": "Paper",
    "method": "Method",
    "concept": "Concept",
    "challenge": "Open problem",
    "application": "Application",
    "note": "Note",
}
EDGE_TYPES = {
    "contains": "contains",          # category -> paper / method
    "addresses": "addresses",        # paper / method -> goal / question / challenge
    "uses": "uses",                  # paper / method -> concept / method
    "serves": "serves",              # category -> goal
    "extends": "extends",            # paper -> paper (builds on)
    "contrasts": "contrasts with",   # paper <-> paper, concept <-> concept
    "relates": "relates to",         # anything, with a label
    "applies_to": "applies to",      # method / category -> application
    "raises": "raises",              # category / paper -> challenge
    "validates": "validated by",     # method -> concept (validation metric)
}
STATUSES = {"seed", "confirmed", "proposed"}
SOURCES = {"review", "chat", "search", "manual", "extract"}


class GraphError(ValueError):
    pass


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:60] or "node"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_node(raw: dict, *, default_status: str = "confirmed", default_source: str = "manual") -> dict:
    """A node with every field checked and defaults filled in. Raises GraphError on a bad one."""
    if not isinstance(raw, dict):
        raise GraphError("A node must be an object.")
    label = str(raw.get("label", "")).strip()
    if not label:
        raise GraphError("A node needs a label.")
    node_type = str(raw.get("type", "concept")).strip().lower()
    if node_type not in NODE_TYPES:
        raise GraphError(f"Unknown node type `{node_type}` for `{label}`; use one of {', '.join(NODE_TYPES)}.")
    node_id = str(raw.get("id") or f"{node_type}:{slug(label)}").strip()
    node = {
        "id": node_id,
        "type": node_type,
        "label": label,
        "summary": str(raw.get("summary", "")).strip(),
        "aliases": [str(a).strip() for a in raw.get("aliases", []) if str(a).strip()],
        "status": raw.get("status") if raw.get("status") in STATUSES else default_status,
        "source": raw.get("source") if raw.get("source") in SOURCES else default_source,
        "tags": [str(t).strip() for t in raw.get("tags", []) if str(t).strip()],
        "created": str(raw.get("created") or now()),
    }
    for key in ("year", "authors", "venue", "doi", "url", "notes", "key"):
        value = raw.get(key)
        if value not in (None, "", []):
            node[key] = value if key == "year" and isinstance(value, int) else str(value).strip()
    if "year" in node and not isinstance(node["year"], int):
        match = re.search(r"\d{4}", node["year"])
        if match:
            node["year"] = int(match.group())
        else:
            del node["year"]
    return node


def clean_edge(raw: dict, *, default_status: str = "confirmed", default_source: str = "manual") -> dict:
    if not isinstance(raw, dict):
        raise GraphError("An edge must be an object.")
    source, target = str(raw.get("source", "")).strip(), str(raw.get("target", "")).strip()
    if not source or not target:
        raise GraphError("An edge needs a source and a target node id.")
    if source == target:
        raise GraphError(f"An edge can't link `{source}` to itself.")
    edge_type = str(raw.get("type", "relates")).strip().lower()
    if edge_type not in EDGE_TYPES:
        raise GraphError(f"Unknown edge type `{edge_type}`; use one of {', '.join(EDGE_TYPES)}.")
    edge = {
        "source": source,
        "target": target,
        "type": edge_type,
        "label": str(raw.get("label", "")).strip(),
        "note": str(raw.get("note", "")).strip(),
        "status": raw.get("status") if raw.get("status") in STATUSES else default_status,
        "source_kind": raw.get("source_kind") if raw.get("source_kind") in SOURCES else default_source,
    }
    if isinstance(raw.get("weight"), (int, float)):
        edge["weight"] = float(raw["weight"])
    return edge


@dataclass
class Graph:
    title: str = "Research knowledge graph"
    description: str = ""
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    schema: str = GRAPH_SCHEMA

    # ---------- reading ----------
    @classmethod
    def from_dict(cls, data: dict) -> "Graph":
        graph = cls(
            title=str(data.get("title", "Research knowledge graph")),
            description=str(data.get("description", "")),
            schema=str(data.get("schema", GRAPH_SCHEMA)),
        )
        for raw in data.get("nodes", []):
            graph.nodes.append(clean_node(raw, default_status="seed", default_source="review"))
        ids = {node["id"] for node in graph.nodes}
        if len(ids) != len(graph.nodes):
            seen, dupes = set(), []
            for node in graph.nodes:
                if node["id"] in seen:
                    dupes.append(node["id"])
                seen.add(node["id"])
            raise GraphError(f"Duplicate node ids: {', '.join(sorted(set(dupes)))}")
        for raw in data.get("edges", []):
            edge = clean_edge(raw, default_status="seed", default_source="review")
            for end in ("source", "target"):
                if edge[end] not in ids:
                    raise GraphError(f"Edge {edge['source']} -> {edge['target']} points to an unknown node `{edge[end]}`.")
            graph.edges.append(edge)
        return graph

    @classmethod
    def load(cls, path: Path) -> "Graph":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self) -> dict:
        return {"schema": self.schema, "title": self.title, "description": self.description,
                "nodes": self.nodes, "edges": self.edges}

    def save(self, path: Path) -> None:
        path = Path(path)
        if path.exists():
            shutil.copyfile(path, path.with_suffix(".backup.json"))
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ---------- lookups ----------
    def node(self, node_id: str) -> dict | None:
        return next((node for node in self.nodes if node["id"] == node_id), None)

    def find(self, text: str) -> list[dict]:
        """Nodes whose id, label or an alias contains the text (case-insensitive), best match first."""
        needle = text.strip().lower()
        if not needle:
            return []
        scored = []
        for node in self.nodes:
            names = [node["id"].lower(), node["label"].lower(), *(a.lower() for a in node["aliases"])]
            if any(name == needle for name in names):
                scored.append((0, node))
            elif any(name.startswith(needle) for name in names):
                scored.append((1, node))
            elif any(needle in name for name in names):
                scored.append((2, node))
            elif needle in node["summary"].lower():
                scored.append((3, node))
        scored.sort(key=lambda item: (item[0], item[1]["label"]))
        return [node for _, node in scored]

    def edges_of(self, node_id: str) -> list[dict]:
        return [edge for edge in self.edges if node_id in (edge["source"], edge["target"])]

    def neighbours(self, node_id: str) -> list[tuple[dict, dict]]:
        """(edge, other node) pairs for every edge touching the node."""
        out = []
        for edge in self.edges_of(node_id):
            other = self.node(edge["target"] if edge["source"] == node_id else edge["source"])
            if other:
                out.append((edge, other))
        return out

    def has_edge(self, source: str, target: str, edge_type: str | None = None) -> bool:
        return any(
            {edge["source"], edge["target"]} == {source, target} and (edge_type is None or edge["type"] == edge_type)
            for edge in self.edges
        )

    # ---------- editing ----------
    def upsert_node(self, raw: dict, *, status: str = "confirmed", source: str = "manual") -> tuple[dict, bool]:
        """Add a node, or update the fields given for an existing id. Returns (node, created)."""
        node = clean_node(raw, default_status=status, default_source=source)
        existing = self.node(node["id"])
        if existing is None:
            # A new node whose label matches an existing one is the same thing: update it instead.
            match = next((n for n in self.nodes if n["label"].lower() == node["label"].lower() and n["type"] == node["type"]), None)
            if match is not None:
                existing = match
        if existing is None:
            self.nodes.append(node)
            return node, True
        for key, value in node.items():
            if key in ("id", "created", "status", "source"):
                continue
            if key in ("aliases", "tags"):
                existing[key] = sorted(set(existing.get(key, [])) | set(value))
            elif value not in ("", None) and (key in raw or key not in existing):
                existing[key] = value
        if raw.get("status") in STATUSES:
            existing["status"] = raw["status"]
        return existing, False

    def add_edge(self, raw: dict, *, status: str = "confirmed", source: str = "manual") -> tuple[dict, bool]:
        edge = clean_edge(raw, default_status=status, default_source=source)
        for end in ("source", "target"):
            if self.node(edge[end]) is None:
                raise GraphError(f"Edge {edge['source']} -> {edge['target']}: unknown node `{edge[end]}`.")
        for existing in self.edges:
            if existing["source"] == edge["source"] and existing["target"] == edge["target"] and existing["type"] == edge["type"]:
                if edge["label"]:
                    existing["label"] = edge["label"]
                if edge["note"]:
                    existing["note"] = edge["note"]
                return existing, False
        self.edges.append(edge)
        return edge, True

    def remove_node(self, node_id: str) -> bool:
        before = len(self.nodes)
        self.nodes = [node for node in self.nodes if node["id"] != node_id]
        self.edges = [edge for edge in self.edges if node_id not in (edge["source"], edge["target"])]
        return len(self.nodes) < before

    def remove_edge(self, source: str, target: str, edge_type: str | None = None) -> bool:
        before = len(self.edges)
        self.edges = [
            edge for edge in self.edges
            if not (edge["source"] == source and edge["target"] == target and (edge_type is None or edge["type"] == edge_type))
        ]
        return len(self.edges) < before

    def set_status(self, node_ids: list[str], status: str) -> int:
        if status not in STATUSES:
            raise GraphError(f"Unknown status `{status}`.")
        changed = 0
        for node in self.nodes:
            if node["id"] in node_ids and node["status"] != status:
                node["status"] = status
                changed += 1
        return changed

    def apply(self, change: dict, *, status: str = "confirmed", source: str = "chat") -> dict:
        """Apply a change set {nodes: [...], edges: [...], remove_nodes: [...], remove_edges: [...]}.

        Edges may name nodes by id or by the label of a node in the same change set. Returns what happened.
        """
        report = {"added_nodes": [], "updated_nodes": [], "added_edges": [], "updated_edges": [],
                  "removed_nodes": [], "removed_edges": [], "errors": []}
        by_label: dict[str, str] = {}
        for raw in change.get("nodes", []) or []:
            try:
                node, created = self.upsert_node(raw, status=status, source=source)
            except GraphError as exc:
                report["errors"].append(str(exc))
                continue
            by_label[node["label"].lower()] = node["id"]
            if raw.get("id"):
                by_label[str(raw["id"]).lower()] = node["id"]
            report["added_nodes" if created else "updated_nodes"].append(node["id"])

        def resolve(ref: str) -> str:
            ref = str(ref or "").strip()
            if self.node(ref):
                return ref
            if ref.lower() in by_label:
                return by_label[ref.lower()]
            low = ref.lower()
            for node in self.nodes:  # an exact label or alias, case-insensitive
                if node["label"].lower() == low or low in (alias.lower() for alias in node["aliases"]):
                    return node["id"]
            return ref

        for raw in change.get("edges", []) or []:
            if not isinstance(raw, dict):
                report["errors"].append("An edge must be an object.")
                continue
            raw = {**raw, "source": resolve(raw.get("source", "")), "target": resolve(raw.get("target", ""))}
            try:
                edge, created = self.add_edge(raw, status=status, source=source)
            except GraphError as exc:
                report["errors"].append(str(exc))
                continue
            report["added_edges" if created else "updated_edges"].append([edge["source"], edge["target"], edge["type"]])
        for node_id in change.get("remove_nodes", []) or []:
            if self.remove_node(resolve(node_id)):
                report["removed_nodes"].append(node_id)
        for raw in change.get("remove_edges", []) or []:
            if isinstance(raw, dict) and self.remove_edge(resolve(raw.get("source", "")), resolve(raw.get("target", "")), raw.get("type")):
                report["removed_edges"].append([raw.get("source"), raw.get("target")])
        return report

    # ---------- for the model ----------
    def outline(self, max_summary: int = 220) -> str:
        """The whole graph as compact text for the model's context: nodes by type, then edges."""
        lines = [f"# {self.title}", self.description.strip(), "", "## Nodes (id | label | summary)"]
        for node_type, title in NODE_TYPES.items():
            nodes = [node for node in self.nodes if node["type"] == node_type]
            if not nodes:
                continue
            lines.append(f"### {title}")
            for node in nodes:
                meta = " ".join(filter(None, [
                    f"({node['year']})" if node.get("year") else "",
                    f"[{node['status']}]" if node["status"] != "confirmed" else "",
                ]))
                summary = node["summary"].replace("\n", " ")
                if len(summary) > max_summary:
                    summary = summary[: max_summary - 1] + "…"
                lines.append(f"- {node['id']} | {node['label']}{' ' + meta if meta else ''} | {summary}")
        lines += ["", "## Edges (source -type-> target: label)"]
        for edge in self.edges:
            label = f": {edge['label']}" if edge["label"] else ""
            lines.append(f"- {edge['source']} -{edge['type']}-> {edge['target']}{label}")
        return "\n".join(lines)

    def node_detail(self, node_id: str) -> str:
        node = self.node(node_id)
        if not node:
            return f"No node with id `{node_id}`."
        lines = [f"# {node['label']} ({NODE_TYPES[node['type']]}, id {node['id']}, status {node['status']})"]
        for key in ("year", "authors", "venue", "doi", "url", "aliases", "tags", "notes"):
            if node.get(key):
                value = ", ".join(node[key]) if isinstance(node[key], list) else node[key]
                lines.append(f"- {key}: {value}")
        if node["summary"]:
            lines += ["", node["summary"]]
        lines += ["", "## Links"]
        for edge, other in self.neighbours(node_id):
            direction = "->" if edge["source"] == node_id else "<-"
            label = f" ({edge['label']})" if edge["label"] else ""
            note = f" — {edge['note']}" if edge["note"] else ""
            lines.append(f"- {direction} {edge['type']}{label}: {other['label']} [{other['id']}]{note}")
        return "\n".join(lines)


class GraphFile:
    """A graph that is re-read when the file changes on disk and written back after edits, safely across threads."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self._graph: Graph | None = None
        self._mtime: float | None = None

    @property
    def graph(self) -> Graph:
        with self.lock:
            mtime = self.path.stat().st_mtime if self.path.exists() else None
            if self._graph is None or mtime != self._mtime:
                self._graph = Graph.load(self.path) if self.path.exists() else Graph()
                self._mtime = mtime
            return self._graph

    def edit(self, work) -> dict:
        """Run `work(graph)` under the lock and save; returns what work returned."""
        with self.lock:
            graph = self.graph
            result = work(graph)
            graph.save(self.path)
            self._mtime = self.path.stat().st_mtime
            return result
