# Reassemblable source for the MK75 stock firmware (SH68F90, 8051).
#   python3 tools/mk75asm.py dis   [dump.bin] [out.asm]   -> sdas8051 source of 0x0000-0xEFFF
#   python3 tools/mk75asm.py build [src.asm]  [out.bin] [ref.bin] -> assemble + link (SDCC, or SDCC in the 'fedora' distrobox), compare with ref
#   (default: the dump). The output is exactly 0xF000 bytes, the size sinowisp write expects.
#   python3 tools/mk75asm.py patch stock.asm patch.asm out.asm out.bin ref.bin -> apply a hook patch (see patch()), build, and
#   check that only the patch sites and the free space 0xEF33-0xEFF7 changed.
# The dump (captures/firmware/mk75-full-isp.bin) is the logical image as sinowisp reads it: 0x0000 holds the firmware's own
# LJMP, 0xEFF8-0xEFFF reads 00 (masked). Only 0x0000-0xEFFF is firmware; 0xF000-0xFFFF is the bootloader (never written).
# Code is found by recursive descent from the reset/interrupt vectors, tools/ghidra/seeds.txt, the code pointer tables in
# tools/mk75tables.txt, Keil LJMP jump tables (MOV DPTR,#T; MUL by 3 or MOV R0,A/ADD A,R0 x2; JMP @A+DPTR) and Keil
# ?C?CCASE case tables after their LCALL. Everything else is emitted as .db. Branch and call targets get labels (F_xxxx
# called, L_xxxx jumped to), and so do case/pointer table entries; MOV DPTR,#imm stays numeric (XRAM or code), so code
# that MOVC tables point into must not move. Names from tools/mk75syms.txt ("addr name") replace the generated labels.
import sys, os, re, shutil, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DUMP = os.path.join(REPO, 'captures/firmware/mk75-full-isp.bin')
FW_END = 0xF000
VECTORS = [0x0000] + [0x03 + 8 * k for k in range(16)]

# opcode -> (mnemonic, operand kinds); kinds: A C AB DPTR @DPTR @A+DPTR @A+PC Rn @Ri dir #imm #imm16 bit /bit rel a11 a16
OPS = {}
def op(code, mn, *k): OPS[code] = (mn, k)
for i in range(8):
    op(0x01 | i << 5, 'ajmp', 'a11'); op(0x11 | i << 5, 'acall', 'a11')
    for base, mn, k in ((0x08, 'inc', ()), (0x18, 'dec', ()), (0x28, 'add', ('A',)), (0x38, 'addc', ('A',)), (0x48, 'orl', ('A',)),
                        (0x58, 'anl', ('A',)), (0x68, 'xrl', ('A',)), (0x98, 'subb', ('A',)), (0xC8, 'xch', ('A',)), (0xE8, 'mov', ('A',))):
        op(base + i, mn, *k, 'R%d' % i)
    op(0x78 + i, 'mov', 'R%d' % i, '#imm'); op(0x88 + i, 'mov', 'dir', 'R%d' % i); op(0xA8 + i, 'mov', 'R%d' % i, 'dir')
    op(0xB8 + i, 'cjne', 'R%d' % i, '#imm', 'rel'); op(0xD8 + i, 'djnz', 'R%d' % i, 'rel'); op(0xF8 + i, 'mov', 'R%d' % i, 'A')
for i in range(2):
    r = '@R%d' % i
    for base, mn, k in ((0x06, 'inc', ()), (0x16, 'dec', ()), (0x26, 'add', ('A',)), (0x36, 'addc', ('A',)), (0x46, 'orl', ('A',)),
                        (0x56, 'anl', ('A',)), (0x66, 'xrl', ('A',)), (0x96, 'subb', ('A',)), (0xC6, 'xch', ('A',)), (0xD6, 'xchd', ('A',)),
                        (0xE6, 'mov', ('A',))):
        op(base + i, mn, *k, r)
    op(0x76 + i, 'mov', r, '#imm'); op(0x86 + i, 'mov', 'dir', r); op(0xA6 + i, 'mov', r, 'dir'); op(0xB6 + i, 'cjne', r, '#imm', 'rel')
    op(0xE2 + i, 'movx', 'A', r); op(0xF2 + i, 'movx', r, 'A'); op(0xF6 + i, 'mov', r, 'A')
for base, mn in ((0x24, 'add'), (0x34, 'addc'), (0x44, 'orl'), (0x54, 'anl'), (0x64, 'xrl'), (0x94, 'subb')):
    op(base, mn, 'A', '#imm'); op(base + 1, mn, 'A', 'dir')
for base, mn in ((0x42, 'orl'), (0x52, 'anl'), (0x62, 'xrl')):
    op(base, mn, 'dir', 'A'); op(base + 1, mn, 'dir', '#imm')
for c, mn, k in ((0x00, 'nop', ()), (0x02, 'ljmp', ('a16',)), (0x03, 'rr', ('A',)), (0x04, 'inc', ('A',)), (0x05, 'inc', ('dir',)),
                 (0x10, 'jbc', ('bit', 'rel')), (0x12, 'lcall', ('a16',)), (0x13, 'rrc', ('A',)), (0x14, 'dec', ('A',)), (0x15, 'dec', ('dir',)),
                 (0x20, 'jb', ('bit', 'rel')), (0x22, 'ret', ()), (0x23, 'rl', ('A',)), (0x30, 'jnb', ('bit', 'rel')), (0x32, 'reti', ()),
                 (0x33, 'rlc', ('A',)), (0x40, 'jc', ('rel',)), (0x50, 'jnc', ('rel',)), (0x60, 'jz', ('rel',)), (0x70, 'jnz', ('rel',)),
                 (0x72, 'orl', ('C', 'bit')), (0x73, 'jmp', ('@A+DPTR',)), (0x74, 'mov', ('A', '#imm')), (0x75, 'mov', ('dir', '#imm')),
                 (0x80, 'sjmp', ('rel',)), (0x82, 'anl', ('C', 'bit')), (0x83, 'movc', ('A', '@A+PC')), (0x84, 'div', ('AB',)),
                 (0x85, 'mov', ('dir', 'dir')), (0x90, 'mov', ('DPTR', '#imm16')), (0x92, 'mov', ('bit', 'C')), (0x93, 'movc', ('A', '@A+DPTR')),
                 (0xA0, 'orl', ('C', '/bit')), (0xA2, 'mov', ('C', 'bit')), (0xA3, 'inc', ('DPTR',)), (0xA4, 'mul', ('AB',)),
                 (0xB0, 'anl', ('C', '/bit')), (0xB2, 'cpl', ('bit',)), (0xB3, 'cpl', ('C',)), (0xB4, 'cjne', ('A', '#imm', 'rel')),
                 (0xB5, 'cjne', ('A', 'dir', 'rel')), (0xC0, 'push', ('dir',)), (0xC2, 'clr', ('bit',)), (0xC3, 'clr', ('C',)),
                 (0xC4, 'swap', ('A',)), (0xC5, 'xch', ('A', 'dir')), (0xD0, 'pop', ('dir',)), (0xD2, 'setb', ('bit',)), (0xD3, 'setb', ('C',)),
                 (0xD4, 'da', ('A',)), (0xD5, 'djnz', ('dir', 'rel')), (0xE0, 'movx', ('A', '@DPTR')), (0xE4, 'clr', ('A',)),
                 (0xE5, 'mov', ('A', 'dir')), (0xF0, 'movx', ('@DPTR', 'A')), (0xF4, 'cpl', ('A',)), (0xF5, 'mov', ('dir', 'A'))):
    op(c, mn, *k)
assert len(OPS) == 255  # all but 0xA5
OPLEN = {'dir': 1, '#imm': 1, '#imm16': 2, 'bit': 1, '/bit': 1, 'rel': 1, 'a11': 1, 'a16': 2}
STOP = {'ret', 'reti', 'ljmp', 'ajmp', 'sjmp', 'jmp'}

def decode(img, pc):
    """-> (mnemonic, [(kind, value)], length, [targets]) or None for 0xA5 / past the end."""
    if pc >= FW_END or img[pc] not in OPS: return None
    mn, kinds = OPS[img[pc]]
    n = 1 + sum(OPLEN.get(k, 0) for k in kinds)
    if pc + n > FW_END: return None
    b = img[pc + 1:pc + n]; i = 0; ops = []; tg = []
    # 0x85 encodes MOV dst,src as 85 src dst
    if img[pc] == 0x85: return mn, [('dir', b[1]), ('dir', b[0])], n, []
    for k in kinds:
        if k == 'a16': v = b[i] << 8 | b[i + 1]; i += 2; tg.append(v)
        elif k == '#imm16': v = b[i] << 8 | b[i + 1]; i += 2
        elif k == 'a11': v = ((pc + 2) & 0xF800) | (img[pc] >> 5) << 8 | b[i]; i += 1; tg.append(v)
        elif k == 'rel': v = (pc + n + (b[i] - 256 if b[i] > 127 else b[i])) & 0xFFFF; i += 1; tg.append(v)
        elif k in OPLEN: v = b[i]; i += 1
        else: v = None
        ops.append((k, v))
    return mn, ops, n, tg

def jump_table(img, pc, code):
    """JMP @A+DPTR at pc: Keil's 'MOV DPTR,#T; MOV B,#3; MUL AB; ...' or 'MOV DPTR,#T; MOV R0,A; ADD A,R0; ADD A,R0' table of
    3-byte slots at T. -> list of slot addresses. The bound comes from a preceding 'CJNE A,#n'; every slot is code (an LJMP,
    or the last case's body placed in the slot). Without a bound, slots run while they hold LJMPs."""
    win = bytes(img[max(0, pc - 32):pc])
    m = None
    for m in re.finditer(rb'\x90(..)(?:\x75\xf0\x03\xa4|\xf8\x28\x28)', win, re.S): pass
    if not m: return []
    t = m.group(1)[0] << 8 | m.group(1)[1]
    start = pc - len(win) + m.start()
    b = [code[a][1][1][1] for a in range(start - 16, start) if a in code and code[a][0] == 'cjne' and code[a][1][:2][0][0] == 'A'
         and code[a][1][1][0] == '#imm']
    if b:
        return [t + 3 * k for k in range(b[-1])]
    out = []
    while t + 3 <= FW_END and img[t] == 0x02 and t not in code:
        out.append(t); t += 3
    return out

def analyse(img, seeds):
    code = {}      # addr -> decoded instruction
    owner = {}     # every byte covered by an instruction -> its start
    called, jumped, tables = set(), set(), {}
    inline = {}    # addr -> ('case', [(target, value)], default) | ('const', n): data placed after a Keil helper call
    work = list(seeds)
    while work:
        pc = work.pop()
        while pc < FW_END and pc not in code:
            ins = decode(img, pc)
            if ins is None or any(owner.get(pc + j, pc) != pc for j in range(ins[2])):
                print('warning: bad or overlapping instruction at 0x%04x' % pc, file=sys.stderr); break
            code[pc] = ins
            for j in range(ins[2]): owner[pc + j] = pc
            mn, ops, n, tg = ins
            for t in tg:
                (called if mn in ('lcall', 'acall') else jumped).add(t)
                if t < FW_END: work.append(t)
            if mn == 'jmp':
                tables[pc] = jump_table(img, pc, code); work.extend(tables[pc]); jumped.update(tables[pc])
            if mn in STOP: break
            pc += n
            h = helper(img, tg[0]) if mn in ('lcall', 'acall') else None
            if h == 'case':
                # ?C?CCASE: DB hi,lo,value ... DB 0,0 then the default target; the call never returns here
                e, ent = pc, []
                while img[e] | img[e + 1]: ent.append((img[e] << 8 | img[e + 1], img[e + 2])); e += 3
                dflt = img[e + 2] << 8 | img[e + 3]
                inline[pc] = ('case', ent, dflt)
                for t in [t for t, v in ent] + [dflt]: jumped.add(t); work.append(t)
                break
            if h:
                inline[pc] = ('const', h); pc += h
    return code, owner, called, jumped, tables, inline

def load_tables():
    """tools/mk75tables.txt: 'ptr ADDR COUNT' = COUNT Keil generic code pointers (DB 0xFF,hi,lo) at ADDR, found by hand."""
    out = []
    for l in open(os.path.join(HERE, 'mk75tables.txt')):
        l = l.split('#')[0].split()
        if l and l[0] == 'ptr': out.append((int(l[1], 16), int(l[2])))
    return out

def discover(img, seeds):
    """analyse() with the hand-listed code pointer tables as extra entry points (called through ?C?ICALL)."""
    ptrs = {}
    for a, n in load_tables():
        for k in range(n):
            p = a + 3 * k
            assert img[p] == 0xFF, 'mk75tables.txt: no code pointer at 0x%04x' % p
            ptrs[p] = img[p + 1] << 8 | img[p + 2]
    code, owner, called, jumped, tables, inline = analyse(img, seeds + list(ptrs.values()))
    called.update(ptrs.values())
    return code, owner, called, jumped, tables, inline, ptrs

def helper(img, t):
    """Keil runtime helpers that read data placed after their call: 'case' (?C?CCASE) or n inline constant bytes."""
    if img[t:t + 7] == b'\xd0\x83\xd0\x82\xf8\xe4\x93': return 'case'
    if img[t:t + 9] == b'\xa8\x82\x85\x83\xf0\xd0\x83\xd0\x82' and img[t + 9:t + 21] == (b'\x12' + img[t + 10:t + 12]) * 4: return 4
    return None

def load_syms():
    p = os.path.join(HERE, 'mk75syms.txt'); s = {}
    if os.path.exists(p):
        for l in open(p):
            l = l.split('#')[0].split()
            if len(l) >= 2: s[int(l[0], 16)] = l[1]
    return s

def seeds_from_file():
    out = []
    for l in open(os.path.join(HERE, 'ghidra/seeds.txt')):
        l = l.split('#')[0].strip()
        if l: out.append(int(l, 16))
    return out

def dis(dump, out):
    img = open(dump, 'rb').read()
    seeds = [v for v in VECTORS if v == 0 or img[v] == 0x02] + seeds_from_file()
    code, owner, called, jumped, tables, inline, ptrs = discover(img, seeds)
    syms = load_syms()
    def label(a):
        if a in syms: return syms[a]
        return ('F_%04x' if a in called else 'L_%04x') % a
    # labels only where a target starts a decoded instruction (so moving code keeps it right); else stay numeric
    labelled = {a for a in called | jumped if a in code} | {a for a in syms if a in code}
    def tgt(v):
        if v in labelled: return label(v)
        return 'BOOT_%04x' % v if v >= FW_END else '0x%04x' % v
    def fmt(k, v):
        if k in ('a16', 'a11', 'rel'): return tgt(v)
        if k == 'dir': return '0x%02x' % v
        if k == 'bit': return '0x%02x' % v
        if k == '/bit': return '/0x%02x' % v
        if k == '#imm': return '#0x%02x' % v
        if k == '#imm16': return '#0x%04x' % v
        return k.lower() if k.startswith('R') or k in ('A', 'C', 'AB', 'DPTR') else k.lower().replace('dptr', 'dptr')
    boots = sorted({t for i in code.values() for t in i[3] if t >= FW_END})
    L = ['; MK75 stock firmware, generated by tools/mk75asm.py from %s' % os.path.basename(dump),
         '; %d instructions, %d code bytes, %d jump tables' % (len(code), len(owner), sum(1 for t in tables.values() if t)),
         '\t.module mk75', '\t.area CSEG (ABS,CODE)']
    L += ['BOOT_%04x = 0x%04x' % (b, b) for b in boots]
    a = 0
    while a < FW_END:
        if a in code:
            if a in labelled: L.append('%s:' % label(a))
            mn, ops, n, tg = code[a]
            L.append('\t.org 0x%04x' % a if a == 0 else None)
            s = '\t%-6s %s' % (mn, ','.join(fmt(k, v) for k, v in ops))
            L.append('%-40s; %04x  %s' % (s.rstrip(), a, img[a:a + n].hex()))
            a += n
        elif a in ptrs:
            L.append('\t.db 0xff,>%s,<%s%s; %04x  code pointer' % (tgt(ptrs[a]), tgt(ptrs[a]), ' ' * 8, a)); a += 3
        elif a in inline and inline[a][0] == 'case':
            _, ent, dflt = inline[a]
            for t, v in ent:
                L.append('\t.db >%s,<%s,0x%02x%s; %04x  case' % (tgt(t), tgt(t), v, ' ' * 8, a)); a += 3
            L.append('\t.db 0x00,0x00,>%s,<%s%s; %04x  default' % (tgt(dflt), tgt(dflt), ' ' * 8, a)); a += 4
        else:
            e = a
            while e < FW_END and e not in code and (e == a or (e not in inline and e not in ptrs)) and e - a < 16: e += 1
            L.append('\t.db %s%s; %04x' % (','.join('0x%02x' % x for x in img[a:e]), ' ' * 2, a))
            a = e
    open(out, 'w').write('\n'.join(l for l in L if l is not None) + '\n')
    print('%s: %d instructions, %d code bytes / %d, %d labels, %d jump tables (%d entries)' % (
        out, len(code), len(owner), FW_END, len(labelled), sum(1 for t in tables.values() if t), sum(len(t) for t in tables.values())))

def ihx_to_bin(path, size):
    img = bytearray(size); seen = bytearray(size); base = 0
    for l in open(path):
        l = l.strip()
        if not l.startswith(':'): continue
        r = bytes.fromhex(l[1:]); n, addr, typ = r[0], r[1] << 8 | r[2], r[3]
        if typ == 0:
            for i in range(n):
                p = base + addr + i
                if p >= size: sys.exit('ihx: byte past 0x%x at 0x%x' % (size, p))
                img[p] = r[4 + i]; seen[p] = 1
        elif typ == 4: base = (r[4] << 8 | r[5]) << 16
    return img, seen

def toolchain():
    """SDCC's 8051 assembler and linker: Debian/Arch names, Fedora's sdcc- names, or (no SDCC on the host) the 'fedora' distrobox."""
    for sdas, sdld in (('sdas8051', 'sdld'), ('sdcc-sdas8051', 'sdcc-sdld')):
        if shutil.which(sdas): return [], sdas, sdld
    return ['distrobox', 'enter', 'fedora', '--'], 'sdcc-sdas8051', 'sdcc-sdld'

def build(src, out, ref_path=DUMP):
    d = os.path.dirname(os.path.abspath(out)); base = os.path.join(d, os.path.splitext(os.path.basename(src))[0])
    wrap, sdas, sdld = toolchain()
    def run(*cmd):
        r = subprocess.run(wrap + list(cmd), capture_output=True, text=True)
        if r.returncode: sys.exit('%s failed:\n%s%s' % (cmd[0], r.stdout, r.stderr))
    run(sdas, '-plosgff', '-o', base + '.rel', os.path.abspath(src))
    run(sdld, '-n', '-i', base + '.ihx', base + '.rel')
    img, seen = ihx_to_bin(base + '.ihx', FW_END)
    open(out, 'wb').write(img)
    ref = open(ref_path, 'rb').read()[:FW_END]
    diff = [i for i in range(FW_END) if img[i] != ref[i]]
    print('%s: %d bytes emitted, %d differ from %s' % (out, sum(seen), len(diff), os.path.basename(ref_path)))
    for i in diff[:20]: print('  0x%04x: built %02x stock %02x' % (i, img[i], ref[i]))
    return not diff

FREE = (0xEF33, 0xEFF8)  # zeros after the last stock code; 0xEFF8-0xEFFF is the boot entry sinowisp writes

def patch(stock, patchfile, out_asm, out_bin, ref_path):
    """Apply a hook patch: ';@site ADDR LEN' replaces the stock instructions at ADDR..ADDR+LEN with the lines below it
    (same size); everything after ';@code' is appended (new code, .org inside FREE). Then build, and check that only the
    sites and FREE changed."""
    src = open(stock).read().splitlines(); sites = []; code = []; cur = None
    for l in open(patchfile).read().splitlines():
        m = re.match(r';@site\s+(0x[0-9a-fA-F]+)\s+(\d+)', l)
        if m: cur = (int(m.group(1), 16), int(m.group(2)), []); sites.append(cur); continue
        if l.startswith(';@code'): cur = None; continue
        (cur[2] if cur else code).append(l)
    for addr, n, new in sites:
        idx = [i for i, l in enumerate(src) if re.search(r'; ([0-9a-f]{4})  [0-9a-f]+$', l)
               and addr <= int(re.search(r'; ([0-9a-f]{4})  ', l).group(1), 16) < addr + n]
        got = sum(len(re.search(r'  ([0-9a-f]+)$', src[i]).group(1)) // 2 for i in idx)
        first = int(re.search(r'; ([0-9a-f]{4})  ', src[idx[0]]).group(1), 16) if idx else -1
        if first != addr or got != n: sys.exit('site 0x%04x: does not cover whole instructions (%d bytes)' % (addr, got))
        src[idx[0]:idx[-1] + 1] = new + ['; ^ patched 0x%04x, %d bytes' % (addr, n)]
    open(out_asm, 'w').write('\n'.join(src + ['; ---- %s' % os.path.basename(patchfile)] + code) + '\n')
    build(out_asm, out_bin, ref_path)
    img = open(out_bin, 'rb').read(); ref = open(ref_path, 'rb').read()[:FW_END]
    ok = [(a, a + n) for a, n, _ in sites] + [FREE]
    diff = [i for i in range(FW_END) if img[i] != ref[i]]
    bad = [i for i in diff if not any(s <= i < e for s, e in ok)]
    used = [i for i in range(*FREE) if img[i]]
    print('patched: %d bytes changed; sites %s; new code 0x%04x-0x%04x (%d of %d free bytes)' % (
        len(diff), ', '.join('0x%04x' % a for a, n, _ in sites), FREE[0], (max(used) + 1) if used else FREE[0],
        (max(used) + 1 - FREE[0]) if used else 0, FREE[1] - FREE[0]))
    if bad: sys.exit('changes outside the sites and free space: ' + ', '.join('0x%04x' % i for i in bad[:20]))
    if any(img[FW_END - 8:FW_END]): sys.exit('new code reaches the boot entry 0xEFF8-0xEFFF')
    return True

if __name__ == '__main__':
    a = sys.argv[1:] or ['dis']
    if a[0] == 'dis': dis(a[1] if len(a) > 1 else DUMP, a[2] if len(a) > 2 else os.path.join(REPO, 'fw/build/mk75.asm'))
    elif a[0] == 'build': sys.exit(0 if build(a[1] if len(a) > 1 else os.path.join(REPO, 'fw/build/mk75.asm'),
                                                a[2] if len(a) > 2 else os.path.join(REPO, 'fw/build/mk75.bin'),
                                                a[3] if len(a) > 3 else DUMP) else 1)
    elif a[0] == 'patch' and len(a) == 6: patch(*a[1:])
    else: sys.exit('usage: mk75asm.py dis [dump] [out.asm] | build [src.asm] [out.bin] [ref.bin] |'
                   ' patch stock.asm patch.asm out.asm out.bin ref.bin')
