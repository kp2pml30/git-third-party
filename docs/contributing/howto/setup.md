# Setup

First-time clone. All commands run from the repo root.

## Dev shell

The dev shell provides `python3` and installs the git hooks into
`.git/hooks/`:

```bash
nix develop
```

With [direnv](https://direnv.net/):

```bash
direnv allow   # uses .envrc -> `use flake .#`
```

## Run the tool

`git-third-party` is a single zero-dependency Python script — run it directly:

```bash
./git-third-party help
```

Or build and run the packaged binary (wraps `git` onto `PATH`):

```bash
nix run . -- help
```

## Formatting and checks

```bash
nix fmt              # format everything (nixfmt, ruff-format, …)
nix flake check      # run all hooks sandboxed
```
