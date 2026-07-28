"""
Guard against clobbering local work.

`_dirty_check` unit tests drive the guard directly by pointing the tool's module
globals at a scratch repo; the integration tests exercise the same guard through
the real `update`/`save` command path. Together they pin the promise that the
tool refuses to run on a repo with local modifications — plain files, staged
changes, or a dirty submodule — instead of silently overwriting them.
"""

from pathlib import Path

import pytest
from fixtures import _load_tool, commit_files, git

# --------------------------------------------------------------------------- #
# Unit tests: call `_dirty_check` directly.
# --------------------------------------------------------------------------- #


@pytest.fixture
def tool():
	"""
	A fresh in-process copy of the tool, independent of run_tool's cache.
	"""
	return _load_tool()


def _point_tool_at(tool, top: Path, env: dict) -> None:
	# `_dirty_check` only consults these two module globals.
	tool.top_dir = top
	tool.GIT = env.get('GIT', 'git')


@pytest.fixture
def unit_repo(tmp_path, base_env, tool):
	"""
	A clean committed repo at <top>/pkg, with tool globals aimed at <top>.
	"""
	top = tmp_path / 'top'
	target = top / 'pkg'
	target.mkdir(parents=True)
	git(['init'], target, base_env)
	commit_files(target, base_env, {'a.txt': 'a\n', 'b.txt': 'b\n'}, 'init')
	_point_tool_at(tool, top, base_env)
	return tool, target


@pytest.fixture
def unit_repo_with_submodule(tmp_path, base_env, upstreams, tool):
	"""
	Like `unit_repo`, but the target embeds `child` as a submodule at `sub`.
	"""
	top = tmp_path / 'top'
	target = top / 'pkg'
	target.mkdir(parents=True)
	git(['init'], target, base_env)
	commit_files(target, base_env, {'a.txt': 'a\n'}, 'init')
	git(['submodule', 'add', str(upstreams['child']['path']), 'sub'], target, base_env)
	git(['commit', '-m', 'add submodule'], target, base_env)
	_point_tool_at(tool, top, base_env)
	return tool, target


def test_dirty_check_passes_on_clean_repo(unit_repo):
	tool, _ = unit_repo
	tool._dirty_check('pkg')  # must not raise


def test_dirty_check_flags_unstaged_modification(unit_repo):
	tool, target = unit_repo
	(target / 'a.txt').write_text('modified\n')
	with pytest.raises(tool.GitThirdPartyException, match='dirty'):
		tool._dirty_check('pkg')


def test_dirty_check_flags_staged_modification(unit_repo, base_env):
	tool, target = unit_repo
	(target / 'a.txt').write_text('modified\n')
	git(['add', 'a.txt'], target, base_env)
	# The unstaged diff is clean now, so this can only trip on the `--cached`
	# branch of the guard.
	with pytest.raises(tool.GitThirdPartyException, match='dirty'):
		tool._dirty_check('pkg')


def test_dirty_check_flags_staged_new_file(unit_repo, base_env):
	tool, target = unit_repo
	(target / 'c.txt').write_text('c\n')
	git(['add', 'c.txt'], target, base_env)
	with pytest.raises(tool.GitThirdPartyException, match='dirty'):
		tool._dirty_check('pkg')


def test_dirty_check_flags_untracked_file(unit_repo):
	tool, target = unit_repo
	# A brand-new untracked file is real local work; the guard must refuse rather
	# than let a later checkout/patch stomp on it.
	# RED until the porcelain rewrite: `git diff` never reports untracked files.
	(target / 'untracked.txt').write_text('scratch\n')
	with pytest.raises(tool.GitThirdPartyException, match='dirty'):
		tool._dirty_check('pkg')


def test_dirty_check_passes_with_clean_submodule(unit_repo_with_submodule):
	tool, target = unit_repo_with_submodule
	assert (target / 'sub' / 'child.txt').read_text() == 'child-v1\n'
	tool._dirty_check('pkg')  # must not raise


def test_dirty_check_flags_dirty_submodule(unit_repo_with_submodule):
	tool, target = unit_repo_with_submodule
	# Editing tracked content *inside* the submodule leaves the superproject with
	# a dirty gitlink, which the guard must catch.
	(target / 'sub' / 'child.txt').write_text('hacked in submodule\n')
	with pytest.raises(tool.GitThirdPartyException, match='dirty'):
		tool._dirty_check('pkg')


def test_dirty_check_flags_dirty_submodule_despite_ignore_config(
	unit_repo_with_submodule, base_env
):
	tool, target = unit_repo_with_submodule
	# A hostile-but-legal local config that suppresses submodule changes in
	# `git diff`. The guard must not rely on the default and miss the dirt.
	# RED until the porcelain rewrite passes `--ignore-submodules=none`.
	git(['config', 'diff.ignoreSubmodules', 'all'], target, base_env)
	(target / 'sub' / 'child.txt').write_text('hacked in submodule\n')
	with pytest.raises(tool.GitThirdPartyException, match='dirty'):
		tool._dirty_check('pkg')


def test_dirty_check_message_names_offending_path(unit_repo):
	tool, target = unit_repo
	# The refusal must say *what* is dirty so the user can act on it.
	# RED until the porcelain rewrite includes the status output in the message.
	(target / 'a.txt').write_text('modified\n')
	with pytest.raises(tool.GitThirdPartyException, match='a.txt'):
		tool._dirty_check('pkg')


# --------------------------------------------------------------------------- #
# Integration tests: the full command path via run_tool.
# --------------------------------------------------------------------------- #


def _add_simple(gtp, base_env, upstreams, workspace):
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	target = workspace / 'third-party' / 'simple'
	commit_files(target, base_env, {'lib.txt': 'patched\n'}, 'feat: patch lib')
	assert gtp('save', 'third-party/simple').returncode == 0
	return target


def _add_parent(gtp, upstreams, workspace):
	parent = upstreams['parent']
	assert (
		gtp('add', 'third-party/parent', str(parent['path']), parent['commit']).returncode
		== 0
	)
	return workspace / 'third-party' / 'parent'


def test_update_refuses_staged_change(gtp, workspace, base_env, upstreams):
	target = _add_simple(gtp, base_env, upstreams, workspace)

	# Stage (but do not commit) an edit; update must refuse without touching it.
	(target / 'lib.txt').write_text('staged edit\n')
	git(['add', 'lib.txt'], target, base_env)
	res = gtp('update', 'third-party/simple')
	assert res.returncode == 1
	assert 'dirty' in res.stderr
	assert (target / 'lib.txt').read_text() == 'staged edit\n'


def test_save_refuses_staged_change(gtp, workspace, base_env, upstreams, read_manifest):
	target = _add_simple(gtp, base_env, upstreams, workspace)

	(target / 'lib.txt').write_text('staged edit\n')
	git(['add', 'lib.txt'], target, base_env)
	res = gtp('save', 'third-party/simple')
	assert res.returncode == 1
	assert 'dirty' in res.stderr
	# The recorded patch series is left untouched.
	assert len(read_manifest()['repos']['third-party/simple']['patches']) == 1


def test_update_refuses_dirty_submodule(gtp, workspace, base_env, upstreams):
	target = _add_parent(gtp, upstreams, workspace)
	assert gtp('save', 'third-party/parent').returncode == 0

	# A hand-edit inside the checked-out submodule must block update.
	sub_file = target / 'sub' / 'child.txt'
	sub_file.write_text('hand-edited submodule\n')
	res = gtp('update', 'third-party/parent')
	assert res.returncode == 1
	assert 'dirty' in res.stderr
	assert sub_file.read_text() == 'hand-edited submodule\n'


def test_save_refuses_dirty_submodule(gtp, workspace, base_env, upstreams):
	target = _add_parent(gtp, upstreams, workspace)

	sub_file = target / 'sub' / 'child.txt'
	sub_file.write_text('hand-edited submodule\n')
	res = gtp('save', 'third-party/parent')
	assert res.returncode == 1
	assert 'dirty' in res.stderr
	assert sub_file.read_text() == 'hand-edited submodule\n'


def test_update_refuses_untracked_file(gtp, workspace, base_env, upstreams):
	target = _add_simple(gtp, base_env, upstreams, workspace)

	# An untracked scratch file is local work; update must refuse and leave it in
	# place. RED until the porcelain rewrite: today the guard ignores untracked
	# files, so update runs and returns 0.
	(target / 'LOCAL_NOTES.txt').write_text('my notes\n')
	res = gtp('update', 'third-party/simple')
	assert res.returncode == 1
	assert 'dirty' in res.stderr
	assert (target / 'LOCAL_NOTES.txt').read_text() == 'my notes\n'
