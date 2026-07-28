"""
`add` subcommand: registering and checking out a third-party repo.
"""

import pytest


def test_add_checks_out_pinned_commit(gtp, workspace, upstreams):
	simple = upstreams['simple']
	res = gtp('add', 'third-party/simple', str(simple['path']), simple['c1'])
	assert res.returncode == 0, res.stderr
	target = workspace / 'third-party' / 'simple'
	# Pinned at c1, not the branch tip (c2 changed README to v2).
	assert (target / 'README.md').read_text() == 'v1\n'
	assert (target / 'lib.txt').read_text() == 'alpha\n'


def test_add_writes_manifest_entry(gtp, workspace, upstreams, read_manifest):
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	entry = read_manifest()['repos']['third-party/simple']
	assert entry == {
		'url': str(simple['path']),
		'commit': simple['c1'],
		'patches': [],
	}


def test_add_rejects_wrong_arg_count(gtp, workspace):
	res = gtp('add', 'third-party/x')
	assert res.returncode == 1
	# A failed add must not persist a manifest.
	assert not (workspace / '.git-third-party' / 'manifest.json').exists()


@pytest.mark.parametrize('bad', ['a:b', 'a;b', 'a\\b'])
def test_add_rejects_bad_path_chars(gtp, workspace, upstreams, bad):
	simple = upstreams['simple']
	res = gtp('add', f'third-party/{bad}', str(simple['path']), simple['c1'])
	assert res.returncode == 1
	assert 'bad path' in res.stderr
	assert not (workspace / '.git-third-party' / 'manifest.json').exists()


def test_add_rejects_path_outside_repo(gtp, workspace, upstreams, tmp_path):
	simple = upstreams['simple']
	outside = tmp_path / 'outside'
	res = gtp('add', str(outside), str(simple['path']), simple['c1'])
	assert res.returncode == 1
	assert 'not in git subtree' in res.stderr


def test_add_rejects_non_ignored_directory(gtp, workspace, upstreams):
	simple = upstreams['simple']
	# Only `/third-party` is gitignored in the workspace.
	res = gtp('add', 'not-ignored/simple', str(simple['path']), simple['c1'])
	assert res.returncode == 1
	assert 'not ignored' in res.stderr


def test_add_rejects_duplicate(gtp, workspace, upstreams):
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	res = gtp('add', 'third-party/simple', str(simple['path']), simple['c1'])
	assert res.returncode == 1
	assert 'already in manifest' in res.stderr
