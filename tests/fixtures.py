"""
Offline test fixtures for git-third-party.

Everything here builds *local* git repositories on disk so the test-suite never
touches the network. Upstream repos are served over plain filesystem paths and
configured with `uploadpack.allowAnySHA1InWant`, so the tool's
`git fetch origin --depth=1 <sha>` works offline against a pinned commit.

Runnable as a script to materialize the fixtures for manual inspection:

    python tests/fixtures.py /tmp/gtp-fixtures
"""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from importlib.machinery import SourceFileLoader
from pathlib import Path

# The tool under test.
TOOL = Path(__file__).resolve().parent.parent / 'git-third-party'

# Fixed identity + timestamps so generated commits (and therefore patches) are
# byte-for-byte reproducible across runs and machines.
FIXED_ENV = {
	'GIT_AUTHOR_NAME': 'Test Author',
	'GIT_AUTHOR_EMAIL': 'author@example.com',
	'GIT_AUTHOR_DATE': '@1577836800 +0000',
	'GIT_COMMITTER_NAME': 'Test Committer',
	'GIT_COMMITTER_EMAIL': 'committer@example.com',
	'GIT_COMMITTER_DATE': '@1577836800 +0000',
}

# Global git config shared by fixtures and the tool. `protocol.file.allow=always`
# is required for local (file-path) submodule clones on modern git.
GLOBAL_GITCONFIG = """\
[init]
	defaultBranch = main
[user]
	name = Fixture
	email = fixture@example.com
[protocol "file"]
	allow = always
[safe]
	directory = *
"""


def make_env(home: Path) -> dict:
	"""
	A hermetic git environment rooted at *home* (isolated global config).
	"""
	gitconfig = home / '.gitconfig'
	gitconfig.write_text(GLOBAL_GITCONFIG)
	env = dict(os.environ)
	env.update(FIXED_ENV)
	env['HOME'] = str(home)
	env['GIT_CONFIG_GLOBAL'] = str(gitconfig)
	env['GIT_CONFIG_SYSTEM'] = os.devnull
	env['GIT_TERMINAL_PROMPT'] = '0'
	env['GIT'] = 'git'
	return env


def git(args: list[str], cwd: Path, env: dict) -> subprocess.CompletedProcess:
	return subprocess.run(
		['git', *args],
		cwd=str(cwd),
		env=env,
		check=True,
		capture_output=True,
		text=True,
	)


def commit_files(repo: Path, env: dict, files: dict[str, str], message: str) -> str:
	"""
	Write *files* (relative path -> content), commit them, return the sha.
	"""
	for rel, content in files.items():
		path = repo.joinpath(*rel.split('/'))
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_text(content)
	git(['add', '-A'], repo, env)
	git(['commit', '-m', message], repo, env)
	return git(['rev-parse', 'HEAD'], repo, env).stdout.strip()


def _allow_sha(repo: Path, env: dict) -> None:
	git(['config', 'uploadpack.allowAnySHA1InWant', 'true'], repo, env)
	git(['config', 'uploadpack.allowReachableSHA1InWant', 'true'], repo, env)


def build_upstreams(base: Path, env: dict) -> dict:
	"""
	Create the upstream repositories the tests fetch from. All offline.
	"""
	base.mkdir(parents=True, exist_ok=True)

	# A plain two-commit repo. Tests pin at `c1` so the tool must fetch a commit
	# that is not the branch tip (exercising allowAnySHA1InWant).
	simple = base / 'simple'
	git(['init'], _mk(simple), env)
	c1 = commit_files(simple, env, {'README.md': 'v1\n', 'lib.txt': 'alpha\n'}, 'initial')
	c2 = commit_files(simple, env, {'README.md': 'v2\n'}, 'second')
	_allow_sha(simple, env)

	# A tiny repo used as a submodule.
	child = base / 'child'
	git(['init'], _mk(child), env)
	child_commit = commit_files(child, env, {'child.txt': 'child-v1\n'}, 'child init')
	_allow_sha(child, env)

	# A repo that embeds `child` as a submodule at `sub` via a local path url.
	parent = base / 'parent'
	git(['init'], _mk(parent), env)
	commit_files(parent, env, {'parent.txt': 'parent-v1\n'}, 'parent init')
	git(['submodule', 'add', str(child), 'sub'], parent, env)
	parent_commit = commit_files(parent, env, {}, 'add submodule')
	_allow_sha(parent, env)

	return {
		'simple': {'path': simple, 'c1': c1, 'c2': c2},
		'child': {'path': child, 'commit': child_commit},
		'parent': {'path': parent, 'commit': parent_commit},
	}


def make_workspace(ws: Path, env: dict) -> Path:
	"""
	An outer git repo that ignores `/third-party` (where repos are placed).
	"""
	git(['init'], _mk(ws), env)
	(ws / '.gitignore').write_text('/third-party\n')
	git(['add', '.gitignore'], ws, env)
	git(['commit', '-m', 'init'], ws, env)
	return ws


@dataclass
class ToolResult:
	returncode: int
	stdout: str
	stderr: str


def _load_tool():
	"""
	Import the extensionless `git-third-party` script as a module (cached).

	Driving the tool in-process (rather than as a subprocess) lets `pytest-cov`
	measure it directly, so plain `--cov`/`--cov-branch` reports real coverage.
	"""
	loader = SourceFileLoader('git_third_party', str(TOOL))
	spec = importlib.util.spec_from_loader(loader.name, loader)
	module = importlib.util.module_from_spec(spec)
	loader.exec_module(module)
	return module


_TOOL_MODULE = None


def tool_module():
	"""
	The imported tool module, so tests can monkeypatch its internals.
	"""
	global _TOOL_MODULE
	if _TOOL_MODULE is None:
		_TOOL_MODULE = _load_tool()
	return _TOOL_MODULE


def run_tool(
	workspace: Path, args, cwd: Path | None = None, env: dict | None = None
) -> ToolResult:
	global _TOOL_MODULE
	if _TOOL_MODULE is None:
		_TOOL_MODULE = _load_tool()

	out, err = io.StringIO(), io.StringIO()
	prev_cwd = os.getcwd()
	prev_env = os.environ.copy()
	try:
		os.chdir(str(cwd or workspace))
		if env is not None:
			os.environ.clear()
			os.environ.update(env)
		with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
			try:
				rc = _TOOL_MODULE.main(list(args))
			except SystemExit as exc:
				rc = exc.code if isinstance(exc.code, int) else 1
	finally:
		os.chdir(prev_cwd)
		os.environ.clear()
		os.environ.update(prev_env)
	return ToolResult(rc if rc is not None else 0, out.getvalue(), err.getvalue())


def _mk(path: Path) -> Path:
	path.mkdir(parents=True, exist_ok=True)
	return path


def tree_sha(repo: Path, env: dict) -> str:
	"""
	Content-addressed sha of the committed tree (metadata-independent).

	Two checkouts with identical file content share this sha even if the commit
	hashes differ, so it is the precise witness for "no information was lost".
	"""
	return git(['rev-parse', 'HEAD^{tree}'], repo, env).stdout.strip()


def snapshot_worktree(root: Path) -> dict[str, str]:
	"""
	Map every file in the working tree to a hash of its content.

	Walks the whole tree (including submodule checkouts), skipping `.git`
	metadata (a directory in a normal repo, a file in a submodule). Symlinks are
	recorded by target so they are compared without being followed.
	"""
	import hashlib

	result: dict[str, str] = {}
	for dirpath, dirnames, filenames in os.walk(root):
		dirnames[:] = [d for d in dirnames if d != '.git']
		for filename in filenames:
			if filename == '.git':
				continue
			full = Path(dirpath) / filename
			rel = str(full.relative_to(root))
			if full.is_symlink():
				result[rel] = 'symlink:' + os.readlink(full)
			else:
				result[rel] = 'file:' + hashlib.sha256(full.read_bytes()).hexdigest()
	return result


def _serializable(upstreams: dict) -> dict:
	return {
		name: {k: (str(v) if isinstance(v, Path) else v) for k, v in info.items()}
		for name, info in upstreams.items()
	}


def main(argv: list[str] | None = None) -> int:
	argv = sys.argv[1:] if argv is None else argv
	if len(argv) != 1:
		print(f'usage: {sys.argv[0]} <target-dir>', file=sys.stderr)
		return 2
	base = Path(argv[0]).resolve()
	home = base / 'home'
	home.mkdir(parents=True, exist_ok=True)
	env = make_env(home)
	upstreams = build_upstreams(base / 'upstreams', env)
	print(json.dumps(_serializable(upstreams), indent='\t'))
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
