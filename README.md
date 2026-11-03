# Ontos

**A certification-first auto-ontology layer for agents.**

Ontos builds a semantic layer over your data — the entities, attributes,
relationships, and definitions that say what your data *means* — and serves it
to agents through deterministic queries. Every answer carries its provenance:
the certified terms it used, the query that ran, and where the data came from.

> **Status: founding.** This repository was created on 2026-11-02. The design
> brief is public ([docs/founding-brief.md](docs/founding-brief.md)); the
> first working slice is in build. Nothing here is a finished product yet —
> claims in this README describe the design, and each becomes a fact only
> when the slice that proves it ships.

## The pattern

1. **Generate** — read a database's metadata (schema, keys, comments, sample
   distributions) and draft an ontology: entities, attributes, relationships,
   candidate definitions. An LLM proposes; nothing is authoritative yet.
2. **Reconcile** — surface conflicting definitions of the same concept across
   sources and resolve them into one certified meaning.
3. **Certify** — a human reviews, edits, and certifies terms. Only certified
   terms are served. This is the step most implementations skip, and it is
   the whole point of this one.
4. **Serve** — agents ask questions through MCP, CLI, or API. Questions are
   answered by deterministic query generation against certified terms only —
   the serving path never calls a model — and every answer returns its
   provenance.
5. **Learn** — certified corrections and real usage fold back into the
   ontology, so the shared context improves with every question.

## How Ontos differs

- **Certification-first.** AI output becomes authoritative only through a
  validated, human-certified step — the same discipline as a command/event
  ledger: proposals are drafts until they are certified.
- **Event- and simulation-native.** Relational analytics is the easy case.
  Ontos is designed from the start for event logs, runs, and timelines —
  entities that unfold in time, not just tables that sit still.
- **Installable anywhere.** One store (Postgres), one package, no cluster
  required. If it can't be installed cleanly, it doesn't ship.
- **Model-agnostic.** Any OpenAI-compatible endpoint, hosted or local.
  No vendor gravity.
- **MCP-native.** Agents are the primary consumers; the CLI and API are
  the same surface for humans and scripts.

## First user

Ontos is built in the open by the TableX team and dogfooded there first:
organizational memory for exercise programs, context packs for AI
participants and guides, and grounded analysis over run history. It is a
standalone project — useful without TableX, better with it.

## Slice 1 (in build)

A fresh clone runs the whole loop end to end against a bundled sample
database: generate a draft ontology → certify terms at the CLI → ask
questions via CLI and MCP → get answers with their query and provenance.

## License

Apache License 2.0 — see [LICENSE](LICENSE).

Ontos is an independent implementation of the auto-ontology pattern. It is
not affiliated with NVIDIA; the pattern's best-known implementation,
[NVIDIA/auto-ontology](https://github.com/NVIDIA/auto-ontology), is credited
in the founding brief.
