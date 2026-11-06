# Contributing to Ontos

Thanks for stopping by. Ontos is a certification-first auto-ontology
layer for agents: an LLM (or a deterministic template) *proposes* term
definitions, a human *certifies* them, and the serving path answers
questions deterministically from certified terms only — it never calls a
model, and an uncertified term is never served.

Contributions are welcome. Issues and pull requests are the front door;
there is no other gate.

## Run the demo

Requirements: Python 3.11 or newer (3.12 is tested in CI).

```sh
git clone https://github.com/dmaynor/ontos.git
cd ontos
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/ontos demo
```

The demo scrubs model credentials on purpose and runs the whole loop in a
fresh `demo-workspace/`: build the bundled sample database, generate a
draft ontology, watch the gate refuse a question, certify a named subset
of terms, answer questions with SQL and provenance, and answer the same
question again through a real MCP client call. It ends with
`DEMO COMPLETE`.

The APEX dataset demo (the first real dataset: the APEX escape-claim
benchmark record) runs the same loop over real data:

```sh
.venv/bin/ontos demo-apex
```

## Run the tests

```sh
.venv/bin/pip install -e .[dev]
.venv/bin/python -m pytest
```

CI runs the test suite and both demos on pushes and pull requests. A
change that breaks the demo or the gate has not landed until both are
green again.

## The one rule that is not negotiable

The certification gate is the product. There is no flag, environment
variable, or code path that serves an uncertified term, and a pull request
that adds one will not be merged. Tests include negative controls for
exactly this — an uncertified term must be refused, with the refusal
naming the term and its state. If your change touches `ask`, `service`,
or `store`, expect the review to start there.

## Propose a term definition change

Term definitions are data, not code: they live in the ontology store and
are drafted by `ontos generate`. To propose a better definition:

1. Open an issue using the feature-request template (or a plain issue)
   naming the term, the dataset it belongs to, the current definition,
   and your proposed text.
2. Say *why*: what question does the current definition answer wrong, or
   what does it leave ambiguous? Definitions are certified on their
   precision, not their length.
3. If the term is one of the APEX verdict terms (`verdict.held`,
   `verdict.falsified`, `verdict.incomplete`, `verdict.inconclusive`),
   the bar is higher: those definitions are the benchmark's claim
   semantics, and a change needs to state what happens to runs already
   recorded under the old definition.

Editing a certified term's definition returns it to draft in the store —
that behaviour is deliberate and is not a bug.

## Pull request expectations

- Keep the change scoped; unrelated refactors ride in their own PR.
- Add or update tests for behaviour changes. Gate changes need a negative
  control (a test that an uncertified term is refused).
- Run the demo (`ontos demo`, and `ontos demo-apex` if you touched the
  APEX dataset) and the full test suite before opening the PR, and say so
  in the PR description.
- Update `CHANGELOG.md` under `Unreleased` for anything a user would
  notice.
- Docs must not claim what the code does not do. Ontos marks design
  intent as design intent everywhere; keep that discipline.

## License

By contributing, you agree your contributions are licensed under the
Apache License 2.0 (see [LICENSE](LICENSE)).
