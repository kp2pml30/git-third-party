"""
`save` subcommand: recording local changes as deterministic patches.
"""

from fixtures import commit_files, git, run_tool


def _add_simple(gtp, upstreams):
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	return simple


def _patches_dir(workspace):
	return workspace / '.git-third-party' / 'patches' / 'third-party' / 'simple'


def _only_patch(workspace, read_manifest):
	"""
	The single recorded patch file of `third-party/simple`.
	"""
	(name,) = read_manifest()['repos']['third-party/simple']['patches']
	return _patches_dir(workspace) / name


def test_save_without_changes_records_zero_patches(
	gtp, workspace, upstreams, read_manifest
):
	_add_simple(gtp, upstreams)
	res = gtp('save', 'third-party/simple')
	assert res.returncode == 0, res.stderr
	assert read_manifest()['repos']['third-party/simple']['patches'] == []
	pdir = _patches_dir(workspace)
	assert not pdir.exists() or list(pdir.iterdir()) == []


def test_save_records_one_patch_per_commit(
	gtp, workspace, base_env, upstreams, read_manifest
):
	_add_simple(gtp, upstreams)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'lib.txt': 'beta\n'}, 'feat: change lib')
	commit_files(target, base_env, {'new.txt': 'new\n'}, 'feat: add new file')

	res = gtp('save', 'third-party/simple')
	assert res.returncode == 0, res.stderr
	names = read_manifest()['repos']['third-party/simple']['patches']
	assert len(names) == 2
	# The manifest lists the series in order; the directory holds exactly it.
	pdir = _patches_dir(workspace)
	assert {p.name for p in pdir.iterdir()} == set(names)


def test_save_strips_commit_hash_and_git_signature(
	gtp, workspace, base_env, upstreams, read_manifest
):
	_add_simple(gtp, upstreams)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'lib.txt': 'beta\n'}, 'feat: change lib')
	assert gtp('save', 'third-party/simple').returncode == 0

	patch = _only_patch(workspace, read_manifest).read_text()
	# Commit hash on the `From` line is zeroed out...
	assert patch.startswith('From 0000000000000000000000000000000000000000 ')
	# ...and the trailing `-- \n<git version>` signature is removed.
	assert '\n-- \n' not in patch


def test_save_is_byte_for_byte_reproducible(
	gtp, workspace, base_env, upstreams, read_manifest
):
	_add_simple(gtp, upstreams)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'lib.txt': 'beta\n'}, 'feat: change lib')

	assert gtp('save', 'third-party/simple').returncode == 0
	first = _only_patch(workspace, read_manifest).read_bytes()
	# Saving again over the same HEAD must reproduce identical bytes -- and,
	# since the name is the content digest, the same file name too.
	assert gtp('save', 'third-party/simple').returncode == 0
	second = _only_patch(workspace, read_manifest).read_bytes()
	assert first == second


def test_save_prunes_stale_patch_files(
	gtp, workspace, base_env, upstreams, read_manifest
):
	_add_simple(gtp, upstreams)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'a.txt': '1\n'}, 'feat: a')
	commit_files(target, base_env, {'b.txt': '2\n'}, 'feat: b')
	commit_files(target, base_env, {'c.txt': '3\n'}, 'feat: c')
	assert gtp('save', 'third-party/simple').returncode == 0
	first = read_manifest()['repos']['third-party/simple']['patches']
	assert len(first) == 3
	assert {p.name for p in _patches_dir(workspace).iterdir()} == set(first)

	# Drop back to a single extra commit and re-save.
	git(['reset', '--hard', 'HEAD~2'], target, base_env)
	assert gtp('save', 'third-party/simple').returncode == 0
	remaining = read_manifest()['repos']['third-party/simple']['patches']
	# The surviving commit keeps its name; the two dropped files are gone.
	assert remaining == first[:1]
	assert {p.name for p in _patches_dir(workspace).iterdir()} == set(remaining)


def test_save_refuses_dirty_worktree(
	gtp, workspace, base_env, upstreams, read_manifest
):
	_add_simple(gtp, upstreams)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'lib.txt': 'beta\n'}, 'feat: change lib')
	assert gtp('save', 'third-party/simple').returncode == 0

	# An uncommitted edit must block save so no work is silently dropped.
	(target / 'lib.txt').write_text('uncommitted\n')
	res = gtp('save', 'third-party/simple')
	assert res.returncode == 1
	assert 'dirty' in res.stderr
	# The recorded series is unchanged.
	assert len(read_manifest()['repos']['third-party/simple']['patches']) == 1


def test_save_all_records_every_repo(
	gtp, workspace, base_env, upstreams, read_manifest
):
	simple = upstreams['simple']
	for name in ['third-party/a', 'third-party/b']:
		assert gtp('add', name, str(simple['path']), simple['c1']).returncode == 0
		commit_files(
			workspace.joinpath(*name.split('/')), base_env, {'x.txt': name + '\n'}, 'feat: x'
		)
	res = gtp('save', '--all')
	assert res.returncode == 0, res.stderr
	manifest = read_manifest()
	assert len(manifest['repos']['third-party/a']['patches']) == 1
	assert len(manifest['repos']['third-party/b']['patches']) == 1


# Every `format.*` key that changes what `git format-patch` emits: a cover
# letter is a whole extra file, the rest alter the bytes -- and `format.from`
# writes the local committer into the patch, which is exactly the identity leak
# the patches are supposed to be free of.
LEAKY_FORMAT_CONFIG = {
	'format.coverLetter': 'true',
	'format.signOff': 'true',
	'format.from': 'true',
	'format.to': 'someone@example.com',
	'format.cc': 'someone-else@example.com',
	'format.headers': 'X-Custom: yes',
	'format.subjectPrefix': 'RFC',
	'format.notes': 'true',
	'format.attach': 'true',
	'format.thread': 'true',
	'format.useAutoBase': 'true',
}


def test_save_ignores_local_format_config(
	gtp, workspace, base_env, alt_env, upstreams, read_manifest
):
	"""
	`format.*` in the checkout must not leak into the recorded series.

	The patch bytes are the file name, so a config-dependent byte is also a
	config-dependent name: the same history would be recorded differently by two
	people, defeating the whole point of content addressing.
	"""
	_add_simple(gtp, upstreams)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'lib.txt': 'beta\n'}, 'feat: change lib')
	assert gtp('save', 'third-party/simple').returncode == 0
	reference = _only_patch(workspace, read_manifest).read_bytes()

	for key, value in LEAKY_FORMAT_CONFIG.items():
		git(['config', key, value], target, base_env)
	# Saved by a second identity too, so `format.from` would show up as a name
	# that is not in the reference.
	assert (
		run_tool(workspace, ['save', 'third-party/simple'], env=alt_env).returncode == 0
	)

	names = read_manifest()['repos']['third-party/simple']['patches']
	assert len(names) == 1
	assert _only_patch(workspace, read_manifest).read_bytes() == reference
	# And it still replays.
	assert gtp('update', 'third-party/simple').returncode == 0
