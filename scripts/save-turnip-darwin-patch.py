#!/usr/bin/env python3
"""Record the Darwin backend at its declared position in the Mesa patch sequence.

The generator applies preceding patches to pinned Mesa for the diff's base. It
copies the current Darwin files and reverses following patches in reverse order
before recording the difference. The working Mesa checkout remains unchanged.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MESA = ROOT / '.cache/mesa-work'
NEW = ['src/freedreno/vulkan/tu_knl_darwin.cc']
MINE = ['meson.options', 'src/freedreno/vulkan/meson.build', 'src/freedreno/vulkan/tu_knl.cc',
        'src/freedreno/vulkan/tu_knl.h', 'src/freedreno/vulkan/tu_device.cc',
        'src/freedreno/vulkan/tu_device.h',
        'src/vulkan/wsi/wsi_common_metal_layer.m', 'src/util/cache_ops_aarch64.c'] + NEW
OUT = ROOT / 'patches/mesa/turnip-darwin-kmd.patch'
patches = json.loads((ROOT / 'scripts/data/adreno-compiler-inputs.json').read_text())['patches']
position = patches.index(OUT.relative_to(ROOT).as_posix())
preceding = patches[:position]
following = patches[position + 1:]
includes = ['--include=' + path for path in MINE]


def git(tmp, *args, check=True):
    return subprocess.run(['git', '-c', 'user.email=a@b', '-c', 'user.name=n', *args], cwd=tmp, check=check,
                          capture_output=True, text=True).stdout


tmp = Path(tempfile.mkdtemp(dir=ROOT / '.cache'))
try:
    git(tmp, 'init', '-q')
    for f in MINE:
        if f in NEW:
            continue
        (tmp / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp / f).write_bytes(subprocess.run(['git', 'show', 'HEAD:' + f], cwd=MESA, check=True, capture_output=True).stdout)
    git(tmp, 'add', '-A')
    git(tmp, 'commit', '-q', '-m', 'base')
    for patch in preceding:
        git(tmp, 'apply', '--allow-empty', *includes, str(ROOT / patch))
    git(tmp, 'add', '-A')
    git(tmp, 'commit', '-q', '-m', 'preceding patches', '--allow-empty')
    for f in MINE:
        (tmp / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(MESA / f, tmp / f)
    for patch in reversed(following):
        git(tmp, 'apply', '--reverse', '--allow-empty', *includes, str(ROOT / patch))
    for f in NEW:
        git(tmp, 'add', '-N', f)
    OUT.write_text(git(tmp, 'diff', '--binary', '--no-ext-diff', '--abbrev=7'))
finally:
    shutil.rmtree(tmp)
print('wrote', OUT.relative_to(ROOT), len(OUT.read_text().splitlines()), 'lines')
