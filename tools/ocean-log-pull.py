#!/usr/bin/env python3
"""Pull the Ocean persistent console log ("oceanlog") from TWRP.

The kernel (patch 0317) writes its console ring to the last 4 MiB + 512 B
of the userdata partition. Run with the Moto in TWRP (temporarily booted),
userdata unmounted or not, it only reads:

    python tools/ocean-log-pull.py ADB_PATH OUT.txt
"""
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

SERIAL = "ZY326CHZKD"
DEV = "/dev/block/mmcblk0p64"
USERDATA_FIRST = 15826944
USERDATA_LAST = 122142686
RING = 4 << 20
SECTORS = 1 + RING // 512
LOG_FIRST = USERDATA_LAST + 1 - SECTORS


def main(adb, out):
    def run(*args):
        return subprocess.run([adb, "-s", SERIAL, *args], check=True, capture_output=True).stdout

    if run("shell", "getprop ro.product.device").decode().strip() != "ocean":
        raise SystemExit("not the Moto ocean")
    start = int(run("shell", "cat /sys/class/block/mmcblk0p64/start").decode())
    if start != USERDATA_FIRST:
        raise SystemExit(f"unexpected userdata start {start}")
    skip = LOG_FIRST - USERDATA_FIRST
    run("shell", f"dd if={DEV} of=/tmp/oceanlog.bin bs=512 skip={skip} count={SECTORS} 2>/dev/null")
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "oceanlog.bin"
        run("pull", "/tmp/oceanlog.bin", str(local))
        data = local.read_bytes()
    run("shell", "rm /tmp/oceanlog.bin")
    if len(data) != SECTORS * 512:
        raise SystemExit(f"short read: {len(data)} bytes")
    magic, version, size, total, seq = struct.unpack_from("<8sIIQQ", data, 0)
    if magic != b"OCEANLG1" or version != 1 or size != RING:
        raise SystemExit("no Ocean log header (the kernel never flushed one)")
    ring = data[512:]
    if total <= size:
        text = ring[:total]
    else:
        cut = total % size
        text = ring[cut:] + ring[:cut]
    Path(out).write_bytes(text.replace(b"\0", b""))
    print(f"{out}: {len(text)} bytes (total {total}, flush #{seq})")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
