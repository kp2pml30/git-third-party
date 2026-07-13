"""`update` must not silently drop local commits that were never `save`d.

Before detaching to the base commit, the guard reconstructs the saved patch
series by patch-id, finds the longest matching prefix against the current
history, and refuses when the checkout is *ahead* — i.e. carries commits beyond
that prefix that no patch file records.
"""

from fixtures import commit_files, git


def _add_and_save_one(gtp, workspace, base_env, upstreams):
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'lib.txt': 'patched\n'}, 'feat: patch lib')
	assert gtp('save', 'third-party/simple').returncode == 0
	return target


def test_update_refuses_unsaved_commit(gtp, workspace, base_env, upstreams):
	target = _add_and_save_one(gtp, workspace, base_env, upstreams)
	# A second commit that was never saved. Update must refuse rather than detach
	# it into the reflog.
	commit_files(target, base_env, {'lib.txt': 'more work\n'}, 'feat: unsaved work')

	res = gtp('update', 'third-party/simple')
	assert res.returncode == 1
	assert 'ahead' in res.stderr
	# The unsaved commit is still on HEAD, its content intact.
	subjects = git(['log', '--format=%s'], target, base_env).stdout.splitlines()
	assert subjects[0] == 'feat: unsaved work'
	assert (target / 'lib.txt').read_text() == 'more work\n'


def test_update_allows_exactly_saved_history(gtp, workspace, base_env, upstreams):
	target = _add_and_save_one(gtp, workspace, base_env, upstreams)
	# HEAD == base + the one saved patch: no unsaved work, so update is a safe
	# reapply and must be allowed.
	res = gtp('update', 'third-party/simple')
	assert res.returncode == 0, res.stderr
	assert (target / 'lib.txt').read_text() == 'patched\n'


def test_update_allows_extra_saved_patches(gtp, workspace, base_env, upstreams):
	"""Fewer local commits than saved patches is *behind*, not ahead: allowed."""
	target = _add_and_save_one(gtp, workspace, base_env, upstreams)
	commit_files(target, base_env, {'b.txt': 'b\n'}, 'feat: second')
	assert gtp('save', 'third-party/simple').returncode == 0  # now 2 patches saved

	# Drop the second commit locally (HEAD keeps only the first saved patch).
	git(['reset', '--hard', 'HEAD~1'], target, base_env)
	res = gtp('update', 'third-party/simple')
	assert res.returncode == 0, res.stderr
	# Both patches come back.
	subjects = git(['log', '--format=%s'], target, base_env).stdout.splitlines()
	assert subjects[:2] == ['feat: second', 'feat: patch lib']
