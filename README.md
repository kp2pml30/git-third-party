# Git third party

Patch third-party libraries without forking them.

[![standard-readme compliant](https://img.shields.io/badge/readme%20style-standard-brightgreen.svg)](https://github.com/RichardLitt/standard-readme)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

## Background

`git-third-party` is a small zero-dependency utility that is an alternative to
[git-submodules](https://git-scm.com/book/en/v2/Git-Tools-Submodules) and
[git-subtree](https://manpages.debian.org/testing/git-man/git-subtree.1.en.html).
It stores only the delta (your changes) inside your tree, not the full vendored
source.

It is not oriented for highly concurrent modification of third-party tools by
multiple users.

## Install

With Nix (flakes):

```bash
nix profile install github:kp2pml30/git-third-party
```

Or just drop the single script on your `PATH` — it needs only `python3` and
`git`:

```bash
curl -o ~/.local/bin/git-third-party https://raw.githubusercontent.com/kp2pml30/git-third-party/main/git-third-party
chmod +x ~/.local/bin/git-third-party
```

## Usage

```bash
# add a third-party repository
git-third-party add third-party/RustPython https://github.com/RustPython/RustPython.git a13b99642b0bc13ca89d01768a7ddbec18fe8219
# ^ git-third-party add <relative path> <repository url> <commit hash>

# now modify it as a regular repository, and commit your changes

# save patches to push to your origin
git-third-party save third-party/RustPython
# ^ git-third-party save <relative path>

# reapply patches (e.g. on a fresh checkout)
git-third-party update third-party/RustPython
# ^ git-third-party update <relative path>
```

Without installing, you can run it straight from the flake:

```bash
nix run github:kp2pml30/git-third-party -- add third-party/RustPython <url> <commit>
```

### How it works

It stores a configuration under `/.git-third-party/` that describes all
third-party repositories and their patches. `save` updates the patches, `update`
reapplies them.

The `.git-third-party` directory must be tracked by git, while the third-party
working trees themselves should not be.

Best effort is made to keep patches deterministic and to strip metadata from
them, including:

- git version
- commit hash (which depends on the committer)
- …

## Contributing

See [docs/contributing/](docs/contributing/README.md).

## License

GPL-3.0 (C) 2024-2026 Kira Prokopenko
