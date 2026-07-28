"""
The manifest file, and the migration off its old name.

Older versions called it `.git-third-party/config.json`, which was a misnomer:
nothing in it is configuration, it is the set of managed repositories and the
patch series each one carries. It is `manifest.json` now, and a tree written by
an older version is renamed the next time the tool writes.
"""

import json

from fixtures import commit_files


def _manifest_path(workspace):
	return workspace / '.git-third-party' / 'manifest.json'


def _legacy_path(workspace):
	return workspace / '.git-third-party' / 'config.json'


def _downgrade_to_legacy_name(workspace) -> dict:
	"""
	Put the manifest back under the name an older version of the tool wrote.
	"""
	manifest = json.loads(_manifest_path(workspace).read_text())
	_legacy_path(workspace).write_text(json.dumps(manifest, indent='\t') + '\n')
	_manifest_path(workspace).unlink()
	return manifest


def _add_and_save(gtp, workspace, base_env, upstreams):
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'lib.txt': 'patched\n'}, 'feat: patch lib')
	assert gtp('save', 'third-party/simple').returncode == 0
	return target


def test_manifest_is_written_under_the_new_name(gtp, workspace, base_env, upstreams):
	_add_and_save(gtp, workspace, base_env, upstreams)
	assert _manifest_path(workspace).exists()
	assert not _legacy_path(workspace).exists()


def test_legacy_named_manifest_is_read(gtp, workspace, base_env, upstreams):
	_add_and_save(gtp, workspace, base_env, upstreams)
	before = _downgrade_to_legacy_name(workspace)

	# The repo is only known through the legacy file; if it were not read, this
	# would fail with "not in manifest" instead of updating.
	assert gtp('update', 'third-party/simple').returncode == 0
	assert json.loads(_manifest_path(workspace).read_text()) == before


def test_legacy_named_manifest_is_renamed(gtp, workspace, base_env, upstreams):
	_add_and_save(gtp, workspace, base_env, upstreams)
	_downgrade_to_legacy_name(workspace)

	assert gtp('update', 'third-party/simple').returncode == 0
	# One file, not two: a leftover would keep diverging from the real manifest
	# and silently feed anything still reading the old name.
	assert not _legacy_path(workspace).exists()


def test_new_name_wins_over_a_stale_legacy_file(gtp, workspace, base_env, upstreams):
	"""
	Both names present is the state a crash mid-rename leaves behind.

	The new file is the one that was just written, so it must win; the stale one
	is unreferenced and gets swept by the same write that reads it.
	"""
	_add_and_save(gtp, workspace, base_env, upstreams)
	current = json.loads(_manifest_path(workspace).read_text())
	stale = {'repos': {}}
	_legacy_path(workspace).write_text(json.dumps(stale, indent='\t') + '\n')

	assert gtp('update', '--all').returncode == 0
	assert json.loads(_manifest_path(workspace).read_text()) == current
	assert not _legacy_path(workspace).exists()
