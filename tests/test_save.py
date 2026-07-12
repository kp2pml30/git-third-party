"""`save` subcommand: recording local changes as deterministic patches."""

from fixtures import commit_files, git


def _add_simple(gtp, upstreams):
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	return simple


def _patches_dir(workspace):
	return workspace / '.git-third-party' / 'patches' / 'third-party' / 'simple'


def test_save_without_changes_records_zero_patches(
	gtp, workspace, upstreams, read_config
):
	_add_simple(gtp, upstreams)
	res = gtp('save', 'third-party/simple')
	assert res.returncode == 0, res.stderr
	assert read_config()['repos']['third-party/simple']['patches'] == 0
	pdir = _patches_dir(workspace)
	assert not pdir.exists() or list(pdir.iterdir()) == []


def test_save_records_one_patch_per_commit(
	gtp, workspace, base_env, upstreams, read_config
):
	_add_simple(gtp, upstreams)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'lib.txt': 'beta\n'}, 'feat: change lib')
	commit_files(target, base_env, {'new.txt': 'new\n'}, 'feat: add new file')

	res = gtp('save', 'third-party/simple')
	assert res.returncode == 0, res.stderr
	assert read_config()['repos']['third-party/simple']['patches'] == 2
	pdir = _patches_dir(workspace)
	assert {p.name for p in pdir.iterdir()} == {'1', '2'}


def test_save_strips_commit_hash_and_git_signature(gtp, workspace, base_env, upstreams):
	_add_simple(gtp, upstreams)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'lib.txt': 'beta\n'}, 'feat: change lib')
	assert gtp('save', 'third-party/simple').returncode == 0

	patch = (_patches_dir(workspace) / '1').read_text()
	# Commit hash on the `From` line is zeroed out...
	assert patch.startswith('From 0000000000000000000000000000000000000000 ')
	# ...and the trailing `-- \n<git version>` signature is removed.
	assert '\n-- \n' not in patch


def test_save_is_byte_for_byte_reproducible(gtp, workspace, base_env, upstreams):
	_add_simple(gtp, upstreams)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'lib.txt': 'beta\n'}, 'feat: change lib')

	assert gtp('save', 'third-party/simple').returncode == 0
	first = (_patches_dir(workspace) / '1').read_bytes()
	# Saving again over the same HEAD must reproduce identical bytes.
	assert gtp('save', 'third-party/simple').returncode == 0
	second = (_patches_dir(workspace) / '1').read_bytes()
	assert first == second


def test_save_prunes_stale_patch_files(
	gtp, workspace, base_env, upstreams, read_config
):
	_add_simple(gtp, upstreams)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'a.txt': '1\n'}, 'feat: a')
	commit_files(target, base_env, {'b.txt': '2\n'}, 'feat: b')
	commit_files(target, base_env, {'c.txt': '3\n'}, 'feat: c')
	assert gtp('save', 'third-party/simple').returncode == 0
	assert {p.name for p in _patches_dir(workspace).iterdir()} == {'1', '2', '3'}

	# Drop back to a single extra commit and re-save.
	git(['reset', '--hard', 'HEAD~2'], target, base_env)
	assert gtp('save', 'third-party/simple').returncode == 0
	assert read_config()['repos']['third-party/simple']['patches'] == 1
	assert {p.name for p in _patches_dir(workspace).iterdir()} == {'1'}


def test_save_refuses_dirty_worktree(gtp, workspace, base_env, upstreams, read_config):
	_add_simple(gtp, upstreams)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'lib.txt': 'beta\n'}, 'feat: change lib')
	assert gtp('save', 'third-party/simple').returncode == 0

	# An uncommitted edit must block save so no work is silently dropped.
	(target / 'lib.txt').write_text('uncommitted\n')
	res = gtp('save', 'third-party/simple')
	assert res.returncode == 1
	assert 'dirty' in res.stderr
	# The recorded patch count is unchanged.
	assert read_config()['repos']['third-party/simple']['patches'] == 1


def test_save_all_records_every_repo(gtp, workspace, base_env, upstreams, read_config):
	simple = upstreams['simple']
	for name in ['third-party/a', 'third-party/b']:
		assert gtp('add', name, str(simple['path']), simple['c1']).returncode == 0
		commit_files(
			workspace.joinpath(*name.split('/')), base_env, {'x.txt': name + '\n'}, 'feat: x'
		)
	res = gtp('save', '--all')
	assert res.returncode == 0, res.stderr
	cfg = read_config()
	assert cfg['repos']['third-party/a']['patches'] == 1
	assert cfg['repos']['third-party/b']['patches'] == 1
