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
cp .env.example .env          # put your ANTHROPIC_API_KEY in .env
# either write graph.json by hand / with the editor in the website,
# or drop a review into notes/ and let the model extract a first graph:
litgraph extract notes/review.md
litgraph serve                # http://127.0.0.1:5058/
```

Without a key everything except the chat works. `litgraph check` validates the graph and tests the model.

### The example

`examples/md_coarse_graining/` is a built workspace: a review of molecular-dynamics coarse-graining and
acceleration methods (seven method families, about twenty papers) read against Li-ion transport in
solid-state electrolytes. The graph was written from the review by hand (51 nodes, 107 edges).

```bash
cd examples/md_coarse_graining
cp .env.example .env          # add ANTHROPIC_API_KEY
litgraph serve
```

## How the agent works

Every answer is one request to the Anthropic Messages API with:

- a system prompt: the agent's role, your `AGENTS.md` (your research, terminology rules, what belongs in the
  graph), and the whole graph as compact text (cached with prompt caching);
- the recent conversation (kept in the browser, session only) and the node you selected;
- tools: `find_nodes`, `read_node`, `search_literature` (Semantic Scholar → Crossref → arXiv, no key needed),
  `propose_graph_changes`, and Anthropic's server-side `web_search` and `web_fetch`.

`propose_graph_changes` validates the change on a copy first (unknown ids, bad types) so the model can fix
it, then writes it to `graph.json` with status `proposed`. Every write keeps a `graph.backup.json`. With
`auto_apply = true` in `litgraph.toml` additions go in as confirmed.

The model is set under `[model]` in `litgraph.toml` (default `claude-opus-5-5`; `effort` controls how hard
it thinks). The key is read from `.env` or the environment (`ANTHROPIC_API_KEY`).

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
| `src/litgraph/agent.py` | The tool loop with the Anthropic SDK, streamed as NDJSON events |
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
