#!/usr/bin/env python3
"""Build the herolte (SM-G930F, Exynos 8890) ADT for the HEROLTE XNU config.

Derived from mkadt_a5xelte.py. Addresses come from exynos8890.dtsi and the
phone's own BOOT DTB (see docs/herolte-bringup.md); none is device-verified
under XNU yet. Storage is the Exynos 8890 UFS (/herolte-ufs); no touch or
GPU nodes: the A5 drivers for those target Exynos 7580 hardware.
"""
import argparse
import os
from pathlib import Path

import adt
import mkadt

DRAM_BASE = 0x90000000      # isolated XNU window, free in the herolte DTB
DRAM_SIZE = 0x20000000      # 512 MiB, ends below TIMA at 0xb1000000
SOC_BASE = 0x10000000       # arm-io ranges base; child regs are relative
FB_BASE, FB_WIDTH, FB_HEIGHT = 0xe2a00000, 1440, 2560


def set_prop(node, name, value):
    for i, (key, flags, _) in enumerate(node.props):
        if key == name:
            node.props[i] = (key, flags, value)
            return
    node.props.append((name, 0, value))


def child(node, name):
    for candidate in node.children:
        if candidate.prop('name') == mkadt.cstr(name):
            return candidate
    raise ValueError(f'missing donor ADT node {name}')


def build():
    root = mkadt.build(seed=os.urandom(64), qemu=True)
    # The userland is the iPhone X IPSW (iPhone10,3 / D22AP), like the donor:
    # compatible[0] is hw.model/hw.target, model is hw.machine. The donor's
    # /buttons stays (home-button-type 2: gesture navigation, no Home key).
    # 'samsung,a5xelte' keeps the shared SweetPlatformExpert IONameMatch.
    set_prop(root, 'compatible', mkadt.cstr('D22AP') + mkadt.cstr('iPhone10,3') +
             mkadt.cstr('samsung,a5xelte') + mkadt.cstr('samsung,herolte') +
             mkadt.cstr('samsung,exynos8890') + mkadt.cstr('AppleARM'))
    chosen = child(root, 'chosen')
    set_prop(chosen, 'dram-base', mkadt.u64(DRAM_BASE))
    set_prop(chosen, 'dram-size', mkadt.u64(DRAM_SIZE))
    set_prop(chosen, 'firmware-version', mkadt.cstr('herolte-entry'))
    set_prop(chosen, 'system-firmware-version', mkadt.cstr('herolte-entry'))
    cpus = child(root, 'cpus')
    cpu0 = child(cpus, 'cpu0')
    # S-Boot starts on the Cortex-A53 "Apollo" cluster: MPIDR 0x100..0x103.
    # The Mongoose cluster (MPIDR 0..3) is left out until SMP works.
    set_prop(cpu0, 'compatible', mkadt.cstr('arm,cortex-a53') + mkadt.cstr('ARM,v8'))
    set_prop(cpu0, 'reg', mkadt.u32(0x100))
    set_prop(cpu0, 'timebase-frequency', mkadt.u32(26000000))
    for logical in range(1, 4):
        cpus.children.append(mkadt.node(f'cpu{logical}', [
            ('device_type', mkadt.cstr('cpu')),
            ('compatible', mkadt.cstr('arm,cortex-a53') + mkadt.cstr('ARM,v8')),
            ('reg', mkadt.u32(0x100 | logical)),
            ('cpu-id', mkadt.u32(logical)),
            ('cluster-id', mkadt.u32(0)),
            ('cluster-type', mkadt.u32(0)),
            ('die-cluster-id', mkadt.u32(0)),
            ('cluster-core-id', mkadt.u32(logical)),
            ('l2-cache-id', mkadt.u32(0)),
            ('l3-cache-id', mkadt.u32(0)),
            ('state', mkadt.cstr('stopped')),
            ('timebase-frequency', mkadt.u32(26000000)),
            ('clock-frequency', mkadt.u32(1586000000)),
            ('bus-frequency', mkadt.u32(100000000)),
            ('memory-frequency', mkadt.u32(1794000000)),
            ('peripheral-frequency', mkadt.u32(26000000)),
            ('fixed-frequency', mkadt.u32(26000000)),
        ]))
    arm_io = child(root, 'arm-io')
    set_prop(arm_io, 'device_type', mkadt.cstr('herolte-io'))
    set_prop(arm_io, 'compatible', mkadt.cstr('samsung,exynos8890-io') +
             mkadt.cstr('arm-io'))
    set_prop(arm_io, 'ranges', mkadt.u64(0, SOC_BASE, 0xf0000000))
    arm_io.children = [n for n in arm_io.children if n.prop('name') == mkadt.cstr('wdt')]
    # GIC-400: distributor 0x11001000, CPU interface 0x11002000.
    arm_io.children.append(mkadt.node('gic', [
        ('compatible', mkadt.cstr('arm,cortex-a15-gic')),
        ('interrupt-controller', mkadt.cstr('master')),
        ('virtual-timer-intid', mkadt.u32(27)),
        ('reg', mkadt.u64(0x11001000 - SOC_BASE, 0x1000, 0x11002000 - SOC_BASE, 0x1000)),
    ]))
    arm_io.children.append(mkadt.node('disp0', [
        ('device_type', mkadt.cstr('display-subsystem')),
        # AppleCLCD (SweetFramebuffer.cpp) matches 'samsung,a5xelte-display'
        # in KernelConfigTables.cpp; without it SpringBoard sees no main display.
        ('compatible', mkadt.cstr('samsung,a5xelte-display') +
         mkadt.cstr('samsung,herolte-display')),
        ('canvas-width', mkadt.u32(FB_WIDTH)),
        ('canvas-height', mkadt.u32(FB_HEIGHT)),
    ]))
    root.children = [n for n in root.children if n.prop('name') not in
                     (mkadt.cstr('sweet-fbcon'), mkadt.cstr('sweet-ufs'))]
    # Exynos 8890 UFSHCI (exynos8890.dtsi ufs@0x155A0000): standard HCI at
    # +0, vendor HCI +0x100, UNIPRO +0x1000, UFS protector +0x2000. Absolute
    # address, read by bsd/dev/herolte_ufs.c (ufsprobe=1, rd=ufsroot0).
    root.children.append(mkadt.node('herolte-ufs', [
        ('reg', mkadt.u64(0x155A0000, 0x3000)),
    ]))
    # pe_serial.c looks this node up by name for the kprintf console.
    root.children.append(mkadt.node('a5xelte-fbcon', [
        ('reg', mkadt.u64(FB_BASE, FB_WIDTH * FB_HEIGHT * 4)),
        ('width', mkadt.u32(FB_WIDTH)),
        ('height', mkadt.u32(FB_HEIGHT)),
        ('stride', mkadt.u32(FB_WIDTH * 4)),
    ]))
    return root


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    blob = adt.serialize(build())
    args.output.write_bytes(blob)
    print(f'{args.output}: {len(blob)} bytes')
