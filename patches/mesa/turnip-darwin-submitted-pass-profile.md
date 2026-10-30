# Turnip submitted command and attachment records

`turnip-darwin-submitted-pass-profile.patch` records commands as Turnip emits
them and exports the bounded aggregates when their command buffer is submitted.
The capture uses `NativeAdrenoTrace.h` points 65540 through 65543 and argument
keys 39 through 49. Every exported aggregate includes the process, command
buffer, submission and completion IDs assigned by the existing transport.

## Packet counts

The common `tu_cs_emit_pkt7_at` entry records every `CP_WAIT_FOR_IDLE` issued
through a captured command buffer's command streams. It remembers an
`EVENT_WRITE` or `EVENT_WRITE7` header until `tu_cs_emit` receives its first data
word, then records that word's event number. Temporary substreams inherit their
command buffer owner and follow `parent` to combine nested execution conditions.
The record name is the emitting function; the source line distinguishes waits
within that function. Timestamp-copy submissions add their two WFI packets once
per submission.

Point 65540 has arguments pass ID 39, classification 40, emitted count 41 and
estimated executions 42. Classification contains:

| Bits | Meaning |
| --- | --- |
| 0..7 | PM4 opcode |
| 8..15 | Event number for EVENT_WRITE |
| 16..23 | Stream: 0 main, 1 draw, 2 tile store, 3 draw epilogue, 4 suballocated state |
| 24..26 | Applicable render modes: bit 0 binning, bit 1 GMEM, bit 2 sysmem |
| 27 | A predicate or visibility-dependent IB skip makes the estimate an upper bound |
| 32..63 | Source line |

Each main-stream packet is already emitted at its individual tile or pass
location. Draw-stream estimates multiply by actual tile invocations plus one
binning invocation where applicable. Tile stores repeat per emitted tile;
draw epilogues run once per pass. The actual tile count is incremented inside
`tu6_render_tile`, after FDM merging and visibility exclusions. Conditional GPU
execution remains an upper bound. Suballocated state and incomplete pass
estimates use `UINT64_MAX`. The emitted count remains available separately.

Inherited secondary command buffers use their containing primary pass ID.
Secondary command buffers with complete passes retain their own command IDs.
Counts are repeated per submission so reused command buffers remain associated
with the job that executes them.

## Internal passes and resources

Render-pass GPU begin and end records carry pass ID 39. Point 65541 exports
`render_pass_identity` with pass, Metal encoder, internal instance and split
reason, then `render_pass_execution` with pass, emitted tiles, draws and details.
Execution details contain rendered bit 0, sysmem bit 1, binning bit 2, LRZ bit 3,
capture render flags in bits 8..15 and sample count in bits 16..23.

Metal marker 15 sets encoder, instance and split reason immediately before the
actual Vulkan pass begins. Marker 17 retains the frontend's copy-batch and
dependency-barrier counts. The attachment records come from Turnip's actual
attachment load, store, resolve and clear emission functions.

Point 65542 contains pass 39, image handle 46, packed details 47 and image IOVA
48. Details contain operation in bits 0..7, attachment index in 8..15, GMEM
attachment index in 16..23, flags in 24..31 and VkFormat in 32..63.

Operation 0 describes every actual internal-pass attachment, including those
with no load or store. Its flags are load, store, clear, will resolve, stencil
load, stencil store and GMEM, in bits 0 through 6. Operations 1 load, 2 store,
3 resolve and 4 clear describe the commands emitted for GMEM. Their flags are
common/depth, stencil, conditional, force load, fast path and unaligned, in
bits 0 through 5. These operation records are excluded when Turnip chooses
sysmem. Descriptor indices connect resolve destinations to their GMEM source
attachments. Conditional operations describe the emitted commands and may be
skipped by the GPU's tile visibility predicate.

## Bounds and capture control

Each captured command buffer owns at most 2048 packet aggregates, 64 passes,
256 attachment records and 64 secondary references. Open-address lookup avoids
scanning all aggregates for each packet; submission walks only occupied slots.
The allocation shares the existing 16 MiB timestamp/metadata reservation budget.
Point 65543 reports capacity loss or missing command metadata through key 49.
The two transport queues each hold 8192 records. Queue, append and timestamp
budget losses retain their existing separate counters.

The worker reads method 42 once when it registers a new capture generation.
Flags 1 and 2 select GMEM or sysmem; flag 4 enables detailed tile timestamps.
GMEM selection occurs after Turnip's existing legality checks. The default
timestamp mask retains render-pass, binning, sysmem draw, copy and compute
timings. The detailed mask adds GMEM draw, load/store, cache-flush and tile-store
timings. Packet and attachment aggregates are collected in both modes.
