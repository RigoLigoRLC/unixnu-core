# AdrenoMetal

AdrenoMetal publishes a Metal device through `MTLAddDevice`. It translates AIR through metal2vulkan, compiles SPIR-V with Turnip, and submits work to [Adreno740](/drivers/adreno740). Firmware, power votes and display integration come from the board.

## Rendering and interfaces

| Area | Behavior |
| --- | --- |
| MSAA policy | All clients use one sample for textures, pipelines and render passes by default. Resolve targets receive the rendered output; load and store-and-resolve preserve the source. `NATIVE_METAL_SINGLE_SAMPLE=0` preserves a process's requested sample counts; `1` forces single-sample rendering. |
| Heap resources | Buffer and texture `makeAliasable` release their heap ranges. |
| Texture channels | Texture descriptors and views preserve all four swizzles, including explicit zero and one. |
| Copies and raster state | Blits cover the requested mip and slice ranges. Viewport and scissor setters forward every entry, up to 16. |
| Compressed input | A zero-length no-copy compressed texture infers its DroidVM layout size and retains the owner's deallocator through use. |
| Functions | Function constant dictionaries expose names, indices and types. Function and compute-pipeline completion selectors report results. `specializedName` is the exported name; source lookup retains the original definition. |
| Constant tables | Dynamically indexed constant tables larger than 4 KiB use shared constant storage. Constant pointer casts and GEP expressions retain their offsets. |
| Memory accounting | Device allocation totals include pooled, dedicated and imported backing. Texture sizes come from their backing allocation. The recommended working set is RAM / 4, capped at 2 GiB. |
| Queue capacity | `newCommandQueueWithMaxCommandBufferCount:` uses the runtime's outstanding-buffer limit. Uncommitted destruction releases a slot; completion releases it after handlers return. |

A render pass that fails encoding returns an encoder and reports a command-buffer error. This supports callers that cache encoder methods.


Unused owned image backing is reused by pooled and dedicated images. Extra spares share a 256 MiB budget per device and expire after ten seconds. Plain backing of at least 256 KiB is retired on the existing room worker, with a 128 MiB queue limit. An allocation failure releases queued backing before retrying. Imported memory and owner callbacks keep their release ordering. First-use allocations can still prepare new pages.

## Cache and priority

Clients with the same UID use `Library/Caches/org.unixnu.metal` under their account home when writable. Sandbox restrictions select a private cache. `NATIVE_METAL_SHARED_CACHE_DIR` selects another shared root; an empty value disables sharing. The cache covers Apple frontend output, runtime artifacts and Turnip IR3. Concurrent pack imports use distinct temporary files. Pipeline journals are per process.

Logical Metal queues share one Vulkan queue and kernel queue per process. The frontend forwards the most urgent **current** request among live queues. Lowering or destroying a queue removes its boost. Getters report each queue's own request; setters report backend acceptance. The kernel chooses foreground or background priority from the task's GPU role. Priority policy does not use process names.

## Build and checks

From the resolved iOS 27 target tree:

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
python3 scripts/build-turnip-darwin.py --target ios27
python3 scripts/build-adreno-metal-plugin.py --target ios27
python3 scripts/check-native-metal-frontend-host.py
```

The normal build applies the recorded translator and Turnip patches and enables Mesa's disk shader cache. Host checks cover rendered pixels, resolves, resource aliasing, swizzles, copies, callbacks, queue limits and priority aggregation. Hardware qualification covers frame pacing and preemption under concurrent clients.

See the [GPU adaptation procedure](/porting/gpu) for staging and board inputs.

Frame diagnostics retain allocation, command, completion and GPU/display timing. Pixel capture is disabled. See [GPU frame diagnostics](/porting/gpu-diagnostics).

`sheng-wallpaper-freeze=1` isolates wallpaper rendering. A Poster renderer retains its first successfully drawn and stored IOSurface output of at least two million pixels, then parks later command buffers before runtime submission. Parked buffers remain committed and unscheduled; their owners and queue leases stay retained. Previously submitted work completes normally. PosterBoard, backboardd and other clients continue submitting. The mode defaults to off.

Detailed latency records identify slow encoder calls, callback invoke addresses and resource destruction. Kernel sampling of the render, encode and completion threads correlates upstream waits.
