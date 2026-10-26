"""Put files into the Moto's iOS root through the drop zone (bsd/dev/ocean_sdhci.c).

    python ocean-drop.py ADB LOCAL=/device/path[:mode] ...

Packs the files into the drop-zone format (header "OCEANDP1", one 512-byte
entry per file, data sector-aligned, CRC32 over entries and data), pushes it
to TWRP and writes it into the 256 MiB drop zone of userdata, which lies after
the 20 GiB iOS volume and before the log area: nothing of either is touched.
Reads the zone back and compares. On the next iOS boot the kernel checks the
CRC, writes every file through the VFS and marks the zone done.

The phone must be in TWRP. Device paths must be absolute, in existing
directories. Mode defaults to 0755.
"""
import hashlib
import os
import struct
import subprocess
import sys
import tempfile
import zlib

SERIAL = "ZY326CHZKD"
USERDATA_FIRST = 15826944               # partition start, in disk sectors
HFS_LAST = 57769983                     # last sector of the 20 GiB iOS volume
DROP_FIRST = 58720256                   # OCEAN_DROP_FIRST
DROP_SECTORS = 256 << 11                # 256 MiB
LOG_FIRST = 122142686 + 1 - (1 + (4 << 20) // 512)
assert HFS_LAST < DROP_FIRST and DROP_FIRST + DROP_SECTORS <= LOG_FIRST


def pack(files):
    entries, data = [], bytearray()
    for local, path, mode in files:
        blob = open(local, "rb").read()
        assert path.startswith("/") and len(path.encode()) < 256, path
        entries.append(struct.pack("<256sIIQQ", path.encode(), mode, 0, len(data), len(blob)).ljust(512, b"\0"))
        data += blob + b"\0" * (-len(blob) % 512)
    body = b"".join(entries) + bytes(data)
    crc = zlib.crc32(body) & 0xffffffff
    header = struct.pack("<8sIIQII", b"OCEANDP1", 1, len(files), len(data), crc, 0).ljust(512, b"\0")
    image = header + body
    assert len(image) // 512 <= DROP_SECTORS
    return image, crc


def adb(adb_path, *args, data=None):
    return subprocess.run([adb_path, "-s", SERIAL, *args], check=True, capture_output=True, input=data).stdout


def main(adb_path, specs):
    files = []
    for spec in specs:
        local, _, rest = spec.partition("=")
        path, _, mode = rest.partition(":")
        files.append((local, path, int(mode, 8) if mode else 0o755))
    image, crc = pack(files)
    sha = hashlib.sha256(image).hexdigest()
    for local, path, mode in files:
        print(f"  {path} <- {local} ({os.path.getsize(local)} bytes, mode {mode:o})")
    print(f"drop image: {len(image)} bytes, {len(files)} files, CRC {crc:08x}, sha256 {sha}")

    if adb(adb_path, "shell", "getprop ro.product.device").decode().strip() != "ocean":
        sys.exit("not the Moto in TWRP")
    dev = adb(adb_path, "shell", "readlink -f /dev/block/by-name/userdata").decode().strip()
    size = int(adb(adb_path, "shell", f"blockdev --getsz {dev}").decode().strip())
    seek = DROP_FIRST - USERDATA_FIRST
    if size != 122142686 - USERDATA_FIRST + 1 or seek + len(image) // 512 > size:
        sys.exit(f"unexpected userdata size {size}")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as t:
        t.write(image)
    try:
        adb(adb_path, "push", t.name, "/tmp/ocean-drop.img")
    finally:
        os.unlink(t.name)
    count = len(image) // 512
    adb(adb_path, "shell", f"dd if=/tmp/ocean-drop.img of={dev} bs=512 seek={seek} count={count} conv=notrunc,fsync 2>&1")
    back = adb(adb_path, "shell", f"dd if={dev} bs=512 skip={seek} count={count} 2>/dev/null | sha256sum").decode().split()[0]
    print(f"written to {dev} sectors {seek}..{seek + count - 1}; read back sha256 {back}: "
          f"{'MATCHES' if back == sha else 'DIFFERENT'}")
    if back != sha:
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])
