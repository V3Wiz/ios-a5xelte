# A5XELTE GPU port: measured boundary and implementation order

Status: source audit and patch `0125` resource service linked into the A5XELTE
Mach-O. No GPU power-on, Mali register read, GPU job, iOS GPU API bridge, or
GPU-rendered SpringBoard frame has been observed on this port.

## Stage-1 code candidate

Patch `xnu/patches/0125-a5xelte-g3d-resource-service.patch` adds the
`A5XELTEGPU` IOKit service, and `tools/mkadt_a5xelte.py` supplies its
`/arm-io/gpu` nub. The service is disabled unless `a5gpu=1` is explicitly in
the BOOT command line. Even when enabled, it only publishes the exact physical
resource addresses and GIC SPI numbers listed below. It has no MMIO map,
power/clock/regulator writes, GPU interrupt handler or user client. Therefore
it cannot alter framebuffer performance yet. It is a compile and matching
foundation for the next hardware stage, with the existing CPU display path
untouched. `a5gpu=0` (or absent) makes the service decline to start.

The ADT node and IOKit service are separate: seeing `gpu` in the device tree
does not prove the service matched, and seeing `A5XELTE G3D: resource service
registered` would prove only registration. The service compiled and linked,
but has not yet been packaged into BOOT or tested on the phone.

## What currently limits the screen

`xnu/iokit/Kernel/arm/SweetFramebuffer.cpp` is the inherited AppleCLCD bridge.
It describes the CoreAnimation CPU renderer, holds the latest swap record,
copies IOSurface rectangles with the CPU to the DECON scanout buffer at
`0x67000000`, and emits a 60 Hz timer notification. Its default
`sweetfb_hz=10` permitted a panel copy only every sixth timer tick. Patch `0124`
sets an A5XELTE default of 30 Hz and records actual cadence and copy cost;
its phone result is pending. Raising the
limit can improve visible update cadence, but it does not run icon composition
or any other rendering work on the Mali GPU. Measure copy duration and CPU
cost before choosing a higher default; a 1080 x 1920 XRGB8888 full frame is
8,294,400 bytes.

`xnu/iokit/Kernel/arm/SweetSurface.cpp` maps the physical display surface
write-combined and currently accepts accelerator/shared-event methods without
implementing GPU execution or fences. `AppleCLCD` and `IOSurface` service
registration, a visible Apple logo, and an interactive SpringBoard prove a
display/input path, not a GPU path. A `GPU_ID` print would prove only a register
read.

## Hardware reference that already works under Linux

The native Linux device tree at `../../../mainline/exynos7580-a5xelte-gpu.dts`
describes this handset's Mali-T720 MC2 register aperture at `0x11400000`
(size `0x5000`), G3D clock controller at `0x11460000`, and shared PMU at
`0x10460000`. GIC SPIs are JOB 282, MMU 283, GPU 281. G3D uses S2MPU03
BUCK4, an internal Mali MMU, calibrated ASV/OPP voltages, MIF/INT bandwidth,
and TMU2 cooling. The source and device evidence are in
`../../../docs/gpu-native-migration.md` and `../../../docs/gpu-dvfs-native.md`:
Linux Panfrost/Mesa ran actual T720 jobs and Xorg/Qt rendering. Those results
do not transfer to XNU merely by compiling a kernel driver.

The Linux clock/power source
`../../../mainline/drivers/clk-exynos7580-g3d.c` checks PMU status `0x4064`,
configures the G3D domain and clocks in a bounded order, checks bus clocks
before high OPPs, and retains the domain on. This PMU is shared with other
systems. A guessed write, unbounded wait, or read from a power-gated G3D
aperture could stop boot. The native record in
`../../../docs/gpu-dvfs-native.md` also documents an external abort caused by
one invalid CMU offset; avoid a broad register dump on the phone.

## Port stages and proof required at each gate

1. **Baseline and safe identification.** Preserve the current BOOT candidate
   and record CPU usage, AppleCLCD swap/present counts, copied bytes, presentation
   duration and display cadence during the same SpringBoard workload. Keep
   GPU power and GPU MMIO untouched. Confirm the board-local `a5gpu=0`
   fallback in patch `0125` before any active driver test. A read-only PMU status probe may
   run only after the mapping and register offset are checked against the
   Exynos7580 native source; reading Mali `GPU_ID` additionally requires a
   positively confirmed powered/clocked domain. This is diagnostics, not
   acceleration.
2. **G3D resource owner.** Add an A5XELTE-only IOKit platform service with
   exact PMU/CMU/GPU ranges and IRQs. Port the Exynos7580-specific BUCK4,
   power-domain, TOP-parent, divider/gate, ASV/OPP, bandwidth and thermal
   ordering. All transitions need bounded waits, rollback and a boot-argument
   kill switch. First hold a conservative verified OPP; do not copy values
   from another Exynos model. Proof: device readback of the power state,
   clock rate, voltage and the `GPU_ID` product field `0x720` (register bits
   31:16, as decoded by native Panfrost), with no job submission yet.
3. **GPU execution and memory.** Adapt the Midgard T720 register/job/MMU
   behavior from the native Panfrost implementation to XNU-owned wired pages,
   cache maintenance, mapped Mali virtual addresses, JOB/MMU/GPU interrupts,
   completion fences, fault recovery and timeouts. A simple isolated clear or
   triangle into an offscreen buffer must complete and its pixels must match
   a known reference on the physical phone. The GPU's own MMU is used;
   no external SysMMU should be presumed. Treat a kernel driver that only
   reports an ID as an incomplete stage.
4. **iOS rendering integration.** Trace the exact graphics user clients and
   shared-library calls made by this installed iOS build. The private staged
   iPhone 8 Plus root contains `com.apple.Metal` and
   `com.apple.AGXMetalA11`; these are Apple/A11-side components, while this
   phone has Mali-T720. This is an inventory observation, not a claim about
   every possible fallback in the closed framework. The open XNU tree has no
   Mali-compatible Metal/IOAccelerator provider. Linux DRM/GBM/EGL and Mesa's
   Panfrost userland cannot be inserted into iOS CoreAnimation by a kernel
   device match. Implement and validate the iOS-facing surface, command and
   fence contract, or an explicitly selected compositor backend that can
   submit T720 jobs. Preserve a CPU fallback while this is incomplete.
5. **Scanout without a CPU full-frame copy.** Export linear XRGB8888/BGRA
   buffers that both the GPU and the Exynos7580 DECON path can address;
   synchronize GPU completion before scanout and retire old buffers only
   after presentation. Compare the exact color layout, row stride and cache
   behavior with the working Linux DMA-BUF/DECON result. A new logo, a
   faster timer, or a successful `present()` log is not GPU proof.

## Acceptance before saying "GPU accelerated iOS"

- On the phone, known GPU-produced pixels pass readback, and JOB completion
  plus nonzero GPU activity counters identify Mali execution without faults.
- A SpringBoard icon/animation workload submits jobs through the iOS-facing
  path; GPU-produced frames reach DECON with correct colors and fences.
- In a controlled before/after run, record frame intervals, input-to-visible
  latency, CPU time in `present()`, GPU frequency/temperature and dropped
  frames. The unchanged software path remains bootable if the GPU path fails.

The immediate display-pacing work can be built and tested independently of
these GPU stages. It should be reported as a CPU/display improvement, never
as completed Mali acceleration.

External primary references: [Mesa Panfrost driver architecture and Mali
T720 support](https://docs.mesa3d.org/drivers/panfrost.html), [Apple Metal GPU
programming interface](https://developer.apple.com/documentation/Metal).
