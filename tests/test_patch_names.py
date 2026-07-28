"""
Content-addressed patch file names, and the migration off the legacy layout.

Patch files used to be named by their 1-based position in the series, with the
manifest recording only a count. Names are now the Crockford Base32 SHA-3 digest
of the patch bytes and the *order* lives in the manifest, so editing the series
touches one file instead of renumbering everything after it.
"""

import base64
import hashlib
import json
import shutil
import subprocess

import pytest
from fixtures import commit_files, git, snapshot_worktree, tool_module

# Crockford Base32, in the same order as RFC 4648's alphabet, so a standard
# base32 encoding can be translated into it. Independent of the tool's own
# encoder on purpose: this is what the names are checked against.
CROCKFORD = '0123456789abcdefghjkmnpqrstvwxyz'
_FROM_RFC4648 = str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567', CROCKFORD)


def expected_name(patch: bytes) -> str:
	"""
	The name the spec calls for: SHA3-256, first 80 bits, Crockford Base32.
	"""
	digest = hashlib.sha3_256(patch).digest()[:10]
	return base64.b32encode(digest).decode().translate(_FROM_RFC4648)


def _patches_dir(workspace):
	return workspace / '.git-third-party' / 'patches' / 'third-party' / 'simple'


def _manifest_path(workspace):
	return workspace / '.git-third-party' / 'manifest.json'


def _add_with_history(gtp, workspace, base_env, upstreams):
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'lib.txt': 'patched\n'}, 'feat: patch lib')
	commit_files(target, base_env, {'extra.txt': 'extra\n'}, 'feat: add extra')
	assert gtp('save', 'third-party/simple').returncode == 0
	return target


def _downgrade_to_legacy(workspace):
	"""
	Rewrite an already-saved repo into the old positional layout.

	This is the on-disk state a checkout made by an older version of the tool is
	in, and exactly what the migration has to pick up.
	"""
	manifest = json.loads(_manifest_path(workspace).read_text())
	names = manifest['repos']['third-party/simple']['patches']
	pdir = _patches_dir(workspace)
	contents = [pdir.joinpath(name).read_bytes() for name in names]
	for name in set(names):
		pdir.joinpath(name).unlink()
	for i, data in enumerate(contents, start=1):
		pdir.joinpath(str(i)).write_bytes(data)
	manifest['repos']['third-party/simple']['patches'] = len(contents)
	_manifest_path(workspace).write_text(json.dumps(manifest, indent='\t') + '\n')
	return contents


def test_patch_names_are_crockford_base32_digests(
	gtp, workspace, base_env, upstreams, read_manifest
):
	_add_with_history(gtp, workspace, base_env, upstreams)
	names = read_manifest()['repos']['third-party/simple']['patches']
	assert len(names) == 2
	for name in names:
		# 80 bits of SHA-3, so exactly 16 unpadded Crockford characters.
		assert len(name) == 16
		assert set(name) <= set(CROCKFORD)
		# And it is the digest of that exact file, not merely digest-shaped: a
		# different hash, a different slice of it or a swapped bit order all fail
		# here.
		assert name == expected_name(_patches_dir(workspace).joinpath(name).read_bytes())


def test_inserting_a_patch_keeps_the_other_names(
	gtp, workspace, base_env, upstreams, read_manifest
):
	target = _add_with_history(gtp, workspace, base_env, upstreams)
	before = read_manifest()['repos']['third-party/simple']['patches']

	# Insert a commit *before* the last one: under positional names this would
	# rewrite the content of every file from the insertion point on.
	git(['reset', '--hard', 'HEAD~1'], target, base_env)
	commit_files(target, base_env, {'mid.txt': 'mid\n'}, 'feat: middle')
	git(['cherry-pick', 'HEAD@{2}'], target, base_env)
	assert gtp('save', 'third-party/simple').returncode == 0

	after = read_manifest()['repos']['third-party/simple']['patches']
	assert len(after) == 3
	# First and last patch are untouched; only the inserted one is new.
	assert after[0] == before[0]
	assert after[2] == before[1]
	assert {p.name for p in _patches_dir(workspace).iterdir()} == set(after)


def test_identical_patches_share_one_file(
	gtp, workspace, base_env, upstreams, read_manifest
):
	"""
	A repeated patch is one file listed twice, and still applies twice.
	"""
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'dup.txt': 'dup\n'}, 'feat: dup')
	git(['rm', 'dup.txt'], target, base_env)
	git(['commit', '-m', 'feat: drop dup'], target, base_env)
	commit_files(target, base_env, {'dup.txt': 'dup\n'}, 'feat: dup')

	assert gtp('save', 'third-party/simple').returncode == 0
	names = read_manifest()['repos']['third-party/simple']['patches']
	assert names[0] == names[2]
	assert len({p.name for p in _patches_dir(workspace).iterdir()}) == 2

	before = snapshot_worktree(target)
	shutil.rmtree(target)
	assert gtp('update', 'third-party/simple').returncode == 0
	assert snapshot_worktree(target) == before


def test_colliding_names_are_refused(
	gtp, workspace, base_env, upstreams, monkeypatch, read_manifest
):
	"""
	Two different patches under one name must never silently overwrite.

	The digest is truncated, so a collision is astronomically unlikely rather
	than impossible; it is forced here to prove the check fires.
	"""
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'a.txt': 'a\n'}, 'feat: a')
	commit_files(target, base_env, {'b.txt': 'b\n'}, 'feat: b')

	monkeypatch.setattr(tool_module(), '_patch_name', lambda data: 'collide')
	res = gtp('save', 'third-party/simple')
	assert res.returncode == 1
	assert 'collision' in res.stderr
	# Nothing recorded, and not one file written: the rejected series is resolved
	# in full before anything touches the patches directory.
	assert read_manifest()['repos']['third-party/simple']['patches'] == []
	assert list(_patches_dir(workspace).iterdir()) == []


def test_update_migrates_legacy_layout(
	gtp, workspace, base_env, upstreams, read_manifest
):
	target = _add_with_history(gtp, workspace, base_env, upstreams)
	before = snapshot_worktree(target)
	contents = _downgrade_to_legacy(workspace)
	assert {p.name for p in _patches_dir(workspace).iterdir()} == {'1', '2'}

	shutil.rmtree(target)
	res = gtp('update', 'third-party/simple')
	assert res.returncode == 0, res.stderr

	names = read_manifest()['repos']['third-party/simple']['patches']
	assert len(names) == 2
	assert {p.name for p in _patches_dir(workspace).iterdir()} == set(names)
	# Renamed, not rewritten: the patch bytes and the result are unchanged.
	assert [_patches_dir(workspace).joinpath(n).read_bytes() for n in names] == contents
	assert snapshot_worktree(target) == before


def test_save_migrates_legacy_layout(
	gtp, workspace, base_env, upstreams, read_manifest
):
	_add_with_history(gtp, workspace, base_env, upstreams)
	contents = _downgrade_to_legacy(workspace)

	assert gtp('save', 'third-party/simple').returncode == 0

	names = read_manifest()['repos']['third-party/simple']['patches']
	assert {p.name for p in _patches_dir(workspace).iterdir()} == set(names)
	assert [_patches_dir(workspace).joinpath(n).read_bytes() for n in names] == contents


def test_migration_refuses_to_lose_a_missing_patch(
	gtp, workspace, base_env, upstreams, read_manifest
):
	_add_with_history(gtp, workspace, base_env, upstreams)
	_downgrade_to_legacy(workspace)
	_patches_dir(workspace).joinpath('2').unlink()

	res = gtp('update', 'third-party/simple')
	assert res.returncode == 1
	assert 'can not migrate' in res.stderr
	# Nothing renamed, nothing dropped: the legacy layout is left as it was.
	assert read_manifest()['repos']['third-party/simple']['patches'] == 2
	assert {p.name for p in _patches_dir(workspace).iterdir()} == {'1'}


@pytest.mark.parametrize(
	'data',
	[
		b'\x00' * 10,
		b'\xff' * 10,
		# Every bit position distinct, so a wrong bit or byte order shows up.
		bytes(range(10)),
		b'\x80' + b'\x00' * 9,
		b'\x00' * 9 + b'\x01',
	],
)
def test_crockford_encoding_matches_standard_base32(data):
	expected = base64.b32encode(data).decode().translate(_FROM_RFC4648)
	assert tool_module()._crockford32(data) == expected


def test_failed_command_after_migration_leaves_manifest_consistent(
	gtp, workspace, base_env, upstreams, read_manifest
):
	"""
	A command that fails *after* migrating still leaves the migration committed.

	The positional files are unlinked as part of the migration, so a manifest that
	still described them -- because the command aborted before the manifest was
	written -- would leave the repo unusable by every subsequent command. This
	covers the abort path only; a crash mid-write is not exercised.
	"""
	target = _add_with_history(gtp, workspace, base_env, upstreams)
	_downgrade_to_legacy(workspace)
	# A commit no patch records: update refuses, after the migration has run.
	commit_files(target, base_env, {'unsaved.txt': 'unsaved\n'}, 'feat: unsaved')

	res = gtp('update', 'third-party/simple')
	assert res.returncode == 1
	assert 'ahead' in res.stderr

	names = read_manifest()['repos']['third-party/simple']['patches']
	assert len(names) == 2
	assert {p.name for p in _patches_dir(workspace).iterdir()} == set(names)

	# And the repo is still usable: save the extra commit, then replay.
	assert gtp('save', 'third-party/simple').returncode == 0
	before = snapshot_worktree(target)
	shutil.rmtree(target)
	assert gtp('update', 'third-party/simple').returncode == 0
	assert snapshot_worktree(target) == before


def test_failed_save_all_leaves_earlier_repos_consistent(
	gtp, workspace, base_env, upstreams, read_manifest
):
	"""
	A repo already saved by a `--all` run must not be left describing dead files.

	`save` prunes patch files that dropped out of the series, so the manifest it
	produced has to reach disk before the run can fail on the next repo.
	"""
	simple = upstreams['simple']
	for name in ['third-party/a', 'third-party/b']:
		assert gtp('add', name, str(simple['path']), simple['c1']).returncode == 0
		commit_files(
			workspace.joinpath(*name.split('/')), base_env, {'x.txt': name + '\n'}, 'feat: x'
		)
	# `b` can not be saved, so the run fails after `a` is already written.
	(workspace / 'third-party' / 'b' / 'x.txt').write_text('uncommitted\n')

	res = gtp('save', '--all')
	assert res.returncode == 1
	assert 'dirty' in res.stderr

	manifest = read_manifest()
	assert manifest['repos']['third-party/b']['patches'] == []
	names = manifest['repos']['third-party/a']['patches']
	assert len(names) == 1
	pdir = workspace / '.git-third-party' / 'patches' / 'third-party' / 'a'
	assert {p.name for p in pdir.iterdir()} == set(names)


def test_patch_bytes_are_not_normalized_by_the_enclosing_repo(
	gtp, workspace, base_env, upstreams, read_manifest
):
	"""
	A `text=auto` rule in the outer repo must not rewrite stored patch bytes.

	`* text=auto eol=lf` is the recommended setting and normalizes CRLF on `git
	add`. A patch is named after its bytes, so a normalized one applies different
	content on a fresh clone and then collides with itself on the next `save`.
	The tool has to opt its own directory out.
	"""
	(workspace / '.gitattributes').write_text('* text=auto eol=lf\n')
	git(['add', '.gitattributes'], workspace, base_env)
	git(['commit', '-m', 'normalize line endings'], workspace, base_env)

	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	target = workspace / 'third-party' / 'simple'
	(target / 'crlf.txt').write_bytes(b'first\r\nsecond\r\n')
	git(['add', '-A'], target, base_env)
	git(['commit', '-m', 'feat: crlf file'], target, base_env)
	assert gtp('save', 'third-party/simple').returncode == 0

	name = read_manifest()['repos']['third-party/simple']['patches'][0]
	on_disk = _patches_dir(workspace).joinpath(name).read_bytes()
	assert b'\r\n' in on_disk

	# What git would store, which is what a fresh clone gets back.
	git(['add', '-A', '.git-third-party'], workspace, base_env)
	staged = subprocess.run(
		['git', 'cat-file', 'blob', f':.git-third-party/patches/third-party/simple/{name}'],
		cwd=str(workspace),
		env=base_env,
		check=True,
		capture_output=True,
	).stdout
	assert staged == on_disk


def test_crlf_content_survives_a_round_trip(gtp, workspace, base_env, upstreams):
	"""
	Patched content with CRLF (and no trailing newline) must come back verbatim.

	Patches are read and written as bytes precisely so git's `\\ No newline at end
	of file` marker and any embedded CR are replayed rather than normalized.
	"""
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	target = workspace / 'third-party' / 'simple'
	(target / 'crlf.txt').write_bytes(b'first\r\nsecond\r\nno trailing newline')
	git(['add', '-A'], target, base_env)
	git(['commit', '-m', 'feat: crlf file'], target, base_env)
	assert gtp('save', 'third-party/simple').returncode == 0

	before = snapshot_worktree(target)
	shutil.rmtree(target)
	assert gtp('update', 'third-party/simple').returncode == 0
	assert snapshot_worktree(target) == before
	assert (target / 'crlf.txt').read_bytes() == b'first\r\nsecond\r\nno trailing newline'


# Local git settings that change what `git am` produces: `am.keepcr=false` drops
# a `\r` that is real content, `apply.whitespace=fix` rewrites indentation, and
# `am.messageId` appends a trailer to the commit message -- which is part of the
# patch bytes, so it would rename the whole series on the next `save`.
HOSTILE_AM_CONFIG = {
	'am.keepcr': 'false',
	'apply.whitespace': 'fix',
	'am.messageId': 'true',
}


def test_update_ignores_local_am_config(
	gtp, workspace, base_env, upstreams, read_manifest
):
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	target = workspace / 'third-party' / 'simple'
	# Content that every one of those settings would mangle: CRLF endings and a
	# line indented with a space before a tab.
	(target / 'crlf.txt').write_bytes(b'first\r\nsecond\r\n \tindented\r\n')
	git(['add', '-A'], target, base_env)
	git(['commit', '-m', 'feat: crlf file'], target, base_env)
	assert gtp('save', 'third-party/simple').returncode == 0
	before = read_manifest()['repos']['third-party/simple']['patches']

	for key, value in HOSTILE_AM_CONFIG.items():
		git(['config', key, value], target, base_env)
	# Drop the local commit so `update` has to replay the patch.
	git(['reset', '--hard', simple['c1']], target, base_env)
	assert gtp('update', 'third-party/simple').returncode == 0

	assert (target / 'crlf.txt').read_bytes() == b'first\r\nsecond\r\n \tindented\r\n'
	# And the replayed commit re-saves to the same patch: no trailer crept into
	# the message.
	assert gtp('save', 'third-party/simple').returncode == 0
	assert read_manifest()['repos']['third-party/simple']['patches'] == before


def test_unfinished_am_is_reported(gtp, workspace, base_env, upstreams):
	"""
	A conflicted `git am` left behind must be named, not hit as a git error.

	The working tree is clean in that state, so nothing else notices; every later
	`am` would fail with `previous rebase directory ... still exists`.
	"""
	target = _add_with_history(gtp, workspace, base_env, upstreams)
	patch = _patches_dir(workspace).joinpath(
		json.loads(_manifest_path(workspace).read_text())['repos']['third-party/simple'][
			'patches'
		][0]
	)
	# Replay a patch that is already applied: it conflicts, and `am` stops.
	rs = subprocess.run(
		['git', 'am', str(patch)],
		cwd=str(target),
		env=base_env,
		capture_output=True,
	)
	assert rs.returncode != 0
	assert (target / '.git' / 'rebase-apply').exists()

	res = gtp('update', 'third-party/simple')
	assert res.returncode == 1
	assert 'unfinished `git am`' in res.stderr
	assert 'git am --abort' in res.stderr


def test_legacy_manifest_with_unknown_repos_is_not_dropped(
	gtp, workspace, base_env, upstreams
):
	"""
	A `config.json` holding a repo the manifest lacks is real work, not leftovers.

	That is what a merge with someone still on an older version produces, and the
	rename must refuse rather than unlink it.
	"""
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	legacy = workspace / '.git-third-party' / 'config.json'
	legacy.write_text(
		json.dumps(
			{
				'repos': {
					'third-party/other': {
						'url': str(simple['path']),
						'commit': simple['c1'],
						'patches': [],
					}
				}
			},
			indent='\t',
		)
		+ '\n'
	)

	res = gtp('update', '--all')
	assert res.returncode == 1
	assert 'third-party/other' in res.stderr
	assert legacy.exists()
