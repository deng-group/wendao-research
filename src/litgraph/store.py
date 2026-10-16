"""The knowledge graph on disk: graph.json, its schema, validation, and edits.

Five levels of nodes (family, technique, paper, claim, quantity) and typed edges; see docs/GRAPH_SCHEMA.md.
Every node records where it came from (`source`) and whether the researcher has confirmed it (`status`).
"""

from __future__ import annotations

import json
import re
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

GRAPH_SCHEMA = "2.0"

# The five levels, in order.
NODE_TYPES = {
    "family": "Method family",
    "technique": "Technique",
    "paper": "Paper",
    "claim": "Claim",
    "quantity": "Quantity",
}
EDGE_TYPES = {
    "contains": "contains",          # family -> technique / paper
    "uses": "uses",                  # paper -> technique
    "extends": "extends",            # paper -> paper, technique -> technique
    "contrasts": "contrasts with",   # paper <-> paper, technique <-> technique, family <-> family
    "supports": "supports",          # paper -> claim
    "contradicts": "contradicts",    # paper -> claim
    "about": "is about",             # claim -> technique / family / quantity
    "validates": "validates",        # paper -> quantity
    "relates": "relates to",         # anything, labelled
}
VALIDATION_LEVELS = ("structural", "thermodynamic", "kinetic", "transport", "mechanistic")
CLAIM_STATUSES = ("supported", "contradicted", "contested", "hypothesis", "open")
STATUSES = {"seed", "confirmed", "proposed"}
SOURCES = {"review", "chat", "search", "manual", "extract"}

# Extra fields per type, beyond id/type/label/summary/aliases/tags/status/source. (required, optional)
TYPE_FIELDS = {
    "family": ((), ("keeps", "discards", "computes", "relevance")),
    "technique": ((), ("reference",)),
    "paper": (("year", "authors", "venue", "learns", "discards", "validated_at"), ("doi", "url", "priority", "notes")),
    "claim": (("claim_status",), ("scope",)),
    "quantity": (("definition", "level"), ("symbol", "units")),
}
LIST_FIELDS = {"aliases", "tags", "validated_at"}
INT_FIELDS = {"year", "relevance", "priority"}


class GraphError(ValueError):
    pass


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:60] or "node"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_list(value) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        value = [part for part in re.split(r"[,;]", value)]
    return [str(item).strip() for item in value if str(item).strip()]


def clean_node(raw: dict, *, default_status: str = "confirmed", default_source: str = "manual") -> dict:
    """A node with every field checked and defaults filled in. Raises GraphError on a bad one."""
    if not isinstance(raw, dict):
        raise GraphError("A node must be an object.")
    label = str(raw.get("label", "")).strip()
    if not label:
        raise GraphError("A node needs a label.")
    node_type = str(raw.get("type", "")).strip().lower()
    if node_type not in NODE_TYPES:
        raise GraphError(f"Unknown node type `{node_type}` for `{label}`; use one of {', '.join(NODE_TYPES)}.")
    node_id = str(raw.get("id") or f"{node_type}:{slug(label)}").strip()
    node = {
        "id": node_id,
        "type": node_type,
        "label": label,
        "summary": str(raw.get("summary", "")).strip(),
        "aliases": _as_list(raw.get("aliases")),
        "status": raw.get("status") if raw.get("status") in STATUSES else default_status,
        "source": raw.get("source") if raw.get("source") in SOURCES else default_source,
        "tags": _as_list(raw.get("tags")),
        "created": str(raw.get("created") or now()),
    }
    required, optional = TYPE_FIELDS[node_type]
    for key in (*required, *optional):
        value = raw.get(key)
        if value in (None, "", []):
            continue
        if key in LIST_FIELDS:
            node[key] = _as_list(value)
        elif key in INT_FIELDS:
            match = re.search(r"\d{1,4}", str(value))
            if match:
                node[key] = int(match.group())
        else:
            node[key] = str(value).strip()
    if node_type == "paper" and "validated_at" in node:
        bad = [level for level in node["validated_at"] if level.lower() not in VALIDATION_LEVELS]
        if bad:
            raise GraphError(f"`{label}`: validated_at must use {', '.join(VALIDATION_LEVELS)}, not {', '.join(bad)}.")
        node["validated_at"] = [level.lower() for level in node["validated_at"]]
    if node_type == "quantity" and "level" in node and node["level"].lower() not in VALIDATION_LEVELS:
        raise GraphError(f"`{label}`: level must be one of {', '.join(VALIDATION_LEVELS)}.")
    if node_type == "quantity" and "level" in node:
        node["level"] = node["level"].lower()
    if node_type == "claim" and "claim_status" in node and node["claim_status"].lower() not in CLAIM_STATUSES:
        raise GraphError(f"`{label}`: claim_status must be one of {', '.join(CLAIM_STATUSES)}.")
    if node_type == "claim" and "claim_status" in node:
        node["claim_status"] = node["claim_status"].lower()
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

    # ---------- the rules (docs/GRAPH_SCHEMA.md) ----------
    def check(self, node_ids: list[str] | None = None) -> tuple[list[str], list[str]]:
        """(hard problems, soft problems) for the nodes given (default: all). Hard problems block a proposal."""
        hard, soft = [], []
        nodes = [n for n in self.nodes if node_ids is None or n["id"] in node_ids]
        by_label: dict[str, str] = {}
        for node in self.nodes:
            for name in (node["label"], *node["aliases"]):
                key = name.lower()
                if key in by_label and by_label[key] != node["id"] and (node_ids is None or node["id"] in node_ids):
                    soft.append(f"`{node['id']}` shares the name `{name}` with `{by_label[key]}`.")
                by_label.setdefault(key, node["id"])
        for node in nodes:
            nid, kind = node["id"], node["type"]
            edges = self.edges_of(nid)
            incoming = lambda t: [e for e in edges if e["type"] == t and e["target"] == nid]  # noqa: E731
            outgoing = lambda t: [e for e in edges if e["type"] == t and e["source"] == nid]  # noqa: E731
            if kind == "paper":
                families = [e for e in incoming("contains") if (self.node(e["source"]) or {}).get("type") == "family"]
                if len(families) != 1:
                    hard.append(f"Paper `{nid}` must have exactly one `contains` edge from a family (has {len(families)}).")
                if not outgoing("uses"):
                    hard.append(f"Paper `{nid}` must `use` at least one technique.")
                missing = [k for k in ("year", "authors", "venue", "learns", "discards", "validated_at") if not node.get(k)]
                if missing:
                    hard.append(f"Paper `{nid}` is missing {', '.join(missing)}.")
            elif kind == "technique":
                families = [e for e in incoming("contains") if (self.node(e["source"]) or {}).get("type") == "family"]
                if not families:
                    hard.append(f"Technique `{nid}` must have a `contains` edge from a family.")
                used = incoming("uses") or [e for e in edges if e["type"] == "extends"]
                if not used and not any(n.get("reference") == nid for n in self.nodes):
                    hard.append(f"Technique `{nid}` must be used by at least one paper.")
            elif kind == "claim":
                if not node.get("claim_status"):
                    hard.append(f"Claim `{nid}` needs claim_status ({', '.join(CLAIM_STATUSES)}).")
                if not outgoing("about"):
                    hard.append(f"Claim `{nid}` must have an `about` edge to a technique, family or quantity.")
                if node.get("claim_status") not in ("open", "hypothesis") and not (incoming("supports") or incoming("contradicts")):
                    hard.append(f"Claim `{nid}` with status {node.get('claim_status')} needs a `supports` or `contradicts` edge from a paper.")
            elif kind == "quantity":
                missing = [k for k in ("definition", "level") if not node.get(k)]
                if missing:
                    hard.append(f"Quantity `{nid}` is missing {', '.join(missing)}.")
            elif kind == "family":
                if not node["summary"]:
                    hard.append(f"Family `{nid}` needs a summary explaining the idea; keeps / discards / computes are separate fields.")
        for edge in self.edges:
            if node_ids is not None and edge["source"] not in node_ids and edge["target"] not in node_ids:
                continue
            if edge["type"] in ("contrasts", "relates") and not edge["label"]:
                soft.append(f"Edge {edge['source']} -{edge['type']}-> {edge['target']} needs a label.")
        return hard, soft

    # ---------- editing ----------
    def upsert_node(self, raw: dict, *, status: str = "confirmed", source: str = "manual") -> tuple[dict, bool]:
        """Add a node, or update the fields given for an existing id. Returns (node, created)."""
        node = clean_node(raw, default_status=status, default_source=source)
        existing = self.node(node["id"])
        if existing is None:
            # A new node whose label matches an existing one of the same type is the same thing: update it instead.
            match = next((n for n in self.nodes if n["label"].lower() == node["label"].lower() and n["type"] == node["type"]), None)
            if match is not None:
                existing = match
        if existing is None:
            self.nodes.append(node)
            return node, True
        if existing["type"] != node["type"] and "type" in raw:
            existing["type"] = node["type"]
        for key, value in node.items():
            if key in ("id", "created", "status", "source", "type"):
                continue
            if key in ("aliases", "tags"):
                existing[key] = sorted(set(existing.get(key, [])) | set(value))
            elif value not in ("", None, []) and (key in raw or key not in existing):
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

    def resolve(self, ref: str, by_label: dict[str, str] | None = None) -> str:
        """A node id from an id, a label or an alias (case-insensitive); the text itself if nothing matches."""
        ref = str(ref or "").strip()
        if self.node(ref):
            return ref
        low = ref.lower()
        if by_label and low in by_label:
            return by_label[low]
        for node in self.nodes:
            if node["label"].lower() == low or low in (alias.lower() for alias in node["aliases"]):
                return node["id"]
        return ref

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
        for raw in change.get("edges", []) or []:
            if not isinstance(raw, dict):
                report["errors"].append("An edge must be an object.")
                continue
            raw = {**raw, "source": self.resolve(raw.get("source", ""), by_label), "target": self.resolve(raw.get("target", ""), by_label)}
            try:
                edge, created = self.add_edge(raw, status=status, source=source)
            except GraphError as exc:
                report["errors"].append(str(exc))
                continue
            report["added_edges" if created else "updated_edges"].append([edge["source"], edge["target"], edge["type"]])
        for node_id in change.get("remove_nodes", []) or []:
            if self.remove_node(self.resolve(node_id, by_label)):
                report["removed_nodes"].append(node_id)
        for raw in change.get("remove_edges", []) or []:
            if isinstance(raw, dict) and self.remove_edge(self.resolve(raw.get("source", ""), by_label), self.resolve(raw.get("target", ""), by_label), raw.get("type")):
                report["removed_edges"].append([raw.get("source"), raw.get("target")])
        return report

    # ---------- for the model ----------
    def outline(self, max_summary: int = 240) -> str:
        """The whole graph as compact text for the model's context: nodes by level, then edges."""
        lines = [f"# {self.title}", self.description.strip(), "", "## Nodes, by level (id | label | fields | summary)"]
        for node_type, title in NODE_TYPES.items():
            nodes = [node for node in self.nodes if node["type"] == node_type]
            if not nodes:
                continue
            lines.append(f"### {title}")
            for node in nodes:
                bits = []
                if node_type == "paper":
                    bits.append(f"{node.get('authors', '?')} ({node.get('year', '?')}), {node.get('venue', '?')}")
                    if node.get("learns"):
                        bits.append(f"learns: {node['learns']}")
                    if node.get("discards"):
                        bits.append(f"discards: {node['discards']}")
                    if node.get("validated_at"):
                        bits.append("validated at: " + ", ".join(node["validated_at"]))
                elif node_type == "claim":
                    bits.append(f"status: {node.get('claim_status', '?')}")
                elif node_type == "quantity":
                    bits.append(f"{node.get('level', '?')}; definition: {node.get('definition', '')}")
                elif node_type == "family":
                    for key in ("keeps", "discards", "computes"):
                        if node.get(key):
                            bits.append(f"{key}: {node[key]}")
                    if node.get("relevance"):
                        bits.append(f"relevance {node['relevance']}/5")
                if node["status"] != "confirmed":
                    bits.append(f"[{node['status']}]")
                summary = node["summary"].replace("\n", " ")
                if len(summary) > max_summary:
                    summary = summary[: max_summary - 1] + "…"
                lines.append(f"- {node['id']} | {node['label']} | {'; '.join(bits)} | {summary}")
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
        required, optional = TYPE_FIELDS[node["type"]]
        for key in (*required, *optional, "aliases", "tags"):
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
