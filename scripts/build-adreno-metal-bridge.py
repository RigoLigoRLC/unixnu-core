#!/usr/bin/env python3
"""Build the native Metal bridge (drivers/AdrenoMetal/bridge/NativeMetalBridge.rs): the pinned metal2vulkan runtime behind a C ABI, as a static library.

--target ios (default) cross-builds for arm64-apple-ios17.0, --target host for the macOS host simulation. The runtime's own example library
(runtime_examples.ll) and its function-constant fixture are assembled to AIR with llvm-as and embedded for the self-tests. Only generated build files hold local paths; nothing here
is committed. Output: build/adreno-metal-bridge/<target>/libadreno_metal_bridge.a"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from mesa_patch_identity import validate_recorded_patches

ROOT = Path(__file__).resolve().parents[1]
PIN = json.loads((ROOT / 'scripts/data/gpu-metal-vulkan-inputs.json').read_text())['translator']['commit']
SOURCE = ROOT / '.cache/gpu-reference/metal2vulkan'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--target', choices=['ios', 'host'], default='ios')
parser.add_argument('--manifest-only', action='store_true',
                    help='write build/adreno-metal-bridge/Cargo.toml (patched source, fixtures) and stop before cargo, for `cargo fetch`')
args = parser.parse_args()
if subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() != PIN:
    raise SystemExit('Translator revision differs from the qualified source pin')
patch_directory = ROOT / 'drivers/AdrenoMetal/bridge/patches'
patch_names = [line.split('#', 1)[0].strip()
               for line in (patch_directory / 'series').read_text().splitlines()]
PATCHES = [patch_directory / name for name in patch_names if name]
source_status = subprocess.check_output(
    ['git', '-C', str(SOURCE), 'status', '--porcelain', '--untracked-files=all'], text=True)
if not source_status:
    for patch in PATCHES:
        subprocess.run(['git', '-C', str(SOURCE), 'apply', str(patch)], check=True)

# Sequential patches may update the same file. Reversing them in a temporary
# copy must recover the pinned source bytes before the compiler consumes it.
validate_recorded_patches(ROOT, SOURCE, {'patches': [str(patch) for patch in PATCHES]})
expected = ''.join(patch.read_text() for patch in PATCHES)
out = ROOT / 'build/adreno-metal-bridge'
out.mkdir(parents=True, exist_ok=True)
llvm_as = next((p for p in ['/opt/homebrew/opt/llvm/bin/llvm-as', shutil.which('llvm-as') or ''] if p and Path(p).exists()), None)
if not llvm_as:
    raise SystemExit('llvm-as (LLVM 21 or newer) is required to assemble the fixture')
air = out / 'runtime_examples.air'
subprocess.run([llvm_as, '-o', air, SOURCE / 'crates/metal2vulkan-validation/fixtures/public/examples/runtime_examples.ll'], check=True)
fc_air = out / 'function_constant.air'
subprocess.run([llvm_as, '-o', fc_air, SOURCE / 'crates/metal2vulkan-validation/fixtures/public/kernel_function_constant_gate_fold.ll'], check=True)
manifest = out / 'Cargo.toml'
manifest.write_text('\n'.join([
    '[package]', 'name = "adreno-metal-bridge"', 'version = "0.1.0"', 'edition = "2024"', 'rust-version = "1.98"', '[workspace]',
    '[lib]', 'crate-type = ["staticlib"]', 'path = ' + json.dumps(str(ROOT / 'drivers/AdrenoMetal/bridge/NativeMetalBridge.rs')),
    '[dependencies]',
    'metal2vulkan = { path = ' + json.dumps(str(SOURCE / 'crates/metal2vulkan')) + ', features = ["ash"] }',
    'metal2vulkan-runtime = { path = ' + json.dumps(str(SOURCE / 'crates/metal2vulkan-runtime')) + ' }',
    'ash = { version = "0.38", default-features = false }',
    'libc = "0.2"',
    # The runtime hashes every shader-cache key and entry; without asm, sha2 0.10 on aarch64 is the portable software rounds, not the
    # ARMv8 SHA-256 instructions every target CPU has (cpufeatures answers sha2 true on Apple platforms).
    'sha2 = { version = "0.10", features = ["asm"] }',
    '[profile.release]', 'panic = "unwind"', 'debug = 1',
    'lto = "fat"', 'codegen-units = 1', '',
]))
if args.manifest_only:
    print(manifest)
    raise SystemExit(0)
triple = 'aarch64-apple-ios' if args.target == 'ios' else 'aarch64-apple-darwin'
# The translator source the runtime is built from (its pin and recorded patches), which keys the shader cache: shader priming keeps what it
# finished while this stays the same (PrimeShaders.h).
runtime_id = hashlib.sha256((PIN + '\n' + expected).encode()).hexdigest()[:32]
env = dict(os.environ, NMB_RUNTIME_ID=runtime_id, NMB_FIXTURE_AIR=str(air), NMB_FC_AIR=str(fc_air), IPHONEOS_DEPLOYMENT_TARGET='17.0', MACOSX_DEPLOYMENT_TARGET='14.0')
target_dir = ROOT / 'build/m2v-target'
log = out / ('build-%s.log' % args.target)
with log.open('w') as stream:
    result = subprocess.run(['cargo', '+1.98.0', 'build', '--release', '--manifest-path', manifest, '--target', triple,
                             '--target-dir', target_dir], env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=1800)
if result.returncode:
    raise SystemExit(log.read_text()[-6000:])
library = target_dir / triple / 'release/libadreno_metal_bridge.a'
final = out / args.target / 'libadreno_metal_bridge.a'
final.parent.mkdir(exist_ok=True)
shutil.copyfile(library, final)
print('PASS: native Metal bridge static library for %s (%d bytes); translator %s' % (args.target, final.stat().st_size, PIN[:12]))
