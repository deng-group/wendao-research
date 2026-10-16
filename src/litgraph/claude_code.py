"""The research agent run through Claude Code (the Claude Agent SDK) instead of the Messages API.

Same tools and events as `litgraph.agent.Agent`, but the model is driven by the Claude Code CLI, so it uses
the researcher's own Claude Code sign-in (a claude.ai subscription) and needs no API key. The four graph
tools run in this process as an in-process MCP server; web search and web fetch are Claude Code's own.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import Iterator

from litgraph import __version__
from litgraph.agent import Agent, tool_definitions

MAX_TURNS = 16
SERVER = "litgraph"


class ClaudeCodeAgent(Agent):
    """Answers through Claude Code. `client` is unused; the CLI's own sign-in is the credential."""

    def _options(self, system: str, tools: list, events: "queue.Queue | None", structured: dict | None = None):
        from claude_agent_sdk import ClaudeAgentOptions

        builtin = ["WebSearch", "WebFetch"] if self.workspace.web_search and not structured else []
        options = ClaudeAgentOptions(
            system_prompt=system,
            tools=builtin,
            allowed_tools=builtin + [f"mcp__{SERVER}__{tool.name}" for tool in tools],
            mcp_servers={SERVER: self._mcp_server(tools)} if tools else {},
            strict_mcp_config=True,
            setting_sources=[],  # the researcher's own CLAUDE.md and settings stay out of it
            permission_mode="dontAsk",
            include_partial_messages=True,
            max_turns=MAX_TURNS,
            cwd=self.workspace.root,
            env={"CLAUDE_AGENT_SDK_CLIENT_APP": f"litgraph/{__version__}"},
        )
        if self.workspace.model_configured:
            options.model = self.workspace.model
        if self.workspace.effort:
            options.effort = self.workspace.effort
        if self.workspace.cli_path:
            options.cli_path = self.workspace.cli_path
        if structured:
            options.output_format = {"type": "json_schema", "schema": structured}
        return options

    def _mcp_server(self, tools: list):
        from claude_agent_sdk import create_sdk_mcp_server

        return create_sdk_mcp_server(name=SERVER, version=__version__, tools=tools)

    def _tools(self, events: queue.Queue, proposals: list[dict]) -> list:
        """The graph tools as in-process MCP tools, sharing `Agent.run_tool`."""
        from claude_agent_sdk import tool

        made = []
        for definition in tool_definitions(self.workspace):
            if "input_schema" not in definition:
                continue  # server tools (web search) are Claude Code's own here
            name = definition["name"]

            def handler(args: dict, _name=name):
                text, event = self.run_tool(_name, args or {}, proposals)
                if event:
                    events.put(event)
                return {"content": [{"type": "text", "text": text}]}

            async def run(args: dict, _handler=handler):
                return await asyncio.to_thread(_handler, args)

            made.append(tool(name, definition["description"], definition["input_schema"])(run))
        return made

    def _prompt(self, query: str, history: list[dict] | None, context_ids: list[str] | None) -> str:
        graph = self.graph_file.graph
        context = [node for node in (graph.node(i) for i in (context_ids or [])) if node]
        parts = []
        turns = [t for t in (history or [])[-8:] if t.get("role") in ("user", "assistant") and str(t.get("content", "")).strip()]
        if turns:
            parts.append("Earlier in this conversation:\n" + "\n\n".join(
                f"{'Researcher' if t['role'] == 'user' else 'You'}: {str(t['content'])[:3000]}" for t in turns) + "\n\n---\n")
        if context:
            parts.append("Selected in the graph: " + "; ".join(f"{n['label']} [{n['id']}] ({n['type']})" for n in context) + "\n")
        parts.append(query)
        return "\n".join(parts)

    async def _run(self, prompt: str, events: queue.Queue, proposals: list[dict]) -> None:
        from claude_agent_sdk import AssistantMessage, ResultMessage, StreamEvent, TextBlock, ToolUseBlock, query

        try:
            from claude_agent_sdk import ServerToolUseBlock
        except ImportError:  # older SDKs
            ServerToolUseBlock = ()  # noqa: N806
        system = "\n\n".join(block["text"] for block in self.system())
        tools = self._tools(events, proposals)
        options = self._options(system, tools, events)
        answer: list[str] = []
        streamed = False
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, StreamEvent):
                if message.parent_tool_use_id:
                    continue
                event = message.event
                if event.get("type") == "content_block_delta" and (event.get("delta") or {}).get("type") == "text_delta":
                    text = event["delta"].get("text", "")
                    if text:
                        streamed = True
                        answer.append(text)
                        events.put({"type": "delta", "text": text})
                elif event.get("type") == "content_block_start" and (event.get("content_block") or {}).get("type") == "text" and answer and not answer[-1].endswith("\n"):
                    answer.append("\n\n")
                    events.put({"type": "delta", "text": "\n\n"})
            elif isinstance(message, AssistantMessage):
                if message.parent_tool_use_id:
                    continue
                for block in message.content:
                    if isinstance(block, TextBlock) and not streamed and block.text:
                        answer.append(block.text)
                        events.put({"type": "delta", "text": block.text})
                    elif isinstance(block, ToolUseBlock):
                        if block.name in ("WebSearch", "WebFetch"):
                            what = block.input.get("query") or block.input.get("url") or ""
                            events.put({"type": "status", "kind": "web", "text": f"{'Searching the web' if block.name == 'WebSearch' else 'Reading'}: {what}"[:160]})
                    elif ServerToolUseBlock and isinstance(block, ServerToolUseBlock):
                        events.put({"type": "status", "kind": "web", "text": "Searching the web…" if "search" in str(block.name) else "Reading a web page…"})
            elif isinstance(message, ResultMessage):
                if message.is_error:
                    detail = "; ".join(message.errors or []) or message.result or message.subtype
                    events.put({"type": "error", "message": f"Claude Code could not answer: {detail}"})
                    return
                if not answer and message.result:
                    answer.append(message.result)
                    events.put({"type": "delta", "text": message.result})
        events.put({"type": "done", "answer": "".join(answer).strip(), "proposals": proposals,
                    "graph_version": self.graph_file.path.stat().st_mtime if self.graph_file.path.exists() else 0})

    def stream_answer(self, query: str, history: list[dict] | None = None, context_ids: list[str] | None = None) -> Iterator[dict]:
        events: queue.Queue = queue.Queue()
        proposals: list[dict] = []
        prompt = self._prompt(query, history, context_ids)

        def worker():
            try:
                asyncio.run(self._run(prompt, events, proposals))
            except Exception as exc:  # reported to the browser, not raised in the request thread
                events.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
            finally:
                events.put(None)

        threading.Thread(target=worker, daemon=True).start()
        yield {"type": "start", "model": self.workspace.model if self.workspace.model_configured else "claude-code"}
        while True:
            event = events.get()
            if event is None:
                break
            yield event

    def extract(self, text: str, title: str = "") -> dict:
        from claude_agent_sdk import ResultMessage, query

        schema = self._extract_schema()
        instruction = self._extract_instruction(text, title)
        system = "\n\n".join(block["text"] for block in self.system())

        async def run() -> dict:
            result = None
            async for message in query(prompt=instruction, options=self._options(system, [], None, structured=schema)):
                if isinstance(message, ResultMessage):
                    result = message
            if result is None or result.is_error:
                raise RuntimeError("Claude Code could not extract a graph: " + ("; ".join(result.errors or []) if result else "no result"))
            data = result.structured_output
            if data is None and result.result:
                data = json.loads(result.result)
            return data or {}

        change = asyncio.run(run())
        for node in change.get("nodes", []):
            for key in list(node):
                if node[key] in (None, "", []):
                    del node[key]
        return change
