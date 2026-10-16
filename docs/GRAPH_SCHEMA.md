# The literature-review graph schema

How a litgraph knowledge graph is organised, and the rules a new node or edge must satisfy. Every review,
whatever the field, uses the same five levels so that graphs stay comparable and the agent's additions stay
checkable. The schema is enforced by `litgraph check` and by the agent's `propose_graph_changes` tool: a
proposal that breaks a rule is returned to the model to fix, not written.

The research question the graph serves is the graph's title and description, not a node. Everything in the
graph is read against it.

## The five levels

| Level | Type | What it is | Test for "is this one?" |
|---|---|---|---|
| 1 | `family` | A method family: a way of attacking the problem, defined by what it learns or keeps, what it discards, and what it still has to compute | Two techniques in the same family make the same trade-off, even if their algorithms differ |
| 2 | `technique` | A named, reusable method or formalism that a paper can apply | You could implement it, or cite a standard reference for it, independent of any one paper |
| 3 | `paper` | One publication: evidence, not knowledge | It has authors, a year, a venue, and (usually) a DOI |
| 4 | `claim` | A falsifiable statement about methods, quantities or the field, with a status | A paper could support or contradict it; it can be wrong |
| 5 | `quantity` | A measurable or computable observable, with an operational definition | Two people with the same data compute the same number |

Families are few (five to ten per field) and stable. Techniques are many and shared across families only
rarely. Papers are the bulk of the graph. Claims and quantities are what the review is for: claims record
what is believed and on what evidence; quantities record what a method is validated against.

Open questions are claims with status `open`: "effective dynamics can be learned from short MD alone" is a
claim nobody has yet supported or refuted. Interpretations and judgements of the reviewer are claims with
status `hypothesis`. Neither is a separate type.

## Node fields

Every node: `id`, `type`, `label`, `summary` (one to three sentences a collaborator could check), optional
`aliases`, `tags`, `status` (`seed` from the initial review, `proposed` by the agent, `confirmed` by the
researcher) and `source` (`review`, `chat`, `search`, `manual`, `extract`).

Ids are `type:slug`: `family:generative-dynamics`, `technique:markov-state-model`,
`paper:nam2025-liflow`, `claim:cg-potential-does-not-fix-time-scales`, `quantity:msd`.

| Type | Required fields | Optional fields |
|---|---|---|
| `family` | `summary`: a plain explanation of the idea, for a reader who does not know the family | `keeps` (what it keeps or learns), `discards` (what it gives up), `computes` (what it still has to run); `relevance` (1 to 5, the reviewer's judgement against the research question) |
| `technique` | `summary` | `reference` (the standard citation or paper id) |
| `paper` | `year`, `authors`, `venue`; `learns` (what the model or method learns), `discards` (what it assumes away, removes or does not model), `validated_at` (list of validation levels, see below) | `doi`, `url`, `priority` (reading order) |
| `claim` | `claim_status`: `supported`, `contradicted`, `contested`, `hypothesis`, `open` | `scope` (where it holds) |
| `quantity` | `definition` (one-line operational definition: the object, the data, the computation), `level` (validation level) | `symbol`, `units` |

### Validation levels (for `paper.validated_at` and `quantity.level`)

| Level | What it checks |
|---|---|
| `structural` | Distributions of structure: radial distribution function, site occupancy, local coordination |
| `thermodynamic` | Free-energy differences, equilibrium populations |
| `kinetic` | Residence time, transition probability, hop rate |
| `transport` | Mean squared displacement, diffusivity, correlation factor |
| `mechanistic` | Migration pathways, cooperative events, environment-dependent transitions |

A paper's `validated_at` lists only the levels the paper itself reports evidence for. A model that is right
at every lower level can still be wrong at a higher one; the point of the field is to make that visible.

## Edge types

| Edge | From → to | Meaning |
|---|---|---|
| `contains` | family → technique, family → paper | Membership. A paper has exactly one primary family. |
| `uses` | paper → technique | The paper applies or builds on the technique |
| `extends` | paper → paper, technique → technique | Builds on, generalises, adds to |
| `contrasts` | paper ↔ paper, technique ↔ technique, family ↔ family | A stated difference; the label says which |
| `supports` | paper → claim | The paper gives evidence for the claim |
| `contradicts` | paper → claim | The paper gives evidence against the claim |
| `about` | claim → technique, family or quantity | What the claim is about |
| `validates` | paper → quantity | The paper reports the quantity as a check of its method |
| `relates` | any | A relation not covered above; always labelled |

Every `contrasts` and `relates` edge carries a short `label` in the papers' own terms ("adds many-body
memory", "equilibrium sampling vs dynamics"). `note` holds the one-sentence reason if the label is not
self-explanatory.

## Rules

Checked by `litgraph check` and on every proposal:

1. A paper has exactly one `contains` edge from a family, and at least one `uses` edge to a technique.
2. A paper has `year`, `authors`, `venue`, `learns`, `discards` and a non-empty `validated_at`. Metadata
   comes from a search result or from the researcher, never from memory.
3. A technique has at least one `contains` edge from a family and is used by at least one paper, or is the
   `reference` target of another technique.
4. A claim has `claim_status`, at least one `about` edge, and, unless its status is `open` or `hypothesis`,
   at least one `supports` or `contradicts` edge from a paper.
5. A quantity has a `definition` and a `level`.
6. No two nodes share a label (case-insensitive) or an alias.
7. A `contrasts` or `relates` edge has a `label`.

Rules 1 to 5 are hard: a proposal that violates them is not written. Rules 6 and 7 are reported.

## What the agent is told

The whole graph is in the agent's context as an outline, grouped by level. When it adds a paper it must
fill the three structured fields (`learns`, `discards`, `validated_at`) rather than describe them in prose,
and attach the paper to its family and techniques in the same proposal. When it finds a statement worth
keeping, it adds a claim with the papers that bear on it, not a sentence in a summary. When a paper reports
a check against an observable that is not yet a quantity node, it adds the quantity with its definition.

## Viewing

The website's level filter shows any subset of the five levels. When a level is hidden, nodes on either side
of a hidden node are joined by a dashed bridge edge, so hiding papers shows which techniques each family
contains and which claims and quantities each technique bears on, as derived from the papers.
