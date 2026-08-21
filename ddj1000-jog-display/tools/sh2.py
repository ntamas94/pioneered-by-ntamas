"""A small SH-2A disassembler, enough to read the DDJ-1000's screen firmware.

Written because capstone's SH support mis-decodes the very instructions this
needs -- it renders `mov #imm,rn` as a store and gives up on whole stretches --
and reading a dispatcher wrongly is worse than not reading it.

Covers the integer subset the firmware is built from; anything else comes back
as `.word`, which is honest and rare enough to work around.
"""


def _r(n):
    return "r%d" % n


# SH-2A's 32-bit forms: a 0x3nm1 word followed by one that picks the operation
# in its top nibble and carries a 12-bit displacement. These are how the
# firmware reads report bytes, so without them the interesting half of every
# handler decodes as rubbish.
WIDE_OPS = {
    0x0: "mov.b %(m)s,@(%(d)d,%(n)s)",
    0x1: "mov.w %(m)s,@(%(d)d,%(n)s)",
    0x2: "mov.l %(m)s,@(%(d)d,%(n)s)",
    0x4: "mov.b @(%(d)d,%(m)s),%(n)s",
    0x5: "mov.w @(%(d)d,%(m)s),%(n)s",
    0x6: "mov.l @(%(d)d,%(m)s),%(n)s",
    0x8: "movu.b @(%(d)d,%(m)s),%(n)s",
    0x9: "movu.w @(%(d)d,%(m)s),%(n)s",
}


def decode_wide(w1, w2):
    """The 32-bit instruction (w1, w2), or None if this is not one."""
    if (w1 & 0xF00F) != 0x3001:
        return None
    op = (w2 >> 12) & 0xF
    if op not in WIDE_OPS:
        return None
    n = (w1 >> 8) & 0xF
    m = (w1 >> 4) & 0xF
    return WIDE_OPS[op] % {"n": "r%d" % n, "m": "r%d" % m, "d": w2 & 0xFFF}


def decode(w, pc, mem=None):
    """One instruction. Returns (text, target) -- target for branches/loads."""
    n = (w >> 8) & 0xF
    m = (w >> 4) & 0xF
    d = w & 0xF
    d8 = w & 0xFF
    d12 = w & 0xFFF
    op = (w >> 12) & 0xF

    def s8(v):
        return v - 0x100 if v & 0x80 else v

    def s12(v):
        return v - 0x1000 if v & 0x800 else v

    if w == 0x0009:
        return "nop", None
    if w == 0x000B:
        return "rts", None
    if w == 0x0028:
        return "clrmac", None
    if w == 0x0019:
        return "div0u", None
    if w == 0x006B:
        return "rte", None

    if op == 0x0:
        if d == 0x4:
            return "mov.b %s,@(r0,%s)" % (_r(m), _r(n)), None
        if d == 0x5:
            return "mov.w %s,@(r0,%s)" % (_r(m), _r(n)), None
        if d == 0x6:
            return "mov.l %s,@(r0,%s)" % (_r(m), _r(n)), None
        if d == 0x7:
            return "mul.l %s,%s" % (_r(m), _r(n)), None
        if d == 0xC:
            return "mov.b @(r0,%s),%s" % (_r(m), _r(n)), None
        if d == 0xD:
            return "mov.w @(r0,%s),%s" % (_r(m), _r(n)), None
        if d == 0xE:
            return "mov.l @(r0,%s),%s" % (_r(m), _r(n)), None
        if w & 0xFF == 0x02:
            return "stc sr,%s" % _r(n), None
        if w & 0xFF == 0x0A:
            return "sts mach,%s" % _r(n), None
        if w & 0xFF == 0x1A:
            return "sts macl,%s" % _r(n), None
        if w & 0xFF == 0x2A:
            return "sts pr,%s" % _r(n), None
        if w & 0xFF == 0x23:
            return "braf %s" % _r(n), None
        if w & 0xFF == 0x03:
            return "bsrf %s" % _r(n), None
        return ".word 0x%04x" % w, None

    if op == 0x1:
        return "mov.l %s,@(%d,%s)" % (_r(m), d * 4, _r(n)), None

    if op == 0x2:
        names = {0x0: "mov.b %s,@%s", 0x1: "mov.w %s,@%s", 0x2: "mov.l %s,@%s",
                 0x4: "mov.b %s,@-%s", 0x5: "mov.w %s,@-%s", 0x6: "mov.l %s,@-%s",
                 0x7: "div0s %s,%s", 0x8: "tst %s,%s", 0x9: "and %s,%s",
                 0xA: "xor %s,%s", 0xB: "or %s,%s", 0xC: "cmp/str %s,%s",
                 0xD: "xtrct %s,%s", 0xE: "mulu.w %s,%s", 0xF: "muls.w %s,%s"}
        if d in names:
            return names[d] % (_r(m), _r(n)), None
        return ".word 0x%04x" % w, None

    if op == 0x3:
        names = {0x0: "cmp/eq %s,%s", 0x2: "cmp/hs %s,%s", 0x3: "cmp/ge %s,%s",
                 0x4: "div1 %s,%s", 0x5: "dmulu.l %s,%s", 0x6: "cmp/hi %s,%s",
                 0x7: "cmp/gt %s,%s", 0x8: "sub %s,%s", 0xA: "subc %s,%s",
                 0xB: "subv %s,%s", 0xC: "add %s,%s", 0xD: "dmuls.l %s,%s",
                 0xE: "addc %s,%s", 0xF: "addv %s,%s"}
        if d in names:
            return names[d] % (_r(m), _r(n)), None
        return ".word 0x%04x" % w, None

    if op == 0x4:
        low = w & 0xFF
        one = {0x00: "shll %s", 0x01: "shlr %s", 0x04: "rotl %s", 0x05: "rotr %s",
               0x08: "shll2 %s", 0x09: "shlr2 %s", 0x10: "dt %s", 0x11: "cmp/pz %s",
               0x15: "cmp/pl %s", 0x18: "shll8 %s", 0x19: "shlr8 %s",
               0x20: "shal %s", 0x21: "shar %s", 0x24: "rotcl %s", 0x25: "rotcr %s",
               0x28: "shll16 %s", 0x29: "shlr16 %s", 0x0B: "jsr @%s",
               0x2B: "jmp @%s", 0x0E: "ldc %s,sr", 0x1E: "ldc %s,gbr",
               0x0A: "lds %s,mach", 0x1A: "lds %s,macl", 0x2A: "lds %s,pr",
               0x22: "sts.l pr,@-%s", 0x26: "lds.l @%s+,pr",
               0x02: "sts.l mach,@-%s", 0x12: "sts.l macl,@-%s",
               0x06: "lds.l @%s+,mach", 0x16: "lds.l @%s+,macl",
               0x0F: "mac.w @%s+,@%s+"}
        if low in one:
            return one[low] % _r(n), None
        if low == 0x0C:
            return "shad %s,%s" % (_r(m), _r(n)), None
        if low == 0x0D:
            return "shld %s,%s" % (_r(m), _r(n)), None
        return ".word 0x%04x" % w, None

    if op == 0x5:
        return "mov.l @(%d,%s),%s" % (d * 4, _r(m), _r(n)), None

    if op == 0x6:
        names = {0x0: "mov.b @%s,%s", 0x1: "mov.w @%s,%s", 0x2: "mov.l @%s,%s",
                 0x3: "mov %s,%s", 0x4: "mov.b @%s+,%s", 0x5: "mov.w @%s+,%s",
                 0x6: "mov.l @%s+,%s", 0x7: "not %s,%s", 0x8: "swap.b %s,%s",
                 0x9: "swap.w %s,%s", 0xA: "negc %s,%s", 0xB: "neg %s,%s",
                 0xC: "extu.b %s,%s", 0xD: "extu.w %s,%s", 0xE: "exts.b %s,%s",
                 0xF: "exts.w %s,%s"}
        return names[d] % (_r(m), _r(n)), None

    if op == 0x7:
        return "add #%d,%s" % (s8(d8), _r(n)), None

    if op == 0x8:
        sub = (w >> 8) & 0xF
        if sub == 0x0:
            return "mov.b r0,@(%d,%s)" % (d, _r(m)), None
        if sub == 0x1:
            return "mov.w r0,@(%d,%s)" % (d * 2, _r(m)), None
        if sub == 0x4:
            return "mov.b @(%d,%s),r0" % (d, _r(m)), None
        if sub == 0x5:
            return "mov.w @(%d,%s),r0" % (d * 2, _r(m)), None
        if sub == 0x8:
            return "cmp/eq #0x%02x,r0" % d8, None
        if sub == 0x9:
            t = pc + 4 + s8(d8) * 2
            return "bt 0x%06x" % t, t
        if sub == 0xB:
            t = pc + 4 + s8(d8) * 2
            return "bf 0x%06x" % t, t
        if sub == 0xD:
            t = pc + 4 + s8(d8) * 2
            return "bt/s 0x%06x" % t, t
        if sub == 0xF:
            t = pc + 4 + s8(d8) * 2
            return "bf/s 0x%06x" % t, t
        return ".word 0x%04x" % w, None

    if op == 0x9:
        addr = (pc + 4) + d8 * 2
        val = None
        if mem is not None and addr + 2 <= len(mem):
            val = int.from_bytes(mem[addr:addr + 2], "big")
        return ("mov.w @(0x%06x),%s%s" % (addr, _r(n),
                "   ; = 0x%04x" % val if val is not None else ""), addr)

    if op == 0xA:
        t = pc + 4 + s12(d12) * 2
        return "bra 0x%06x" % t, t
    if op == 0xB:
        t = pc + 4 + s12(d12) * 2
        return "bsr 0x%06x" % t, t

    if op == 0xC:
        sub = (w >> 8) & 0xF
        if sub == 0x8:
            return "tst #0x%02x,r0" % d8, None
        if sub == 0x9:
            return "and #0x%02x,r0" % d8, None
        if sub == 0xA:
            return "xor #0x%02x,r0" % d8, None
        if sub == 0xB:
            return "or #0x%02x,r0" % d8, None
        if sub == 0x7:
            return "mova @(0x%06x),r0" % (((pc + 4) & ~3) + d8 * 4), None
        return ".word 0x%04x" % w, None

    if op == 0xD:
        addr = ((pc + 4) & ~3) + d8 * 4
        val = None
        if mem is not None and addr + 4 <= len(mem):
            val = int.from_bytes(mem[addr:addr + 4], "big")
        return ("mov.l @(0x%06x),%s%s" % (addr, _r(n),
                "   ; = 0x%08x" % val if val is not None else ""), addr)

    if op == 0xE:
        return "mov #%d,%s" % (s8(d8), _r(n)), None

    return ".word 0x%04x" % w, None


def disassemble(mem, start, count, base=0):
    out = []
    off = start
    for _ in range(count):
        if off + 2 > len(mem):
            break
        w = int.from_bytes(mem[off:off + 2], "big")
        if off + 4 <= len(mem):
            w2 = int.from_bytes(mem[off + 2:off + 4], "big")
            wide = decode_wide(w, w2)
            if wide:
                out.append((base + off, w, wide))
                off += 4
                continue
        text, _ = decode(w, off, mem)
        out.append((base + off, w, text))
        off += 2
    return out
