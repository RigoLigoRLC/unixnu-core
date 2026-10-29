# Darwin Turnip GPU capture

`patches/mesa/turnip-darwin-perfetto-capture.patch` adds a bounded consumer to
Mesa u_trace. `NativeAdrenoTrace.h` comes from the selected kernel ABI directory.
The SM-T733 resolved driver directory is a symlink to the device repository,
so both ABI headers enter the same include directory. A Darwin build whose
kernel ABI lacks the trace header keeps the disabled callback implementations.

The transport thread polls capture state every 10 ms and registers one producer
for each active generation. It sends at most eight 176-byte events per IOKit
call. GPU and Metal callbacks append to a 2048-event CPU queue. Each device
accepts at most 8192 GPU trace events per generation and 64 recorded primary
command buffers awaiting submission. Timestamp allocation uses 64-entry chunks.
Overflow increments the explicit dropped count. Capture stop closes admission,
drains submitted u_trace work, sends remaining records, and ends the producer.
A three-second drain timeout reports an incomplete producer.

The A6xx timestamp command is Mesa's `CP_EVENT_WRITE(RB_DONE_TS)`. Mesa waits for
the native completion receipt before reading the timestamp BO. The conversion
uses integer quotient and remainder at 19.2 MHz. A missing timestamp or failed
completion wait marks the event invalid. No new CPU register access occurs.

The default points include render pass, binning, sysmem/tile draw, compute,
copy/clear, GMEM load/store, main-stream cache flushes, and the final tile store
IB. Individual draw timing stays disabled. GMEM load/store reuse Mesa's render
pass timestamp cloning. During capture, A6xx performs the existing tile-tail
WFI before that clone, then emits the clone's WAIT_FOR_ME and CP_MEMCPY. The
move crosses only the timestamp-copy commands; draw, final store, and the tile
render-end marker retain their ordering. Outside capture the original command
sequence remains. The instrumentation event records encoded timestamp,
CP_MEMCPY, WAIT_FOR_ME, and additional WFI dword counts. These counters describe
capture commands; they do not measure shader or cache execution time.

Each command-buffer recording receives a process-wide monotonically increasing
ID. Metal metadata converts its Vulkan handle to that ID. The submit event
associates the recording ID with Turnip's submission number plus one and the
kernel completion receipt. Execute-secondary events associate secondary IDs
with the primary. Begin and end GPU events share point, name, and recording ID.
The shared ABI header lists Turnip point and argument IDs. Metal metadata uses
point IDs 1 through 7, argument key `point * 16 + argument_index`, and source
flags in event flags bits 16 through 31.

The host owns Perfetto protobuf encoding and GPU/CPU clock alignment. GPU
intervals represent completed render-backend timestamps; subtraction between
neighboring stages alone does not identify a pure wait interval.
