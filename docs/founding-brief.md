# Ontos — founding brief

*2026-11-02 · David Maynor (founder) · status: founding document; design
intent, not shipped fact.*

## Origin

On 2026-11-02 we reviewed NVIDIA's
[auto-ontology](https://github.com/NVIDIA/auto-ontology) (Apache-2.0) — a
framework that builds a semantic, graph-based reasoning layer over
enterprise data so agents can query it reliably. The verdict: **the pattern
is right, the product is not ours to adopt** — young, NVIDIA-stack gravity,
analytics-shaped, and a heavy footprint. The decision, same evening:

> "Let's steal the pattern and make a real auto ontology that we can open
> source."

Ontos is a clean-room implementation of that pattern. No NVIDIA code is
used; the pattern, and the differences below, are the inheritance.

## Why this exists

Agents can retrieve documents and query databases, but reliability is the
gate: an answer delivered faster is worth nothing if it is wrong, and it is
wrong in a specific way — the agent does not know what the data *means*,
which definition is the certified one, or where a number came from.

TableX hits this directly. The product's moat is organizational memory:
every finding tied to an owner, an action, and a retest; weaknesses
rehearsed against and measured over time. That memory is an ontology-shaped
problem — findings, weaknesses, exercises, runs, people, roles, injects,
observations — and today the agents that use it (guide pods, AI
participants, analysis) eat hand-built context packs. Ontos is that layer,
built properly, once, and in the open.

## The pattern (what we are stealing)

1. **Generate an ontology from metadata** rather than hand-modeling it.
2. **Reconcile definitions** across systems that disagree.
3. **Ground agents** in certified meaning, not raw schema.
4. **Validate queries against certified definitions and lineage; return
   provenance with every answer.**
5. **Expose through MCP, CLI, and API** so any agent harness can consume it.
6. **Learn**: certified corrections fold back in.

## Our differences (why ours is not a clone)

- **Certification is the core, not a feature.** In Ontos an LLM *proposes*
  terms, definitions, and mappings; a human *certifies* them; the serving
  path is deterministic and never calls a model. This mirrors the
  discipline we already run in TableX's canonical execution model: AI
  output becomes authoritative only through a validated command. An
  uncertified term is a draft and is labeled one everywhere it appears.
- **Event- and simulation-native.** NVIDIA's implementation is shaped for
  relational business analytics (text-to-SQL over warehouse tables). Our
  home data is event streams: runs, ordered events, timelines, projections.
  Ontos models entities that unfold in time as first-class citizens.
- **One package, one store.** Postgres (with pgvector only if a slice
  proves it needs it), installable as a single package on one box. No
  Kubernetes requirement, no five-service stack. The acceptance proof for
  any deployment claim is a clean install.
- **Model-agnostic.** Proposal and extraction steps take any
  OpenAI-compatible endpoint, hosted or local. No NIM, no vendor lock.
- **Open source from day one** (Apache-2.0), because the layer is more
  valuable as shared infrastructure — and because TableX's own history
  (podpatrol) says open components are the ecosystem's front door.

## Architecture sketch (slice 1)

- **Ingest**: connect to a Postgres database; read schema, keys, comments;
  sample distributions where safe.
- **Propose**: an LLM drafts entities, attributes, relationships, and
  definitions into a *draft* ontology stored alongside the catalog.
- **Certify**: CLI review flow — accept, edit, reject — producing the
  certified term set. Every term carries who certified it and when.
- **Serve**: an MCP server and a CLI that answer questions by generating
  queries from certified terms only, executing them read-only, and
  returning the answer **plus** the query, the terms used, and their
  certification provenance.
- **Storage**: Postgres. The ontology lives next to the catalog it
  describes.

## Slice 1 — the demo that defines "real"

A fresh clone, a bundled sample database (a small exercise-platform
schema: organizations, exercises, runs, events, findings), and one command
sequence:

1. `ontos generate` → a draft ontology appears.
2. `ontos certify` → a human certifies the core terms at the CLI.
3. `ontos ask "which findings recurred across the last three runs?"` →
   an answer, its deterministic query, and term-level provenance.
4. The same question answered through the MCP server by an external agent.

Acceptance is the fresh-clone run itself: if a stranger cannot run the
loop from the README, slice 1 is not done.

## Non-goals for v1

- No web UI. CLI and MCP are the surfaces; a UI is earned later.
- No multi-database federation. One source, done well, first.
- No hosted service. Ontos is software you install.
- No uncertified serving, ever. There is no flag for it.

## Open questions (founder's to settle as slices land)

- The name. *Ontos* is the working name; renaming is cheap before launch.
- First real dataset after the sample: the TableX platform schema or the
  SAT analysis journal.
- Whether Ontos joins the TableX ecosystem manifest as a family member or
  stays an adjacent open project (the podpatrol precedent says adjacent
  works).

## Fit

Ontos passes the family's two addition gates: it is consumed by the shared
base (TableX organizational memory, pod context, SAT grounding) rather
than requiring a new platform, and as an open-source project it is
land-and-expand for the ecosystem — the free layer that makes the paid
memory above it legible.
