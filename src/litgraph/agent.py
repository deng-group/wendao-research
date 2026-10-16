"""The research agent: Claude with the graph in context, tools to read and grow it, and literature search.

A turn streams NDJSON events: `start`, `delta` (answer text), `status` (what a tool is doing),
`proposal` (nodes and edges the model added to the graph as proposed), `done`, `error`.
"""

from __future__ import annotations

import copy
import json
import uuid
from typing import Iterator

from litgraph import literature
from litgraph.store import EDGE_TYPES, NODE_TYPES, GraphFile

MAX_TOOL_ROUNDS = 10

ROLE = """You are a research companion for one researcher. You and they maintain a knowledge graph of a research
field: nodes are research questions, goals, method families, papers, methods, concepts, open problems and
applications; edges are typed links between them. The whole graph is given below. Your jobs:

1. Answer questions about the field using the graph first. When you use a node, name it and give its id in
   square brackets, e.g. LiFlow [paper:nam2025-liflow], so the interface can link it.
2. Go beyond the graph when asked, or when the graph can't answer: search the literature (search_literature
   for papers with metadata; web search for anything else) and say clearly which claims come from the graph,
   which from a search, and which are your own reasoning. Never invent papers, authors, years or DOIs: a paper
   you add must come from a search result or from the researcher.
3. Grow the graph: when you find something worth keeping (a paper, a concept, a link between two nodes, a
   refinement of a summary), call propose_graph_changes. Keep proposals small and specific: a few nodes and
   the edges that connect them to existing nodes, each with a one-sentence summary that a collaborator could
   check. Reuse existing node ids; never duplicate a node that exists under another name (use find_nodes
   first when unsure). A proposed change is marked "proposed" in the graph until the researcher confirms it.
4. Be precise about terminology: use the standard name of a method or quantity, define a quantity the first
   time you name it, and separate what is measured from what is interpreted. Separate what a paper claims
   from what it shows. Say what is uncertain.

Always write in English, whatever language the researcher writes in. Keep answers
compact: short paragraphs, lists for parallel items, no filler.

Node types: {node_types}
Edge types: {edge_types}
"""


def tool_definitions(workspace) -> list[dict]:
    tools = [
        {
            "name": "find_nodes",
            "description": "Find nodes in the graph whose id, label or alias contains the text. Use before adding a node.",
            "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"],
                             "additionalProperties": False},
            "strict": True,
        },
        {
            "name": "read_node",
            "description": "The full record of one node: metadata, summary and every link, with the linked nodes' ids.",
            "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"],
                             "additionalProperties": False},
            "strict": True,
        },
        {
            "name": "propose_graph_changes",
            "description": (
                "Add or update nodes and edges in the knowledge graph. New nodes are marked proposed until the "
                "researcher confirms them. Edges may name nodes by an existing id or by the label of a node in the "
                "same call. Give `reason`: one sentence on why these belong in the graph."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                    "nodes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string", "description": "Existing id to update, or a new id like paper:lastname2024-keyword"},
                                "type": {"type": "string", "enum": list(NODE_TYPES)},
                                "label": {"type": "string"},
                                "summary": {"type": "string", "description": "One to three sentences a collaborator could verify"},
                                "year": {"type": "integer"},
                                "authors": {"type": "string"},
                                "venue": {"type": "string"},
                                "doi": {"type": "string"},
                                "url": {"type": "string"},
                                "aliases": {"type": "array", "items": {"type": "string"}},
                                "tags": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["type", "label", "summary"],
                        },
                    },
                    "edges": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "string"},
                                "target": {"type": "string"},
                                "type": {"type": "string", "enum": list(EDGE_TYPES)},
                                "label": {"type": "string", "description": "Short phrase for the link, e.g. 'adds many-body memory'"},
                                "note": {"type": "string"},
                            },
                            "required": ["source", "target", "type"],
                        },
                    },
                },
                "required": ["reason"],
            },
        },
    ]
    if workspace.literature_search:
        tools.append({
            "name": "search_literature",
            "description": (
                "Search the scholarly literature (Semantic Scholar, then Crossref, then arXiv) for papers matching a "
                "query: titles, authors, year, venue, DOI, abstract, citation count. Use it to find papers to add, to "
                "check a paper's details, or to find what cites or extends a method."
            ),
            "input_schema": {"type": "object", "properties": {"query": {"type": "string"},
                                                              "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
                             "required": ["query"], "additionalProperties": False},
        })
    if workspace.web_search:
        tools.append({"type": "web_search_20260209", "name": "web_search", "max_uses": 6})
        tools.append({"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 6, "max_content_tokens": 20000})
    return tools


class Agent:
    def __init__(self, workspace, graph_file: GraphFile, client=None):
        self.workspace = workspace
        self.graph_file = graph_file
        self._client = client

    # ---------- the model ----------
    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def system(self) -> list[dict]:
        instructions = self.workspace.instructions().strip()
        role = ROLE.format(node_types=", ".join(f"{k} ({v})" for k, v in NODE_TYPES.items()),
                           edge_types=", ".join(f"{k} ({v})" for k, v in EDGE_TYPES.items()))
        stable = role + ("\n\n# The researcher's instructions\n\n" + instructions if instructions else "")
        return [
            {"type": "text", "text": stable},
            {"type": "text", "text": "# The knowledge graph\n\n" + self.graph_file.graph.outline(),
             "cache_control": {"type": "ephemeral"}},
        ]

    def request(self, messages: list[dict], tools: list[dict]) -> dict:
        params = {
            "model": self.workspace.model,
            "max_tokens": self.workspace.max_tokens,
            "system": self.system(),
            "messages": messages,
            "tools": tools,
            "output_config": {"effort": self.workspace.effort},
        }
        if self.workspace.fallbacks:
            params["betas"] = ["server-side-fallback-2026-07-01"]
            params["fallbacks"] = "default"
        return params

    def _stream(self, params: dict):
        if self.workspace.fallbacks:
            return self.client.beta.messages.stream(**params)
        return self.client.messages.stream(**params)

    # ---------- tools ----------
    def run_tool(self, name: str, args: dict, proposals: list[dict]) -> tuple[str, dict | None]:
        """Run a client tool. Returns (text for the model, event for the interface or None)."""
        graph = self.graph_file.graph
        if name == "find_nodes":
            found = graph.find(str(args.get("text", "")))[:12]
            if not found:
                return "No matching nodes.", None
            return "\n".join(f"- {n['id']} | {n['label']} ({n['type']}, {n['status']})" for n in found), None
        if name == "read_node":
            return graph.node_detail(str(args.get("id", ""))), None
        if name == "search_literature":
            query = str(args.get("query", "")).strip()
            limit = int(args.get("limit") or 8)
            result = literature.search(query, limit)
            return literature.format_results(result), {"type": "status", "kind": "search", "text": f"Searched the literature: {query}",
                                                       "count": len(result["papers"]), "provider": result["provider"]}
        if name == "propose_graph_changes":
            return self.propose(args, proposals)
        return f"Unknown tool {name}.", None

    def propose(self, change: dict, proposals: list[dict]) -> tuple[str, dict | None]:
        # Check first on a copy, so a change with errors can be fixed by the model before anything is written.
        trial = copy.deepcopy(self.graph_file.graph)
        report = trial.apply(change, status="proposed", source="chat")
        if report["errors"] and not (report["added_nodes"] or report["added_edges"] or report["updated_nodes"]):
            return "Nothing applied. Errors:\n- " + "\n- ".join(report["errors"]), None
        status = "confirmed" if self.workspace.auto_apply else "proposed"
        report = self.graph_file.edit(lambda graph: graph.apply(change, status=status, source="chat"))
        proposal = {
            "id": uuid.uuid4().hex[:10], "reason": str(change.get("reason", "")), "status": status, **report,
            "nodes": [self.graph_file.graph.node(node_id) for node_id in report["added_nodes"] + report["updated_nodes"]],
        }
        proposals.append(proposal)
        summary = (f"Applied as {status}: {len(report['added_nodes'])} new nodes, {len(report['updated_nodes'])} updated, "
                   f"{len(report['added_edges'])} new edges.")
        if report["errors"]:
            summary += " Errors:\n- " + "\n- ".join(report["errors"])
        if report["added_nodes"]:
            summary += "\nNew node ids: " + ", ".join(report["added_nodes"])
        return summary, {"type": "proposal", "proposal": proposal}

    # ---------- a turn ----------
    def stream_answer(self, query: str, history: list[dict] | None = None, context_ids: list[str] | None = None) -> Iterator[dict]:
        graph = self.graph_file.graph
        context = [graph.node(node_id) for node_id in (context_ids or [])]
        context = [node for node in context if node]
        prefix = ""
        if context:
            prefix = "Selected in the graph: " + "; ".join(f"{n['label']} [{n['id']}] ({n['type']})" for n in context) + "\n\n"
        messages = []
        for turn in (history or [])[-8:]:
            if turn.get("role") in ("user", "assistant") and str(turn.get("content", "")).strip():
                messages.append({"role": turn["role"], "content": str(turn["content"])[:4000]})
        if messages and messages[0]["role"] != "user":
            messages = messages[1:]
        messages.append({"role": "user", "content": prefix + query})
        tools = tool_definitions(self.workspace)
        proposals: list[dict] = []
        answer_parts: list[str] = []
        yield {"type": "start", "model": self.workspace.model}
        for _round in range(MAX_TOOL_ROUNDS):
            params = self.request(messages, tools)
            with self._stream(params) as stream:
                for event in stream:
                    kind = getattr(event, "type", "")
                    if kind == "text":
                        answer_parts.append(event.text)
                        yield {"type": "delta", "text": event.text}
                    elif kind == "content_block_start":
                        block = event.content_block
                        if block.type == "server_tool_use":
                            yield {"type": "status", "kind": "web", "text": "Searching the web…" if block.name == "web_search" else "Reading a web page…"}
                        elif block.type == "text" and answer_parts and not answer_parts[-1].endswith("\n"):
                            answer_parts.append("\n\n")
                            yield {"type": "delta", "text": "\n\n"}
                response = stream.get_final_message()
            if response.stop_reason == "refusal":
                yield {"type": "error", "message": "The model declined this request."}
                return
            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content})
                continue
            tool_uses = [block for block in response.content if block.type == "tool_use"]
            if not tool_uses:
                break
            if response.stop_reason == "max_tokens":
                yield {"type": "error", "message": "The answer was cut off (max_tokens). Raise max_tokens in litgraph.toml."}
                return
            results = []
            for block in tool_uses:
                args = block.input if isinstance(block.input, dict) else {}
                try:
                    text, event = self.run_tool(block.name, args, proposals)
                except Exception as exc:  # a tool failure is reported to the model, not fatal
                    text, event = f"Tool error: {exc}", {"type": "status", "kind": "error", "text": f"{block.name} failed: {exc}"}
                if event:
                    yield event
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": text})
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": results})
        answer = "".join(answer_parts).strip()
        yield {"type": "done", "answer": answer, "proposals": proposals,
               "graph_version": self.graph_file.path.stat().st_mtime if self.graph_file.path.exists() else 0}

    # ---------- a document into graph changes ----------
    def _extract_schema(self) -> dict:
        proposal = next(t for t in tool_definitions(self.workspace) if t.get("name") == "propose_graph_changes")
        schema = {
            "type": "object",
            "properties": {"nodes": copy.deepcopy(proposal["input_schema"]["properties"]["nodes"]),
                           "edges": copy.deepcopy(proposal["input_schema"]["properties"]["edges"])},
            "required": ["nodes", "edges"],
            "additionalProperties": False,
        }
        for key in ("nodes", "edges"):  # structured outputs need closed schemas
            schema["properties"][key]["items"]["additionalProperties"] = False
            schema["properties"][key]["items"]["required"] = list(schema["properties"][key]["items"]["properties"])
        return schema

    @staticmethod
    def _extract_instruction(text: str, title: str = "") -> str:
        return (
            "Read the document and extract a knowledge graph: the research questions and goals it poses, method "
            "families, papers (with year, authors, venue, DOI when given), key concepts, open problems and "
            "applications, and the typed links between them that the document itself states. Give every node a "
            "one-to-three sentence summary taken from the document. Reuse ids of nodes already in the graph (listed "
            "in your context) instead of making new ones. Use null or an empty string for fields the document does "
            "not give; never invent metadata.\n\n"
            + (f"# {title}\n\n" if title else "") + text
        )

    def extract(self, text: str, title: str = "") -> dict:
        """Read a document (a review, notes) and return a change set to apply to the graph."""
        params = {
            "model": self.workspace.model, "max_tokens": max(self.workspace.max_tokens, 32000),
            "system": self.system(), "messages": [{"role": "user", "content": self._extract_instruction(text, title)}],
            "output_config": {"effort": self.workspace.effort, "format": {"type": "json_schema", "schema": self._extract_schema()}},
        }
        with self.client.messages.stream(**params) as stream:
            response = stream.get_final_message()
        raw = next((block.text for block in response.content if block.type == "text"), "{}")
        change = json.loads(raw)
        for node in change.get("nodes", []):
            for key in list(node):
                if node[key] in (None, "", []):
                    del node[key]
        return change


def make_agent(workspace, graph_file: GraphFile, client=None) -> Agent:
    """The agent for the workspace's provider: `anthropic` (Messages API) or `claude-code` (Claude Code sign-in)."""
    if workspace.provider == "claude-code":
        from litgraph.claude_code import ClaudeCodeAgent
        return ClaudeCodeAgent(workspace, graph_file, client=client)
    return Agent(workspace, graph_file, client=client)
