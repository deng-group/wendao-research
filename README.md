# litgraph

**litgraph** turns a literature review into a knowledge graph you can explore, and gives you a research
companion (Claude) that answers questions from the graph, searches the literature when the graph runs out,
and adds what you find together back into the graph.

It grew out of [Wendao](https://github.com/deng-group/wendao), the AI learning companion for courses, and lives at [deng-group/wendao-research](https://github.com/deng-group/wendao-research).
Wendao's agent answers only from the course materials; litgraph's agent is meant to go further: the graph is
the starting point, not the boundary.

- **Interactive knowledge graph in five levels**: method families, techniques, papers, claims and
  quantities, linked by typed edges (`contains`, `uses`, `extends`, `contrasts`, `supports`, `validates`, …).
  Show any subset of the levels; hidden levels leave dashed bridges between what they connected. Click a
  node for its structured record (a paper's learns / discards / validated-at, a claim's status and evidence,
  a quantity's definition); edit or add nodes by hand. The schema is in
  [docs/GRAPH_SCHEMA.md](docs/GRAPH_SCHEMA.md).
- **Research companion** on the right: ask about any node or about the field. The agent reads the whole graph,
  can search Semantic Scholar / Crossref / arXiv for papers and the web for anything else, and proposes
  nodes and edges. Proposals appear in the graph at once, marked *proposed* (dashed ring), until you keep or
  discard them.
- **Topics**: a workspace holds one graph and one review document per topic (`topics/<name>/graph.json`
  and `review.md`). Type a topic in the website: an existing one opens; a new one is created and the
  companion builds a first review of it from the literature, which you keep, edit, and save as a document
  with **Write review**.
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
litgraph init my-field        # a workspace: litgraph.toml, AGENTS.md, topics/
cd my-field
litgraph serve                # http://127.0.0.1:5058/ ; type a topic to start the first review
# or seed a topic from a document you already have:
litgraph extract --topic my-topic review.md
```

By default the chat runs through **Claude Code** with your own sign-in (the `claude` CLI; a claude.ai
subscription), so no API key is needed: sign in once with `claude` in a terminal. To use the Messages API
with an API key instead, set `provider = "anthropic"` under `[model]` in `litgraph.toml` and put
`ANTHROPIC_API_KEY` in `.env`. `litgraph check` validates the graph and makes one test call to the model.

### The example

`examples/md_coarse_graining/` is a built workspace with one topic, `topics/md-coarse-graining/`: a review
of molecular-dynamics coarse-graining and acceleration methods read against Li-ion transport in
solid-state electrolytes, as a document in the five-level form (`review.md`) and as a graph (`graph.json`:
7 families, 23 techniques, 20 papers, 14 claims, 11 quantities).

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

`propose_graph_changes` applies the change to a copy first and checks the schema's rules (a paper needs
exactly one family, at least one technique and its structured fields; a claim a status and an `about` edge;
a quantity a definition and a level). A proposal that breaks a rule is returned to the model with the reasons
and nothing is written; one that passes goes into `graph.json` with status `proposed`. Every write keeps a `graph.backup.json`. With
`auto_apply = true` in `litgraph.toml` additions go in as confirmed.

If your shell exports `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_MODEL` (a relay to another
model, say), Claude Code follows them instead of its sign-in; `litgraph check` says so. Set
`ignore_anthropic_env = true` under `[model]` to drop them and use the Claude Code sign-in.

`name` under `[model]` picks the model (unset: Claude Code's default, or `claude-opus-5-5` for the API);
`effort` controls how hard it thinks. An API key is read from `.env` or the environment (`ANTHROPIC_API_KEY`)
and only matters for `provider = "anthropic"`.

## Graph format

`graph.json` (schema 2.0; the full definition, fields and rules are in [docs/GRAPH_SCHEMA.md](docs/GRAPH_SCHEMA.md)):

```json
{"schema": "2.0", "title": "…", "description": "the research question",
 "nodes": [{"id": "paper:nam2025-liflow", "type": "paper", "label": "…", "summary": "…",
            "year": 2025, "authors": "…", "venue": "…", "doi": "…",
            "learns": "…", "discards": "…", "validated_at": ["transport", "structural"],
            "status": "seed", "source": "review"}],
 "edges": [{"source": "family:f", "target": "paper:nam2025-liflow", "type": "contains", "label": ""}]}
```

Levels: `family`, `technique`, `paper`, `claim`, `quantity`. Edge types: `contains`, `uses`, `extends`,
`contrasts`, `supports`, `contradicts`, `about`, `validates`, `relates`. `status` is `seed` (from the
initial review), `confirmed`, or `proposed`; `source` records where a node came from (`review`, `chat`,
`search`, `manual`, `extract`). `litgraph check` reports every rule violation.

## Layout

| Folder | What's in it |
| --- | --- |
| `src/litgraph/store.py` | `graph.json`: schema, validation, edits, the text outline the model reads |
| `src/litgraph/agent.py` | The tools, prompts and the Messages API tool loop, streamed as NDJSON events |
| `src/litgraph/claude_code.py` | The same agent run through Claude Code (Claude Agent SDK, in-process MCP tools) |
| `src/litgraph/literature.py` | Semantic Scholar, Crossref and arXiv lookups |
| `src/litgraph/server.py` | Flask: the page, graph API, proposals, chat stream |
| `src/litgraph/static/` | The website: canvas graph with its own force layout, node card, editor, chat |
| `examples/md_coarse_graining/` | The example workspace (`topics/<name>/graph.json` and `review.md` per topic) |
| `tests/` | Unit tests; the agent is tested against a local fake of the Messages API |

```bash
python -m unittest discover -s tests -t .
```

## License

GPL-3.0-or-later, like Wendao.
