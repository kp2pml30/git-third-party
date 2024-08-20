# Git third party

Small zero-dependency python utility that is an alternative to [git-submodules](https://git-scm.com/book/en/v2/Git-Tools-Submodules) and [git-subtree](https://manpages.debian.org/testing/git-man/git-subtree.1.en.html), that allows patching third-party code, storing commits in your tree

No need to fork, no need to store all code in your tree, store just your patches

**WARNING:** it is a raw prototype

## Usage
```bash
# adding third-party repository
git-third-party add third-party/RustPython https://github.com/RustPython/RustPython.git a13b99642b0bc13ca89d01768a7ddbec18fe8219
# ^ git-third-party add <relative path> <repository url> <commit hash>

# now you can modify it as a regular repository, commit your changes

# save patches to push to your origin
git-third-party save third-party/RustPython
# ^ git-third-party save <relative path>

# update
git-third-party update third-party/RustPython
# ^ git-third-party update <relative path>
```

## How it works?

It stores (at `/.gitthirdparty`) a configutation that describes all third party repositories and patches (at `/.gitthirdparty-patches/<local/repo/path>`). `save` command updates the patches, `update` command reapplies them

## Todo
- [ ] commit hooks
- [ ] updating all
- [ ] automated tests
