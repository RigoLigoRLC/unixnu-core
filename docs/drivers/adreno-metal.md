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

Device answers are cached by selector and argument. The frontend disables no-copy
rebind replay logs. A padded render target aliases its buffer only when the height
is divisible by four, its width rounded to 16 texels fits each row pitch, and the
last rounded row fits the allocation. Other padded targets use a shadow image.

Frame trace and pipeline journal files default off through
`NATIVE_ADRENO_FRAME_TRACE=0` and `NATIVE_ADRENO_PIPELINE_JOURNAL=0`. Periodic
in-memory statistics remain available. Frontend and host-import release errors
each print at most 32 entries per process.

```sh
python3 scripts/build-turnip-darwin.py --target ios
python3 scripts/build-adreno-metal-plugin.py
```

See [Adreno740](/drivers/adreno740) for the runtime path, staging commands, and checks.
