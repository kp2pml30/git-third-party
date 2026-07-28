"""
Managed checkouts must be fetchable but never pushable.
"""

import json
import subprocess

from fixtures import git


NO_PUSH_URL = 'no-push://disabled-by-git-third-party'


def _unshallow(target, upstream, env) -> None:
	"""
	Undo the `--depth=1` fetch the tool does.

	A shallow checkout is refused by the receiving end whatever the url is
	("shallow update not allowed"), which would make a push test pass without
	proving anything about the push url.
	"""
	git(['fetch', '--unshallow', str(upstream)], target, env)


def _push_urls(repo, env) -> list[str]:
	"""
	Every push url of `origin` -- git pushes to all of them, not just the first.
	"""
	return git(
		['remote', 'get-url', '--push', '--all', 'origin'], repo, env
	).stdout.split()


def test_add_disables_push_url(gtp, workspace, base_env, upstreams):
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	target = workspace / 'third-party' / 'simple'
	# Fetching still points at upstream, pushing does not.
	assert git(['remote', 'get-url', 'origin'], target, base_env).stdout.strip() == str(
		simple['path']
	)
	assert _push_urls(target, base_env) == [NO_PUSH_URL]


def test_push_actually_fails(gtp, workspace, base_env, upstreams):
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	target = workspace / 'third-party' / 'simple'
	_unshallow(target, simple['path'], base_env)
	res = subprocess.run(
		['git', 'push', 'origin', 'HEAD:refs/heads/pushed'],
		cwd=str(target),
		env=base_env,
		capture_output=True,
		text=True,
	)
	assert res.returncode != 0
	# And upstream gained no ref from the attempt.
	assert 'pushed' not in git(['branch', '--all'], simple['path'], base_env).stdout


def test_update_repairs_a_pushable_checkout(gtp, workspace, base_env, upstreams):
	"""
	Checkouts created by an older version get the push url on the next update.
	"""
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	target = workspace / 'third-party' / 'simple'
	git(['remote', 'set-url', '--push', 'origin', str(simple['path'])], target, base_env)
	# A second push url: `set-url --push` replaces only the first one, so a repair
	# that used it alone would leave this one live.
	git(
		['remote', 'set-url', '--push', '--add', 'origin', str(simple['path'])],
		target,
		base_env,
	)

	assert gtp('update', 'third-party/simple').returncode == 0
	assert _push_urls(target, base_env) == [NO_PUSH_URL]


def test_add_initializes_an_existing_empty_directory(
	gtp, workspace, base_env, upstreams
):
	"""
	A directory that exists but is not a repo must not fall through to the
	enclosing repository.
	"""
	simple = upstreams['simple']
	target = workspace / 'third-party' / 'simple'
	target.mkdir(parents=True)
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	assert (
		git(['rev-parse', '--show-toplevel'], target, base_env)
		.stdout.strip()
		.endswith('third-party/simple')
	)
	assert _push_urls(target, base_env) == [NO_PUSH_URL]


def test_update_repoints_origin_at_the_configured_url(
	gtp, workspace, base_env, upstreams
):
	"""
	The manifest is the source of truth for where the code comes from.
	"""
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	target = workspace / 'third-party' / 'simple'
	manifest_path = workspace / '.git-third-party' / 'manifest.json'
	manifest = json.loads(manifest_path.read_text())
	moved = str(upstreams['child']['path'])
	manifest['repos']['third-party/simple']['url'] = moved
	manifest_path.write_text(json.dumps(manifest, indent='\t') + '\n')

	# The pinned commit is already in the checkout, so nothing is fetched; only
	# the remote is expected to move.
	assert gtp('update', 'third-party/simple').returncode == 0
	assert git(['remote', 'get-url', 'origin'], target, base_env).stdout.strip() == moved
	assert _push_urls(target, base_env) == [NO_PUSH_URL]


def test_push_fails_even_next_to_a_same_named_repository(
	gtp, workspace, base_env, upstreams
):
	"""
	The sentinel must not be something git can resolve.

	A bare word would be a relative path, so a repository sitting under that name
	in the checkout would quietly become a valid push target.
	"""
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	target = workspace / 'third-party' / 'simple'
	decoy = target / NO_PUSH_URL.rsplit('/', 1)[-1]
	git(['init', '--bare', str(decoy)], target, base_env)
	_unshallow(target, simple['path'], base_env)

	res = subprocess.run(
		['git', 'push', 'origin', 'HEAD:refs/heads/pushed'],
		cwd=str(target),
		env=base_env,
		capture_output=True,
		text=True,
	)
	assert res.returncode != 0
	assert 'pushed' not in git(['branch', '--all'], decoy, base_env).stdout


def test_save_also_disables_push(gtp, workspace, base_env, upstreams):
	"""
	A checkout that is only ever `save`d is repaired too.
	"""
	simple = upstreams['simple']
	assert (
		gtp('add', 'third-party/simple', str(simple['path']), simple['c1']).returncode == 0
	)
	target = workspace / 'third-party' / 'simple'
	git(['remote', 'set-url', '--push', 'origin', str(simple['path'])], target, base_env)

	assert gtp('save', 'third-party/simple').returncode == 0
	assert _push_urls(target, base_env) == [NO_PUSH_URL]
