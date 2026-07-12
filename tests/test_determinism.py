"""Patches must be deterministic: the identity of whoever re-applies and
re-saves them must not change a single byte of the stored patches."""

from fixtures import commit_files, run_tool


def _patches(pdir):
	return {p.name: p.read_bytes() for p in pdir.iterdir()}


def test_save_update_save_is_identity_independent(
	workspace, base_env, alt_env, upstreams
):
	simple = upstreams['simple']
	assert (
		run_tool(
			workspace,
			['add', 'third-party/simple', str(simple['path']), simple['c1']],
			env=base_env,
		).returncode
		== 0
	)
	target = workspace / 'third-party' / 'simple'
	# Local history authored under identity A.
	commit_files(target, base_env, {'lib.txt': 'patched\n'}, 'feat: patch lib')
	commit_files(target, base_env, {'extra.txt': 'more\n'}, 'feat: add extra')

	pdir = workspace / '.git-third-party' / 'patches' / 'third-party' / 'simple'

	# save as identity A
	assert (
		run_tool(workspace, ['save', 'third-party/simple'], env=base_env).returncode == 0
	)
	first = _patches(pdir)
	assert set(first) == {'1', '2'}

	# re-apply and re-save as a *different* identity B (different author name,
	# email, committer, and both author/committer dates).
	assert (
		run_tool(workspace, ['update', 'third-party/simple'], env=alt_env).returncode == 0
	)
	assert (
		run_tool(workspace, ['save', 'third-party/simple'], env=alt_env).returncode == 0
	)
	second = _patches(pdir)

	# Not one byte changed: `git am` restores the original author from the patch
	# and `format-patch` never emits the committer, so patches are stable.
	assert first == second


def test_repeated_save_update_cycles_are_stable(
	workspace, base_env, alt_env, upstreams
):
	simple = upstreams['simple']
	assert (
		run_tool(
			workspace,
			['add', 'third-party/simple', str(simple['path']), simple['c1']],
			env=base_env,
		).returncode
		== 0
	)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'lib.txt': 'patched\n'}, 'feat: patch lib')

	pdir = workspace / '.git-third-party' / 'patches' / 'third-party' / 'simple'
	assert (
		run_tool(workspace, ['save', 'third-party/simple'], env=base_env).returncode == 0
	)
	reference = _patches(pdir)

	# Several update/save round-trips, alternating identities, all converge to
	# the exact same patch bytes.
	for env in (alt_env, base_env, alt_env):
		assert (
			run_tool(workspace, ['update', 'third-party/simple'], env=env).returncode == 0
		)
		assert run_tool(workspace, ['save', 'third-party/simple'], env=env).returncode == 0
		assert _patches(pdir) == reference
