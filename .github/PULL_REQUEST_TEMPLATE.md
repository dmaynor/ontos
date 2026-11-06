## What this changes

<!-- One short paragraph. Link the issue if there is one. -->

## The gate

<!-- Serving is certified-terms-only and there is no bypass. If this PR
touches ask / service / store / generate, state how the gate still holds,
and which negative control proves it. Write "does not touch the serving
path" if it doesn't. -->

## Verification

- [ ] Full test suite passes (`python -m pytest`)
- [ ] `ontos demo` completes (sample dataset)
- [ ] `ontos demo-apex` completes (if the APEX dataset or shared serving code changed)
- [ ] CHANGELOG.md updated under Unreleased (if user-visible)
- [ ] Docs do not claim anything the code does not do
