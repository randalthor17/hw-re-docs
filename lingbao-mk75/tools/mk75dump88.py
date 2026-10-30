#!/usr/bin/env python3
# Read the whole 64 KB flash over the wired keyboard's GET 0x88 (no ISP, no root beyond hidraw access) and compare it with a dump.
# Usage: python3 tools/mk75dump88.py OUT.bin [REF.bin]
# GET 0x88 block b returns code memory from 0x00D5 + b * 0x200; the 16-bit pointer wraps, so blocks 0-127 cover 0x0000-0xFFFF.
# Read-only: a GET writes no flash and skips the LED-scan pause. Cable only (the receiver has no firmware read).
import os, sys, time, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mk75wired as w

BASE = 0x00D5

def read_block(kb, b):
    time.sleep(kb.delay); kb._set(kb._frame(0x88, 0, 1, b, w.BLOCK)); time.sleep(kb.delay)
    buf = bytearray(w.SIZE); buf[0] = w.REPORT_ID
    w.fcntl.ioctl(kb.fd, w._ioc(0x07, w.SIZE), buf, True)
    r = buf[1:]                                                  # [cmd index 0 blocks block lenLo lenHi] + data
    if r[0] != 0x88 or r[4] != b: raise IOError(f'block {b}: bad reply header {r[:7].hex(" ")}')
    return r[7:7 + w.BLOCK]

def dump(kb):
    img, t0 = bytearray(0x10000), time.time()
    for b in range(128):
        for i, v in enumerate(read_block(kb, b)): img[(BASE + b * 0x200 + i) & 0xFFFF] = v
        if b % 16 == 15: print(f'block {b + 1}/128  {time.time() - t0:.1f} s', flush=True)
    return img

def compare(img, ref):
    diff = [a for a in range(min(len(ref), len(img))) if ref[a] != img[a]]
    runs = []
    for a in diff:
        if runs and a <= runs[-1][1] + 16: runs[-1][1] = a
        else: runs.append([a, a])
    print(f'{len(diff)} bytes differ')
    for s, e in runs[:40]: print(f'  0x{s:04X}-0x{e:04X} ({e - s + 1} B)')

if __name__ == '__main__':
    if len(sys.argv) < 2: sys.exit(__doc__ or 'usage: mk75dump88.py OUT.bin [REF.bin]')
    img = dump(w.Wired(w.find_dev()))
    open(sys.argv[1], 'wb').write(img)
    print('MD5', hashlib.md5(img).hexdigest())
    if len(sys.argv) > 2: compare(img, open(sys.argv[2], 'rb').read())
