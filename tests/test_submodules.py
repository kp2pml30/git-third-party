"""Submodules, offline. A repo with a local-path submodule must be checked out
and survive a save -> wipe -> update round-trip without losing information."""

import shutil

from fixtures import commit_files, git, snapshot_worktree, tree_sha


def _add_parent(gtp, workspace, upstreams):
	parent = upstreams['parent']
	res = gtp('add', 'third-party/parent', str(parent['path']), parent['commit'])
	assert res.returncode == 0, res.stderr
	return parent, workspace / 'third-party' / 'parent'


def test_add_checks_out_submodule_offline(gtp, workspace, upstreams):
	_, target = _add_parent(gtp, workspace, upstreams)
	# Submodule content is materialized entirely from local repos.
	assert (target / 'parent.txt').read_text() == 'parent-v1\n'
	assert (target / 'sub' / 'child.txt').read_text() == 'child-v1\n'


def test_submodule_survives_roundtrip(gtp, workspace, base_env, upstreams):
	_, target = _add_parent(gtp, workspace, upstreams)
	assert gtp('save', 'third-party/parent').returncode == 0

	before_files = snapshot_worktree(target)
	before_tree = tree_sha(target, base_env)
	# The snapshot must actually include the submodule content we care about.
	assert 'sub/child.txt' in before_files

	shutil.rmtree(target)
	assert gtp('update', 'third-party/parent').returncode == 0

	# Superproject tree (including the submodule gitlink) and every file on disk
	# come back identical.
	assert snapshot_worktree(target) == before_files
	assert tree_sha(target, base_env) == before_tree


def test_patch_alongside_submodule_roundtrip(gtp, workspace, base_env, upstreams):
	_, target = _add_parent(gtp, workspace, upstreams)
	# A local patch in the superproject that does not touch the submodule.
	commit_files(target, base_env, {'added.txt': 'local\n'}, 'feat: add local file')
	assert gtp('save', 'third-party/parent').returncode == 0

	before_files = snapshot_worktree(target)
	before_tree = tree_sha(target, base_env)

	shutil.rmtree(target)
	assert gtp('update', 'third-party/parent').returncode == 0

	assert snapshot_worktree(target) == before_files
	assert tree_sha(target, base_env) == before_tree
	# Patch applied and submodule still intact.
	assert (target / 'added.txt').read_text() == 'local\n'
	assert (target / 'sub' / 'child.txt').read_text() == 'child-v1\n'
	subjects = git(['log', '--format=%s'], target, base_env).stdout.splitlines()
	assert subjects[0] == 'feat: add local file'
