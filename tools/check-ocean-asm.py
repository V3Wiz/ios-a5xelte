"""Check actual Mach-O driver instructions, not just source or banner strings."""
import struct
import sys
from pathlib import Path

def member(archive, wanted):
    data = Path(archive).read_bytes()
    assert data[:8] == b'!<arch>\n'
    pos = 8
    while pos + 60 <= len(data):
        header = data[pos:pos + 60]
        size = int(header[48:58])
        name = header[:16].decode().strip().rstrip('/')
        body = data[pos + 60:pos + 60 + size]
        if name.startswith('#1/'):
            count = int(name[3:])
            name = body[:count].rstrip(b'\0').decode()
            body = body[count:]
        if name == wanted:
            return body
        pos += 60 + size + size % 2
    raise AssertionError('Missing ' + wanted)

def text_section(data):
    assert struct.unpack_from('<I', data)[0] == 0xfeedfacf
    pos = 32
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        cmd, size = struct.unpack_from('<II', data, pos)
        if cmd == 0x19:
            for n in range(struct.unpack_from('<I', data, pos + 64)[0]):
                section = pos + 72 + n * 80
                if data[section:section + 16].rstrip(b'\0') == b'__text':
                    length, offset = struct.unpack_from('<QI', data, section + 40)
                    return data[offset:offset + length]
        pos += size
    raise AssertionError('Missing __text')

code = text_section(member(sys.argv[1], 'ocean_sdhci.o'))
words = list(struct.unpack('<' + 'I' * (len(code) // 4), code))
sequence = [0xd53b4220, 0xd5034fdf, 0xd5087800,
            0xd5033fdf, 0xd5387400, 0xd51b4220]
masks = [0xffffffe0, 0xffffffff, 0xffffffe0,
         0xffffffff, 0xffffffe0, 0xffffffe0]
audits = sum(all((words[i+j] & masks[j]) == op for j, op in enumerate(sequence))
             for i in range(len(words) - 5))
timers = sum(words[i] == 0xd5033fdf and (words[i+1] & 0xffffffe0) == 0xd53be020
             for i in range(len(words) - 1))
assert audits >= 1, f'No complete DAIF/AT/ISB/PAR/restore sequence: {audits}'
assert timers >= 1, f'No serialized physical counter read: {timers}'
print(f'Compiled ocean_sdhci: {audits} complete mapping audits, {timers} counter reads')
