# Native (Linux hidraw) client for the MK75 WIRED protocol: 520-byte feature report 6, same frame as mk75-wired.js.
# Usage: python3 tools/mk75wired.py [--dev /dev/hidrawN] cfg | psd | get CMD LEN [INDEX] | poke OFFSET VALUE
#   cfg  : read + decode the 128-byte config (GET 0x84)          poke : read-modify-write one config byte (SET 0x04), prints the old value
#   side SLOT|all R G B [SECONDS]: stream side-light direct frames (SET 0x07, 14 x RGB) at 20 Hz; needs fw/patches/side_direct.asm
#   side map A-B|A,B,C.. [SECONDS]: those slots (at most 7) in red, green, blue, yellow, magenta, cyan, white, others off
# The hidraw node is found automatically (258a:010c with a 519-byte feature report 6) unless --dev is given.
import fcntl, glob, os, sys, time

VID, PID, REPORT_ID, SIZE, BLOCK = 0x258A, 0x010C, 6, 520, 512
GET_PSD, GET_LED, SET_LED = 0x82, 0x84, 0x04
EFFECTS = {0: 'OFF', 1: 'Fixed on', 2: 'Respire', 3: 'Rainbow', 4: 'Flash away', 5: 'Raindrops', 6: 'Rainbow wheel', 7: 'Ripples shining', 8: 'Stars twinkle',
           9: 'Shadow disappear', 10: 'Retro snake', 11: 'Neon stream', 12: 'Reaction', 13: 'Sine wave', 14: 'Retinue scanning', 15: 'Rotating windmill',
           16: 'Colorful waterfall', 17: 'Blossoming', 18: 'Rotating storm', 21: 'Self-define'}
LEDOPT = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 21]

def _ioc(n, length): return (3 << 30) | (length << 16) | (ord('H') << 8) | n          # _IOC(READ|WRITE, 'H', n, len)
def find_dev():
    for h in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        ue = open(h + '/device/uevent').read()
        if f'HID_ID=0003:{VID:08X}:{PID:08X}' not in ue: continue
        rd = open(h + '/device/report_descriptor', 'rb').read()
        if bytes([0x85, REPORT_ID]) in rd and b'\xb1\x02' in rd: return '/dev/' + os.path.basename(h)
    sys.exit('wired MK75 not found (is the USB cable plugged in?)')

class Wired:
    def __init__(self, path, delay=0.02): self.fd = os.open(path, os.O_RDWR); self.delay = delay
    def _frame(self, cmd, index, blocks, block, length, chunk=b''):
        f = bytearray(SIZE); f[0] = REPORT_ID; f[1] = cmd; f[2] = index; f[4] = blocks; f[5] = block; f[6] = length & 0xff; f[7] = length >> 8
        f[8:8 + len(chunk)] = chunk; return f
    def _set(self, f):
        for i in range(3):
            try: fcntl.ioctl(self.fd, _ioc(0x06, SIZE), bytes(f)); return
            except OSError:
                if i == 2: raise
                time.sleep(0.07)
    def get(self, cmd, length, index=0):
        out, blocks = bytearray(), max(1, -(-length // BLOCK))
        for b in range(blocks):
            n = min(BLOCK, length - b * BLOCK)
            time.sleep(self.delay); self._set(self._frame(cmd, index, blocks, b, n)); time.sleep(self.delay)
            buf = bytearray(SIZE); buf[0] = REPORT_ID; got = fcntl.ioctl(self.fd, _ioc(0x07, SIZE), buf, True)
            r = buf[1:]                                                  # after the report ID: [cmd index 0 blocks block lenLo lenHi] + data
            if r[0] != cmd: raise IOError(f'response cmd {r[0]:#x} != {cmd:#x}: {r[:7].hex(" ")}')
            out += r[7:7 + n]
        return bytes(out)
    def set(self, cmd, data, index=0):
        blocks = max(1, -(-len(data) // BLOCK))
        for b in range(blocks):
            chunk = data[b * BLOCK:(b + 1) * BLOCK]; time.sleep(self.delay); self._set(self._frame(cmd, index, blocks, b, len(chunk), chunk))
    def read_cfg(self):
        d = self.get(GET_LED, 128)
        if d[126:128] != b'\x5a\xa5': raise IOError('config without 5a a5 end marker: ' + d.hex(' '))
        return bytearray(d)
    def write_cfg(self, d):
        if d[56:58] != b'\xff\xff': raise IOError('refusing to write: bytes 56-57 are not ff ff (read from a sleeping keyboard?)')
        w = bytearray(d); w[9] = 1 if w[10] == 21 else 0; self.set(SET_LED, bytes(w))   # byte 9 = Self-define enable, as OemDrv writes it

def decode(d):
    e = d[10]; slot = 58 + 2 * LEDOPT.index(e) if e in LEDOPT else None
    s = [f'effect {e} "{EFFECTS.get(e, "?")}"' + (f', pair @{slot}: brightness {d[slot]}, speed {d[slot + 1] >> 4}, colourful {d[slot + 1] & 15 == 7}' if slot is not None else ', no pair'),
         f'side light mode {d[18]} colour {d[19]} brightness {d[20]} speed {d[21]}', f'debounce {d[3]}  sleep {d[24]} ({d[24] * 30} s; 0 = never)  knob {d[26]}  byte9 {d[9]}  OS {d[0]},{d[27]}']
    return '\n'.join(s)

if __name__ == '__main__':
    a = sys.argv[1:]; path = None
    if a[:1] == ['--dev']: path, a = a[1], a[2:]
    kb = Wired(path or find_dev())
    if not a or a[0] == 'cfg':
        d = kb.read_cfg(); print(d.hex(' ')); print(decode(d))
    elif a[0] == 'psd': print(kb.get(GET_PSD, 6, 1).hex(' '))
    elif a[0] == 'get': print(kb.get(int(a[1], 0), int(a[2], 0), int(a[3], 0) if len(a) > 3 else 0).hex(' '))
    elif a[0] == 'poke':
        off, val = int(a[1], 0), int(a[2], 0)
        if off in (9, 126, 127) or not 0 <= off < 126 or not 0 <= val <= 255: sys.exit('refusing: offset must be 0..125 (not 9), value 0..255')
        d = kb.read_cfg(); old = d[off]; d[off] = val; kb.write_cfg(d); back = kb.read_cfg()[off]
        print(f'config[{off}]: was {old}, wrote {val}, read back {back}   (restore: poke {off} {old})')
    elif a[0] == 'side':
        if a[1] == 'map':
            if '-' in a[2]: lo, hi = (int(x, 0) for x in a[2].split('-')); order = list(range(lo, hi + 1))
            else: order = [int(x, 0) for x in a[2].split(',')]
            secs = float(a[3]) if len(a) > 3 else 10
            pal = [(80, 0, 0), (0, 80, 0), (0, 0, 80), (80, 80, 0), (80, 0, 80), (0, 80, 80), (80, 80, 80)]
            frame = b''.join(bytes(pal[order.index(i)]) if i in order[:7] else b'\0\0\0' for i in range(14))
        else:
            rgb = bytes(int(x, 0) for x in a[2:5]); secs = float(a[5]) if len(a) > 5 else 5
            slots = range(14) if a[1] == 'all' else [int(a[1], 0)]
            frame = b''.join(rgb if i in slots else b'\0\0\0' for i in range(14))
        end = time.time() + secs
        while time.time() < end: kb.set(0x07, frame); time.sleep(0.05)
    else: sys.exit(__doc__ or 'unknown command')
