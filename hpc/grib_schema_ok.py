#!/usr/bin/env python3
"""Is this GRIB file at the CURRENT message schema?

Exit 0 when the file holds exactly EXPECTED_MESSAGES messages, 1 otherwise;
the count and the expectation are printed either way.

Used by the convert jobs for re-entrancy. Keying the skip on the output file
merely EXISTING is what forced a new output tree at every schema change
(grib -> grib_v2 -> grib_v3): a wider schema written into the old tree would
silently skip every hour already converted at the narrower one. Keying it on
the message count instead makes a re-run across a schema change self-healing.

Deliberately dependency-free -- no eccodes, no numpy, no uv -- so a convert job
can run it with the system python in milliseconds. It walks section 0 of each
message (16 bytes: 'GRIB', reserved, discipline, edition, then the 8-byte total
length) and seeks over the body, so it never reads the data.
"""

import os
import sys


def message_count(path):
    """Number of GRIB messages in the file, by seeking over their headers."""
    n = 0
    size = os.path.getsize(path)
    with open(path, 'rb') as fh:
        while True:
            start = fh.tell()
            if start >= size:
                break
            head = fh.read(16)
            if len(head) < 16:
                raise ValueError(f"{path}: truncated header at offset {start}")
            if head[:4] != b'GRIB':
                raise ValueError(f"{path}: no GRIB marker at offset {start}")
            edition = head[7]
            if edition == 2:
                total = int.from_bytes(head[8:16], 'big')
            elif edition == 1:
                total = int.from_bytes(head[4:7], 'big')
            else:
                raise ValueError(f"{path}: unknown GRIB edition {edition}")
            if total <= 0 or start + total > size:
                raise ValueError(f"{path}: message at {start} claims {total} bytes, "
                                 f"file is {size}")
            fh.seek(start + total)
            n += 1
    return n


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 2
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from wrf_era5_comparison import EXPECTED_MESSAGES
    try:
        found = message_count(argv[0])
    except (OSError, ValueError) as exc:
        print(f"unreadable: {exc}")
        return 1
    print(f"{found}/{EXPECTED_MESSAGES}")
    return 0 if found == EXPECTED_MESSAGES else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
