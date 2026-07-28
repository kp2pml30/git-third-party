"""
`update` subcommand and the save -> wipe -> update round-trip.

These tests are the precise witnesses that the tool never loses information:
after a round-trip the working tree is byte-for-byte identical and the
content-addressed git tree object is the same.
"""

import shutil

from fixtures import commit_files, git, snapshot_worktree, tree_sha


def _add_with_local_history(gtp, workspace, base_env, upstreams):
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	target = workspace / 'third-party' / 'simple'
	# A couple of local commits, including a modification and an addition, so
	# the round-trip has real content to preserve.
	commit_files(target, base_env, {'lib.txt': 'patched\n'}, 'feat: patch lib')
	commit_files(target, base_env, {'extra/deep.txt': 'deep\n'}, 'feat: add nested file')
	return simple, target


def test_update_restores_identical_worktree_after_wipe(
	gtp, workspace, base_env, upstreams
):
	_, target = _add_with_local_history(gtp, workspace, base_env, upstreams)
	assert gtp('save', 'third-party/simple').returncode == 0

	before_files = snapshot_worktree(target)
	before_tree = tree_sha(target, base_env)

	shutil.rmtree(target)
	res = gtp('update', 'third-party/simple')
	assert res.returncode == 0, res.stderr

	# No information lost: same files, same content, same tree object.
	assert snapshot_worktree(target) == before_files
	assert tree_sha(target, base_env) == before_tree


def test_update_reapplies_patches_as_commits(gtp, workspace, base_env, upstreams):
	simple, target = _add_with_local_history(gtp, workspace, base_env, upstreams)
	assert gtp('save', 'third-party/simple').returncode == 0
	shutil.rmtree(target)
	assert gtp('update', 'third-party/simple').returncode == 0

	subjects = git(['log', '--format=%s'], target, base_env).stdout.splitlines()
	# Both patches land, most recent first, on top of the pinned base commit.
	assert subjects[:2] == ['feat: add nested file', 'feat: patch lib']
	# The base commit is still the pinned upstream commit.
	base_sha = git(
		['rev-list', '--max-parents=0', 'HEAD'], target, base_env
	).stdout.strip()
	assert base_sha == simple['c1']


def test_update_all_restores_every_repo(gtp, workspace, base_env, upstreams):
	simple = upstreams['simple']
	names = ['third-party/a', 'third-party/b']
	expected = {}
	for name in names:
		assert gtp('add', name, str(simple['path']), simple['c1']).returncode == 0
		tgt = workspace.joinpath(*name.split('/'))
		commit_files(tgt, base_env, {'p.txt': name + '\n'}, 'feat: p')
		assert gtp('save', name).returncode == 0
		expected[name] = snapshot_worktree(tgt)

	for name in names:
		shutil.rmtree(workspace.joinpath(*name.split('/')))
	res = gtp('update', '--all')
	assert res.returncode == 0, res.stderr

	for name in names:
		assert snapshot_worktree(workspace.joinpath(*name.split('/'))) == expected[name]


def test_update_refuses_dirty_worktree(gtp, workspace, base_env, upstreams):
	_, target = _add_with_local_history(gtp, workspace, base_env, upstreams)
	assert gtp('save', 'third-party/simple').returncode == 0

	(target / 'lib.txt').write_text('local uncommitted work\n')
	res = gtp('update', 'third-party/simple')
	# Update must refuse rather than clobber uncommitted local work.
	assert res.returncode == 1
	assert 'dirty' in res.stderr
	assert (target / 'lib.txt').read_text() == 'local uncommitted work\n'


def test_update_is_idempotent(gtp, workspace, base_env, upstreams):
	_, target = _add_with_local_history(gtp, workspace, base_env, upstreams)
	assert gtp('save', 'third-party/simple').returncode == 0

	assert gtp('update', 'third-party/simple').returncode == 0
	first = snapshot_worktree(target)
	first_tree = tree_sha(target, base_env)
	assert gtp('update', 'third-party/simple').returncode == 0
	assert snapshot_worktree(target) == first
	assert tree_sha(target, base_env) == first_tree
