"""The real command-line entrypoint (`__main__` guard, argv parsing), driven as
an actual subprocess so the installed script is exercised end to end."""

import subprocess
import sys

from fixtures import TOOL, run_tool


def test_errors_when_not_in_a_git_repo(tmp_path, base_env):
	plain = tmp_path / 'not-a-repo'
	plain.mkdir()
	res = run_tool(plain, ['update', '--all'], cwd=plain, env=base_env)
	assert res.returncode == 1
	assert 'could not execute' in res.stderr


def test_unknown_subcommand_reports_usage(gtp):
	res = gtp('definitely-not-a-subcommand')
	assert res.returncode == 1
	assert 'expected one of following subcommands' in res.stderr


def test_update_without_paths_errors(gtp):
	res = gtp('update')
	assert res.returncode == 1
	assert 'non-empty' in res.stderr


def test_cli_reports_usage_without_arguments(workspace, base_env):
	res = subprocess.run(
		[sys.executable, str(TOOL)],
		cwd=str(workspace),
		env=base_env,
		capture_output=True,
		text=True,
	)
	assert res.returncode == 1
	assert 'expected one of following subcommands' in res.stderr


def test_cli_add_end_to_end(workspace, base_env, upstreams):
	simple = upstreams['simple']
	res = subprocess.run(
		[
			sys.executable,
			str(TOOL),
			'add',
			'third-party/simple',
			str(simple['path']),
			simple['c1'],
		],
		cwd=str(workspace),
		env=base_env,
		capture_output=True,
		text=True,
	)
	assert res.returncode == 0, res.stderr
	assert (workspace / 'third-party' / 'simple' / 'README.md').read_text() == 'v1\n'
