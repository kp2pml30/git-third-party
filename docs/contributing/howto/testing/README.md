# Testing

The suite lives under [`tests/`](../../../../tests) and is written with pytest.
It is fully **offline**: [`tests/fixtures.py`](../../../../tests/fixtures.py)
generates local git repositories (served over filesystem paths, with
`uploadpack.allowAnySHA1InWant`) so nothing touches the network.

Run it from the repo root:

```bash
nix develop -c pytest -q tests
```

Or sandboxed, exactly as CI does:

```bash
nix build .#checks.<system>.tests   # e.g. .#checks.x86_64-linux.tests
```

Materialize the fixtures for manual inspection:

```bash
python tests/fixtures.py /tmp/gtp-fixtures
```

## Coverage

The tool is imported and driven **in-process** (see `run_tool` in
`fixtures.py`), so `pytest-cov` measures it directly — no subprocess-coverage
plumbing needed. Branch coverage:

```bash
nix develop -c pytest --cov --cov-branch --cov-report=term-missing tests
```

`--cov-branch` is the branch-coverage flag; the bare `--cov` plus the `include`
filter in [`.coveragerc`](../../../../.coveragerc) scopes the report to the
`git-third-party` script. Add `--cov-report=html` for an annotated tree.

## What is covered

- `test_add.py` — registering a repo, checkout at the pinned commit, and every
  rejection path (bad chars, outside the tree, non-ignored dir, duplicate).
- `test_save.py` — patch recording, count bookkeeping, stale-patch pruning,
  metadata stripping, dirty-worktree refusal.
- `test_update.py` — the save → wipe → update round-trip proves **no
  information is lost**: the working tree and the content-addressed git tree
  object come back identical.
- `test_submodules.py` — a repo with a local-path submodule is checked out and
  survives the round-trip, offline.
- `test_determinism.py` — save → update → save under different author/committer
  identities yields byte-for-byte identical patches.
