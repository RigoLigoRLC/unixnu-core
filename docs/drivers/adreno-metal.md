# AdrenoMetal

Start with the [adaptation procedure](/porting/gpu) for board inputs, source changes, build integration and verification order.

AdrenoMetal provides the Metal frontend through metal2vulkan and Turnip. It
publishes a device through `MTLAddDevice`, translates AIR, and submits work to
the kernel GPU interface.

| Field | Value |
| --- | --- |
| Repository | [UniXNU/AdrenoMetal](https://github.com/UniXNU/AdrenoMetal) |
| Implementation | A740/SM8550 graphics stack and the selected OS ABI |
| Dependencies | Adreno740, Turnip, metal2vulkan, IOGPUFamily and IOSurface interfaces |
| Board inputs | Firmware, power policy, memory layout, display integration |
| Verified device | sheng |
| Runtime plugin | `NativeAdrenoMetal` |

sheng runs the GPU-composited desktop. Exported pipeline caches are reused across
boots. The render server primes every Metal library of the OS image while the
desktop is idle: the payload carries the list (`NativeAdrenoMetal.primelist`) and
a copy of the cryptex QuartzCore library, which the render server's sandbox
cannot reach. The idle desktop submits about 6 command buffers per 250 ms at
120 Hz, so priming waits only above 8. The PR log row shows its progress; all
162 libraries are primed on sheng. With the list present the render server does
not scan directories, and each library is read only while the display is quiet.

A render pass that cannot be encoded still returns an encoder, and its command
buffer is refused: RenderBox caches encoder methods and cannot take nil. The first problem of each process is written to the driver's
per-process text line from the thread that hit it.

The selected board supplies the same `NativeAdrenoABI.h` to Turnip and the plugin.
Turnip reads the reported ABI version and sends 16 indirect buffers in a 416-byte
record for version 1, or 128 in a 3104-byte record for version 2. The diagnostic
mailbox retains the 16-buffer record. Host-import pages remain retained until the
kernel acknowledges removal of their GPU mapping.

On a Darwin device advertising cached coherent memory, Turnip exposes that memory
as the default type for resources, heaps and internal command storage. CPU maps
use write-back caching, and the kernel selects GPU mapping attributes from the
allocation or imported pages. Metal Shared storage, WriteCombined hints, Private
resources and eagerly allocated Memoryless attachments prefer cached coherent
memory on unified-memory GPUs. The frontend's device query recognizes hardware
coherence and kernel-managed visibility; either removes IOSurface flush-range
collection and userspace cache operations from submission and completion.

The SM7325 adaptation passes resource declarations, render memory barriers and
fence stages through the frontend into metal2vulkan. Encoding accumulates access
summaries, and submission exports GPU writes to the CPU only for allocations
with CPU consumers. Turnip's asynchronous Darwin extension submits timeline
dependencies and output points to the kernel scheduler; CPU waits sleep on the
requested point. Display holds a read of the IOSurface backing until DPU has
switched to its replacement.

The `unixnu-sm-t733` branch keeps these submission and synchronization changes
with the system BGRA8 sRGB format policy. The `unixnu-sm-t733-apple3` branch adds
the Apple3 frontend, compiler and format implementations. Each device branch
pins its corresponding core, SoC and Metal revisions.

The SM7325 bridge uses metal2vulkan development commit
`624bab3918de5b978e1101517abca2b4fa426565` and the ordered patches in
`AdrenoMetal/bridge/patches/series`. The new runtime's fence stages retain the
local resource visibility and cached coherent memory policies.

Device answers are cached by selector and argument. The frontend disables no-copy
rebind replay logs. Host-page textures use their imported memory directly when
the runtime accepts the layout. Turnip uses draw loads and 2D stores for linear
imported attachments whose dimensions do not fill complete GMEM blocks. Those
transfers cover the valid texels within the owner's row pitch.

Frame trace and pipeline journal files default off through
`NATIVE_ADRENO_FRAME_TRACE=0` and `NATIVE_ADRENO_PIPELINE_JOURNAL=0`. Periodic
in-memory statistics remain available. Frontend and host-import release errors
each print at most 32 entries per process.

```sh
python3 scripts/build-turnip-darwin.py --target ios
python3 scripts/build-adreno-metal-plugin.py
```

See [Adreno740](/drivers/adreno740) for the runtime path, staging commands, and checks.
