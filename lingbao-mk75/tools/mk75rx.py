# Native (Linux hidraw) client for the MK75 2.4G RECEIVER protocol (3554:fa09, report 0x13, 20-byte frames), same framing as mk75-hid.js:
#   [0]=0x13 [1]=cmd [2]=packages [3]=index [4]=(layer<<4)|len [5..18]=payload (<=14) [19]=sum8(0..18)
# Usage: python3 tools/mk75rx.py cfg | psd | get CMD [LAYER] | side SLOT|all R G B [SECONDS]
#   side: stream side-light direct over the radio (cmd 0x08 layer 3: first slot + 4 x RGB per package, no ack) at 20 Hz;
#   needs fw/patches/side_direct.asm
import glob, os, select, sys, time

VID, PID, RID, FRAME, CHUNK = 0x3554, 0xFA09, 0x13, 20, 14
GET_LED, SET_LED = 0x44, 0x04

def find_dev():
    for h in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        if f'HID_ID=0003:{VID:08X}:{PID:08X}' in open(h + '/device/uevent').read() and bytes([0x85, RID]) in open(h + '/device/report_descriptor', 'rb').read():
            return '/dev/' + os.path.basename(h)
    sys.exit('2.4G receiver with report 0x13 not found')

def frame(cmd, packages=1, index=0, layer=0, chunk=b''):
    f = bytearray(FRAME); f[0] = RID; f[1] = cmd; f[2] = packages; f[3] = index; f[4] = ((layer & 0xf) << 4) | (len(chunk) & 0xf)
    f[5:5 + len(chunk)] = chunk; f[19] = sum(f[:19]) & 0xff; return bytes(f)

class Rx:
    def __init__(self, path=None, timeout=5.0): self.fd = os.open(path or find_dev(), os.O_RDWR | os.O_NONBLOCK); self.timeout = timeout
    def _drain(self):
        while select.select([self.fd], [], [], 0)[0]:
            try: os.read(self.fd, 64)
            except BlockingIOError: return
    def _recv(self, cmd):
        end = time.time() + self.timeout
        while time.time() < end:
            if not select.select([self.fd], [], [], 0.1)[0]: continue
            f = os.read(self.fd, 64)
            if len(f) >= FRAME and f[0] == RID and (f[1] & 0x7f) == cmd: return f      # unrelated reports (events, keys) are skipped
        raise TimeoutError(f'no reply to cmd {cmd:#x}')
    def get(self, cmd, layer=0, retries=3):
        for i in range(retries + 1):                     # radio packages do get lost; the JS client retries the same way
            try: return self._get(cmd, layer)
            except (IOError, TimeoutError):
                if i == retries: raise
                time.sleep(0.07)
    def _get(self, cmd, layer=0):
        self._drain(); os.write(self.fd, frame(cmd, layer=layer)); out = bytearray(); expect = 0
        while True:
            f = self._recv(cmd)
            if f[2] & 0x80: raise IOError('device reported error')
            total, idx, n = f[2] & 0x7f, f[3], min(f[4] & 0xf, CHUNK)
            if idx != expect: raise IOError(f'out of order: wanted {expect}, got {idx}')
            out += f[5:5 + n]; expect += 1
            if idx == total - 1: return bytes(out)
    def set(self, cmd, data, layer=0, ack=True, delay=0.015):
        # flash guards (firmware): keymap layers 0..3 only; macro blocks 0..7 (0xDC00..0xEBFF), block 8+ is firmware code
        if cmd == 0x01 and not 0 <= layer <= 3: raise ValueError(f'refusing keymap write to layer {layer}')
        if cmd == 0x03 and not 0 <= layer <= 7: raise ValueError(f'refusing macro write to block {layer}: overwrites firmware')
        n = max(1, -(-len(data) // CHUNK))
        for i in range(n):
            self._drain(); os.write(self.fd, frame(cmd, n, i, layer, data[i * CHUNK:(i + 1) * CHUNK]))
            if ack:
                f = self._recv(cmd)
                if f[2] & 0x80 or f[3] != i: raise IOError(f'package {i}: bad ack {f[:5].hex(" ")}')
            time.sleep(delay)
    def read_cfg(self):
        d = self.get(GET_LED)
        if len(d) != 128 or d[126:128] != b'\x5a\xa5': raise IOError('unexpected config: ' + d.hex(' '))
        return bytearray(d)
    def write_cfg(self, d):
        if d[56:58] != b'\xff\xff': raise IOError('refusing to write: bytes 56-57 are not ff ff (read from a sleeping keyboard?)')
        w = bytearray(d); w[9] = 1 if w[10] == 21 else 0                     # byte 9 = Self-define enable, as OemDrv writes it
        self.set(SET_LED, bytes(w))

if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(__file__)); import mk75wired as w
    a = sys.argv[1:]; kb = Rx()
    if not a or a[0] == 'cfg': d = kb.read_cfg(); print(d.hex(' ')); print(w.decode(d))
    elif a[0] == 'psd': print(kb.get(5).hex(' '))
    elif a[0] == 'get': print(kb.get(int(a[1], 0), int(a[2], 0) if len(a) > 2 else 0).hex(' '))
    elif a[0] == 'side':
        rgb = bytes(int(x, 0) for x in a[2:5]); secs = float(a[5]) if len(a) > 5 else 5
        slots = range(14) if a[1] == 'all' else [int(a[1], 0)]
        cols = [rgb if i in slots else b'\0\0\0' for i in range(14)] + [b'\0\0\0'] * 2
        end = time.time() + secs
        while time.time() < end:
            for first in (0, 4, 8, 12):
                os.write(kb.fd, frame(0x08, 1, 0, 3, bytes([first]) + b''.join(cols[first:first + 4]))); time.sleep(0.002)
            time.sleep(0.05)
    else: sys.exit('unknown command')
