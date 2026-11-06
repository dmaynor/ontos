# Changelog

All notable changes to Ontos are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-05

The first release: slice 1 (the sample demo loop) plus slice 2, the APEX
benchmark record as the first real dataset.

### Added

- **Slice 1 — the demo loop.** `ontos sample` builds a bundled fictional
  exercise-platform database (organizations, exercises, runs, events,
  findings); `ontos generate` drafts an ontology from its schema with no
  model credentials (deterministic template definitions; optional
  LLM-enriched drafts when an OpenAI-compatible endpoint is configured,
  labeled `origin=llm`); `ontos certify` reviews drafts interactively or
  scripted, recording who certified each term and when; `ontos ask`
  answers a small set of deterministic question shapes (counts,
  recurrence, per-organization rollups, severity breakdown, run
  timelines) from certified terms only, returning the SQL and term-level
  certification provenance with every answer.
- **The certification gate.** Draft, rejected, or absent terms are never
  served. A question that needs an uncertified term is refused, and the
  refusal names the term and its state. There is no bypass flag. Editing
  a certified term's definition returns it to draft.
- **MCP server.** `ontos mcp-serve` exposes `ask`, `get_term`, and
  `list_terms` over stdio through the official MCP Python SDK — the same
  service paths, gate, and provenance as the CLI.
- **Postgres metadata ingest** for `generate` (with an installed driver);
  serving remains SQLite in this release.
- **Slice 2 — APEX as the first real dataset.** `ontos apex-sample`
  builds a database from the APEX escape-claim benchmark record bundled
  in the repo (84 claim runs, 336 probe cells across 21 models and two
  probe families, recorded 2026-11-03 to 2026-11-05); `ontos demo-apex`
  runs the full generate → certify → ask loop over it. The verdict
  vocabulary carries precise certified definitions (`verdict.held`,
  `verdict.falsified`, `verdict.incomplete`, `verdict.inconclusive`),
  and three questions are served deterministically: which models hold at
  every seed tested, every escape on a named probe, and one named
  model's full run history across families — the last also answered
  through the MCP server in the demo.
- Contributor surface: `CONTRIBUTING.md`, issue and pull request
  templates.
- Distribution name: the project's PyPI distribution name is
  `apex-ontos` (the APEX family brand), while the project, repository,
  import package, and CLI command remain Ontos / `ontos`. This release
  is GitHub-only; no PyPI upload has been made.
- Automated tests covering generation, the certification gate (including
  negative controls), answers and provenance, the MCP round trip, and the
  APEX dataset path.

[Unreleased]: https://github.com/dmaynor/ontos/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/dmaynor/ontos/releases/tag/v0.1.0
