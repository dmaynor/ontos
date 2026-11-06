# Ontos

**A certification-first auto-ontology layer for agents.**

Ontos builds a semantic layer over your data — the entities, attributes,
relationships, and definitions that say what your data *means* — and serves it
to agents through deterministic queries. Every answer carries its provenance:
the certified terms it used, the query that ran, and where the data came from.

The difference is certification. An LLM proposes term definitions; a human
certifies them; and the serving path is deterministic — it never calls a
model. A term that has not been certified is a draft, and drafts are never
served: a question that needs one is refused, by name, until a human
certifies it. Most ontology tooling skips that step. Ontos is the step.

> **Status: slices 1 and 2 shipped in 0.1.0.** The quickstart below runs the
> complete generate → certify → ask loop over the bundled sample, including
> the same question answered through an MCP server; the second section runs
> the same loop over APEX, the first real dataset. Anything beyond the scope
> listed below — free-form natural-language-to-SQL, a reconciliation UI,
> Postgres serving, and an HTTP API — remains design intent, not shipped fact.

## Quickstart

Requirements: Python 3.11 or newer (3.12 is tested in CI).

```sh
git clone https://github.com/dmaynor/ontos.git
cd ontos
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/ontos demo
```

The demo uses a fresh `demo-workspace/` directory and runs the whole loop:

1. create the bundled fictional exercise-platform database;
2. generate a draft ontology from its schema;
3. ask a question before certification and watch Ontos refuse it;
4. certify a named subset of terms;
5. answer count, recurrence, organization-rollup, and severity questions;
6. refuse a timeline question until the event terms are certified, then
   certify them and answer it; and
7. answer the recurrence question again through a real MCP client call.

You can also run the demo through the wrapper script after the install:

```sh
./scripts/demo.sh
```

## Run the loop manually

From the repository root, after the quickstart install:

```sh
.venv/bin/ontos sample --out sample.db
.venv/bin/ontos generate --source sample.db

# Drafts are never served. This ask is refused:
.venv/bin/ontos ask "which findings recurred across the last three runs?"

# Review drafts, then certify the terms these questions need.
.venv/bin/ontos certify --list
.venv/bin/ontos certify --as "Your Name" --accept \
  finding finding.title finding.severity finding.in_run \
  run run.in_exercise exercise exercise.in_organization organization \
  event event.occurred_at event.in_run

# Now the same questions answer, with SQL and certification provenance:
.venv/bin/ontos ask "which findings recurred across the last three runs?"
.venv/bin/ontos ask "show the timeline of run 3"
```

In a terminal, bare `ontos certify` starts an interactive accept / edit /
reject review. Scripted certification is available with `--accept`,
`--accept-all`, `--reject`, and `--edit`. Every certification records who
certified the term and when. Editing a certified term's definition returns it
to draft, because the changed text has not been certified.

The ontology store defaults to `ontology.db` in the current directory. Use
the global `--store` option or `ONTOS_STORE` to choose another path.

## Second dataset: APEX, the first real one

Slice 2 points the same loop at real data: the APEX escape-claim
benchmark record — 84 claim runs over 21 models, each run posing four
probes (front-door disclosure, encoded disclosure, role override,
boundary proposal) at one seed, under the frozen families
escape-probes-1.0 and escape-probes-1.1. The record ships in the repo
(`src/ontos/data/apex-runs.json`, a verbatim snapshot of the published
master record), so a fresh clone needs nothing outside the repo:

```sh
.venv/bin/ontos demo-apex
```

The demo builds the dataset, generates the draft ontology, refuses a
question, has a human certify terms — including the verdict vocabulary,
whose definitions ship with the dataset and state the claim semantics
exactly (a run *held* only if all four cells held; *falsified* if any
cell escaped; *incomplete* if no cell escaped but one produced no
artifact; *inconclusive*, a family-1.1 report outcome, when evidence
collection itself failed) — then answers:

- “which models hold at every seed tested?”
- “show every escape on the encoded probe” (any of the four probes)
- “show the full run history of qwen2.5:72b” (any recorded model) —
  also answered through the MCP server at the end of the demo.

Family, briefly: TableX sponsors APEX; APEX's record lives at
[llmdevsecops.ai](https://llmdevsecops.ai) and its arena is
[onlymodels.gg](https://onlymodels.gg). Ontos's PyPI distribution name
is `apex-ontos`, after that family; this release is GitHub-only.

## Questions slice 1 serves

Slice 1 deliberately serves a small set of parameterized templates bound to
certified terms. It does **not** claim general free-form NL-to-SQL — that is a
later slice.

- Counts: “how many findings / runs / exercises / organizations / events?”
- Recurrence: “which findings recurred across runs?” and “which findings
  recurred across the last three runs?”
- Per-organization rollups: “how many findings per organization?” (also runs
  and exercises)
- Severity breakdown: “findings by severity”
- Run timelines: “show the timeline of run 3” or “events in run 3”

If a question needs a term that is still a draft, rejected, or absent, Ontos
refuses it and names the missing terms. There is no bypass flag.

## MCP server

Agents are first-class consumers. Launch the stdio MCP server against the
same store:

```sh
.venv/bin/ontos --store ontology.db mcp-serve
```

It exposes:

- `ask` — the certified-term question service, including refusals and
  provenance;
- `get_term` — one term, labeled with its state (draft lookup is for review,
  not serving); and
- `list_terms` — terms, optionally filtered by state.

The demo proves this surface with the official MCP Python SDK client, not by
inspecting the server code.

## Optional generation inputs

### LLM-enriched draft definitions

`ontos generate` works with no model credentials: definitions are
deterministic templates derived from schema metadata and labeled
`origin=template`. If an OpenAI-compatible endpoint is configured, generate
may enrich those drafts and labels them `origin=llm`; they remain drafts until
certified.

```sh
export ONTOS_LLM_BASE_URL="https://example.invalid/v1"
export ONTOS_LLM_API_KEY="your-key"
export ONTOS_LLM_MODEL="your-model"
```

The `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` names are also
accepted. The serving path never calls a model, configured or not.

### Postgres metadata ingest

The demo source is a generated SQLite file for zero setup. Generate can also
read metadata from a Postgres connection string when a driver is installed:

```sh
.venv/bin/pip install "psycopg[binary]"
.venv/bin/ontos generate --source "postgresql://user:password@host/database"
```

Slice 1 executes served questions against SQLite sources. Postgres serving is
a later slice.

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
- **Installable anywhere.** One package and one local store for slice 1, no
  cluster required. If it can't be installed cleanly, it doesn't ship.
- **Model-agnostic.** Any OpenAI-compatible endpoint, hosted or local.
  No vendor gravity.
- **MCP-native.** Agents are the primary consumers; the CLI uses the same
  service paths.

## First user

Ontos is built in the open by the TableX team and dogfooded there first:
organizational memory for exercise programs, context packs for AI
participants and guides, and grounded analysis over run history. It is a
standalone project — useful without TableX, better with it.

## Scope

Shipped in 0.1.0:

- generated SQLite sample source with organizations, exercises, runs,
  events, and findings;
- deterministic ontology generation from SQLite metadata, with optional
  LLM-enriched draft definitions;
- CLI certification with certifier and timestamp provenance;
- deterministic CLI questions over certified terms only;
- a stdio MCP server exposing ask and term lookup;
- an end-to-end demo plus automated tests for the gate, answers, provenance,
  and MCP round trip;
- the APEX benchmark record as the first real dataset (slice 2), with a
  vocabulary-table mechanism for terms a schema cannot express, certified
  verdict definitions, three served question shapes, and its own demo; and
- source-shipped vocabulary: a source database may carry a `vocabulary`
  table of candidate terms, which generate drafts under the same gate.

Still design intent, not shipped: reconciliation workflows beyond manual
certification, general NL-to-SQL, Postgres question serving, an HTTP API, and
a web UI.

## Development

```sh
.venv/bin/pip install -e .[dev]
.venv/bin/python -m pytest
```

CI runs the test suite and the demo on pushes and pull requests.

## License

Apache License 2.0 — see [LICENSE](LICENSE).

Ontos is an independent implementation of the auto-ontology pattern. It is
not affiliated with NVIDIA; the pattern's best-known implementation,
[NVIDIA/auto-ontology](https://github.com/NVIDIA/auto-ontology), is credited
in the founding brief.
