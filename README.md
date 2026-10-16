# litgraph

**litgraph** turns a literature review into a knowledge graph you can explore, and gives you a research
companion (Claude) that answers questions from the graph, searches the literature when the graph runs out,
and adds what you find together back into the graph.

It grew out of [Wendao](https://github.com/deng-group/wendao), the AI learning companion for courses, and lives at [deng-group/wendao-research](https://github.com/deng-group/wendao-research).
Wendao's agent answers only from the course materials; litgraph's agent is meant to go further: the graph is
the starting point, not the boundary.

- **Interactive knowledge graph**: research questions, goals, method families, papers, methods, concepts,
  open problems and applications, linked by typed edges (`contains`, `uses`, `extends`, `contrasts`, …).
  Drag, zoom, search; click a node for its summary, metadata, DOI and links; edit or add nodes by hand.
- **Research companion** on the right: ask about any node or about the field. The agent reads the whole graph,
  can search Semantic Scholar / Crossref / arXiv for papers and the web for anything else, and proposes
  nodes and edges. Proposals appear in the graph at once, marked *proposed* (dashed ring), until you keep or
  discard them.
- **`litgraph extract`**: turn a review or your notes into graph nodes and edges with the model.
- **`litgraph export`**: the graph as one HTML file that opens without a server.

## Install

Python 3.11 or newer.

```bash
git clone https://github.com/deng-group/wendao-research.git
cd wendao-research
pip install -e .              # or `uv sync`
```

## Quick start

```bash
litgraph init my-field        # a workspace: litgraph.toml, AGENTS.md, graph.json, notes/
cd my-field
# either write graph.json by hand / with the editor in the website,
# or drop a review into notes/ and let the model extract a first graph:
litgraph extract notes/review.md
litgraph serve                # http://127.0.0.1:5058/
```

By default the chat runs through **Claude Code** with your own sign-in (the `claude` CLI; a claude.ai
subscription), so no API key is needed: sign in once with `claude` in a terminal. To use the Messages API
with an API key instead, set `provider = "anthropic"` under `[model]` in `litgraph.toml` and put
`ANTHROPIC_API_KEY` in `.env`. `litgraph check` validates the graph and makes one test call to the model.

### The example

`examples/md_coarse_graining/` is a built workspace: a review of molecular-dynamics coarse-graining and
acceleration methods (seven method families, about twenty papers) read against Li-ion transport in
solid-state electrolytes. The graph was written from the review by hand (51 nodes, 107 edges).

```bash
cd examples/md_coarse_graining
litgraph check                # graph + one test call through Claude Code
litgraph serve
```

## How the agent works

Two providers, chosen with `provider` under `[model]` in `litgraph.toml`, give the model the same context,
tools and events:

- **`claude-code`** (default): the turn runs through Claude Code via the Claude Agent SDK, which uses the
  CLI bundled with the SDK (or `cli_path`) and your Claude Code sign-in. The four graph tools run in this
  process as an in-process MCP server; web search and web fetch are Claude Code's own `WebSearch` and
  `WebFetch`. Your `CLAUDE.md` and Claude Code settings are not loaded (`setting_sources = []`), and no
  other tools are allowed.
- **`anthropic`**: one request to the Anthropic Messages API with an API key, the tools defined inline,
  and Anthropic's server-side `web_search` / `web_fetch`.

With either, the request carries:

- a system prompt: the agent's role, your `AGENTS.md` (your research, terminology rules, what belongs in the
  graph), and the whole graph as compact text (cached with prompt caching);
- the recent conversation (kept in the browser, session only) and the node you selected;
- tools: `find_nodes`, `read_node`, `search_literature` (Semantic Scholar → Crossref → arXiv, no key needed),
  `propose_graph_changes`, and Anthropic's server-side `web_search` and `web_fetch`.

`propose_graph_changes` validates the change on a copy first (unknown ids, bad types) so the model can fix
it, then writes it to `graph.json` with status `proposed`. Every write keeps a `graph.backup.json`. With
`auto_apply = true` in `litgraph.toml` additions go in as confirmed.

`name` under `[model]` picks the model (unset: Claude Code's default, or `claude-opus-5-5` for the API);
`effort` controls how hard it thinks. An API key is read from `.env` or the environment (`ANTHROPIC_API_KEY`)
and only matters for `provider = "anthropic"`.

## Graph format

`graph.json`:

```json
{"schema": "1.0", "title": "…", "description": "…",
 "nodes": [{"id": "paper:nam2025-liflow", "type": "paper", "label": "LiFlow …", "summary": "…",
            "year": 2025, "authors": "…", "venue": "…", "doi": "…", "aliases": ["LiFlow"],
            "status": "seed", "source": "review"}],
 "edges": [{"source": "category:f", "target": "paper:nam2025-liflow", "type": "contains", "label": ""}]}
```

Node types: `question`, `goal`, `category`, `paper`, `method`, `concept`, `challenge`, `application`, `note`.
Edge types: `contains`, `addresses`, `uses`, `serves`, `extends`, `contrasts`, `relates`, `applies_to`,
`raises`, `validates`. `status` is `seed` (from the initial review), `confirmed`, or `proposed`;
`source` records where a node came from (`review`, `chat`, `search`, `manual`, `extract`).

## Layout

| Folder | What's in it |
| --- | --- |
| `src/litgraph/store.py` | `graph.json`: schema, validation, edits, the text outline the model reads |
| `src/litgraph/agent.py` | The tools, prompts and the Messages API tool loop, streamed as NDJSON events |
| `src/litgraph/claude_code.py` | The same agent run through Claude Code (Claude Agent SDK, in-process MCP tools) |
| `src/litgraph/literature.py` | Semantic Scholar, Crossref and arXiv lookups |
| `src/litgraph/server.py` | Flask: the page, graph API, proposals, chat stream |
| `src/litgraph/static/` | The website: canvas graph with its own force layout, node card, editor, chat |
| `examples/md_coarse_graining/` | The example workspace |
| `tests/` | Unit tests; the agent is tested against a local fake of the Messages API |

```bash
python -m unittest discover -s tests -t .
```

## License

GPL-3.0-or-later, like Wendao.
