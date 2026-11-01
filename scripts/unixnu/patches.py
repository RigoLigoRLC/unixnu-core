"""Ordered XNU patch series and target-local source preparation."""
import hashlib
import json
import os
import shutil
import time

from .profiles import resolve_path
from .util import Error, git, log, run


def plan(ctx, modules):
    result = []
    for reference in ctx.board.get('kernel', {}).get('patch_series', []):
        series = resolve_path(ctx, reference, modules)
        if not series.is_file():
            raise Error(f'patch series missing: {series}')
        for number, line in enumerate(series.read_text().splitlines(), 1):
            entry = line.strip()
            if not entry or entry.startswith('#'):
                continue
            if entry.startswith('component:') or entry.partition(':')[0] in ctx.profile_roots:
                path = resolve_path(ctx, entry, modules)
            else:
                path = series.parent / entry
            path = path.resolve()
            if not path.is_file():
                raise Error(f'{series}:{number}: patch missing: {path}')
            if path in result:
                raise Error(f'patch appears twice in the selected series: {path}')
            result.append(path)
    return result


def prepare(ctx, modules):
    selected = plan(ctx, modules)
    module = modules.get(('refer', 'xnu'))
    if not module or module.path is None:
        raise Error('XNU source missing; run unixnu fetch')
    revision = git(module.path, 'rev-parse', 'HEAD').strip()
    records = []
    for path in selected:
        stat = path.stat()
        records.append([str(path), stat.st_size, stat.st_mtime_ns])
    signature = {'xnu_commit': revision, 'patches': records}
    if os.environ.get('UNIXNU_RECORD_HASHES', '1') != '0':
        signature['sha256'] = [hashlib.sha256(path.read_bytes()).hexdigest() for path in selected]
    work = ctx.tree / '.cache/xnu-work'
    cache = work.parent
    stamp = work / '.unixnu-patch-selection.json'
    try:
        previous = json.loads(stamp.read_text())
    except (FileNotFoundError, ValueError):
        previous = None
    if previous != signature or not (work / '.git').is_dir():
        log(f'kernel: prepare XNU {revision[:12]}')
        if work.exists():
            saved = cache / f'xnu-work-before-patch-update-{time.time_ns()}'
            work.rename(saved)
            log(f'kernel: preserved previous XNU source at {saved}')
        objects = ctx.tree / 'build/xnu/ios-obj'
        if objects.exists():
            saved = objects.with_name(f'ios-obj-before-patch-update-{time.time_ns()}')
            objects.rename(saved)
            log(f'kernel: preserved previous XNU objects at {saved}')
        for header_stamp in (cache / 'fakeroot').glob('.xnu-*-headers'):
            header_stamp.unlink()
        work.parent.mkdir(parents=True, exist_ok=True)
        run(['git', 'clone', '--quiet', '--shared', '--no-checkout', module.path, work])
        git(work, 'checkout', '--quiet', '--detach', revision)
        for path in selected:
            log(f'kernel: patch {path.name}')
            try:
                git(work, 'apply', str(path))
            except Error as error:
                shutil.rmtree(work)
                raise Error(f'XNU patch {path}: {error}') from error
        # A fresh clone lacks the public headers newer xnu omits (TrustCache among them); archives compile against it before the kernel build.
        run(['python3', ctx.tree / 'scripts/prepare-xnu-source.py'], cwd=ctx.tree)
        stamp.write_text(json.dumps(signature, indent=2) + '\n')
    selection = json.dumps(signature, indent=2) + '\n'
    (ctx.work / 'xnu-inputs.json').write_text(selection)
    (cache / 'xnu-patch-selection.json').write_text(selection)
    patch_list = ctx.work / 'xnu-patches.list'
    patch_list.write_text(''.join(str(path) + '\n' for path in selected))
    (cache / 'xnu-patches.list').write_text(patch_list.read_text())
    return patch_list
