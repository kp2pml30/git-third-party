"""
pytest fixtures: hermetic, offline git repositories for the tool tests.
"""

import json
from pathlib import Path

import pytest
from fixtures import (
	build_upstreams,
	make_env,
	make_workspace,
	run_tool,
)


@pytest.fixture(scope='session')
def base_env(tmp_path_factory) -> dict:
	home = tmp_path_factory.mktemp('git-home')
	return make_env(home)


@pytest.fixture(scope='session')
def alt_env(base_env) -> dict:
	"""
	A second identity (name, email, committer, dates all different) sharing
	the same global git config. Used to prove the person who re-applies/saves a
	patch does not leak into the patch bytes.
	"""
	env = dict(base_env)
	env.update(
		{
			'GIT_AUTHOR_NAME': 'Other Person',
			'GIT_AUTHOR_EMAIL': 'other@elsewhere.test',
			'GIT_AUTHOR_DATE': '@1600000000 +0500',
			'GIT_COMMITTER_NAME': 'Third Committer',
			'GIT_COMMITTER_EMAIL': 'third@elsewhere.test',
			'GIT_COMMITTER_DATE': '@1650000000 -0800',
		}
	)
	return env


@pytest.fixture(scope='session')
def upstreams(tmp_path_factory, base_env) -> dict:
	base = tmp_path_factory.mktemp('upstreams')
	return build_upstreams(base, base_env)


@pytest.fixture
def workspace(tmp_path, base_env) -> Path:
	return make_workspace(tmp_path / 'work', base_env)


@pytest.fixture
def gtp(workspace, base_env):
	"""
	Run the tool inside the workspace; returns the CompletedProcess.
	"""

	def run(*args, cwd: Path | None = None):
		return run_tool(workspace, list(args), cwd=cwd, env=base_env)

	return run


@pytest.fixture
def read_manifest(workspace):
	def read() -> dict:
		return json.loads((workspace / '.git-third-party' / 'manifest.json').read_text())

	return read
