# One submission PM4 capture

The Darwin queue backend starts one worker per process. The worker obtains the
immutable shader capture prefix and publishes `s<session>_pm4_status.json`. A
disabled shader session leaves PM4 capture disabled. The helper publishes the
fixed `s<session>_pm4_request.txt` containing `1 <session> <target_submit>\n`.
The worker accepts one request, allocates the bounded snapshot, and arms it for
60 seconds. It retains the request file as the session's one-request record.

Target zero selects the next nonempty submission after arming. Other values
select the process-wide PM4 submission serial shown as `last_submit` in status.
The serial increments after resource collection for each nonempty submission.
It differs from the per-device Mesa `submit_count` and native completion receipt;
the result records each identifier separately, along with device index, queue ID
and primary command-buffer recording IDs. A missed target produces an explicit
`target-already-passed` result.

The submit thread follows top-level IBs, CP_INDIRECT_BUFFER and
CP_SET_DRAW_STATE references in CPU mappings already retained for submission.
It copies the referenced command ranges before the kernel call. Ordinary
command-stream allocations are eligible. An explicitly referenced command range
in another driver-internal GPU-read-only allocation is also eligible, allowing
pipeline state commands without copying the surrounding shader allocation.
Texture, application-resource and arbitrary shader contents remain excluded.
CP_LOAD_STATE6 external addresses are recorded with address-only coverage;
their data extent is not inferred from an address.

The RD buffer is limited to 16 MiB, retained resource metadata to 4096 objects,
IB/state references and saved ranges to 2048 each, and command recording IDs to
256. Packet traversal is limited to 16 MiB of command bytes. The manifest records
limit failures, missing mappings/resources, malformed packets and unsaved
references. Resource allocation flags identify command buffers writable by the
GPU; their snapshot represents bytes before this submission executes. Packet
traversal records references rather than execution counts or predicate outcomes.

The kernel result and completion receipt are published to the worker with the
snapshot. The worker writes uncompressed Mesa RD sections and JSON through
temporary files followed by atomic rename. It never reads a BO after publication.
All file reads and writes run on that worker. The capture adds no GPU wait, BO
mapping, process stop, resource-table scan or file operation under `bo_mutex`.
The existing submit path owns BO references and GPU execution.

Output files are `s<session>_pm4-<serial>.rd` and `.json`. The manifest's
`references` identifies kind 0 top-level IB, 1 nested IB, 2 draw-state commands,
and 3 external state address, with the referring packet address. Each saved
range includes its RD byte offset. Host decoding must report missing command
references and metadata limits even when cffdump produces text successfully.
