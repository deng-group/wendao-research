# Instructions for the research agent

## The research

I study ion transport in solid-state electrolytes with machine-learning interatomic potentials (MLIP) and
molecular dynamics. The question behind this graph: can we learn an efficient representation or dynamics
model from atomistic simulations that predicts accurately at larger spatial and temporal scales? The target
quantities are diffusivity, ionic conductivity, hop rates, migration pathways and correlated migration.

The seed of the graph is a literature review (topics/md-coarse-graining/review.md) written in the five-level
schema (docs/GRAPH_SCHEMA.md): seven method families A to G, techniques, papers, claims, quantities. Keep
the families when adding papers: a paper is `contains`-linked from exactly one family and `uses` the
techniques it applies. A paper's `learns`, `discards` and `validated_at` fields are what I compare across
families; fill them from the paper, not from its abstract's claims.

## Terminology

- Use standard scientific terminology only; do not coin shorthand or metaphors (geometry optimization,
  collective variable, Markov state model).
- Define a quantity the first time it appears (formula or a one-line operational definition) and keep the
  same name afterwards. Say what an offset, width or neighbour is relative to.
- Separate a measured quantity, a hypothesis and an interpretation; label interpretations as such.
- Separate what a paper claims from what its evidence shows.

## What belongs in the graph

- A paper: only with title, authors, year and venue from a search result or from me; `validated_at` lists
  only the levels the paper reports evidence for (structural, thermodynamic, kinetic, transport, mechanistic).
- A technique: a method a paper applies that you could implement or cite independently of that paper.
- A claim: a falsifiable statement about methods or quantities, with the papers that bear on it. My
  judgements are claims with status hypothesis; unanswered questions are claims with status open.
- A quantity: an observable a paper validates against, with a one-line operational definition (object,
  data, computation) and its level; MSD, diffusivity, hop rate, migration pathway are the ones I care about.
- An edge: a relation the paper itself states, or that I confirm; `contrasts` and `relates` carry a label in
  the paper's own terms.
- Do not add application-specific papers (one material's conductivity) unless they test a method family.

## Answers

Always answer in English, even if I write in Chinese. Lead with the answer; short paragraphs; lists for parallel items. When
you use a node, cite its id in square brackets so the interface can link it. Say what the graph does not
cover instead of guessing.
