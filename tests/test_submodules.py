"""
Submodules, offline. A repo with a local-path submodule must be checked out
and survive a save -> wipe -> update round-trip without losing information.
"""

import json
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


def test_update_with_explicit_submodule_list(gtp, workspace, upstreams):
	_, target = _add_parent(gtp, workspace, upstreams)
	# Pin an explicit submodule list in the manifest and re-materialize, taking
	# the `submodules` branch of update.
	manifest_path = workspace / '.git-third-party' / 'manifest.json'
	manifest = json.loads(manifest_path.read_text())
	manifest['repos']['third-party/parent']['submodules'] = ['sub']
	manifest_path.write_text(json.dumps(manifest))

	shutil.rmtree(target)
	assert gtp('update', 'third-party/parent').returncode == 0
	assert (target / 'sub' / 'child.txt').read_text() == 'child-v1\n'


def test_empty_submodule_list_still_checks_out(gtp, workspace, upstreams):
	_, target = _add_parent(gtp, workspace, upstreams)
	manifest_path = workspace / '.git-third-party' / 'manifest.json'
	manifest = json.loads(manifest_path.read_text())
	manifest['repos']['third-party/parent']['submodules'] = []
	manifest_path.write_text(json.dumps(manifest))

	shutil.rmtree(target)
	assert gtp('update', 'third-party/parent').returncode == 0
	# NOTE: documents current behavior — `submodules: []` does NOT skip checkout.
	# `git submodule update --init --recursive` runs unconditionally first, so
	# the submodule is materialized regardless of the list.
	assert (target / 'sub' / 'child.txt').read_text() == 'child-v1\n'


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
