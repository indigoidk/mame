#!/usr/bin/env python3
"""
phase_c_epset.py — image-independent m68k fault + ORIGINAL-panic capture over gdbstub.

Supersedes the hardcoded `Z1 @ 0x1A1A` breakpoint (phase_c_gdb / phase4_panic) with two channels,
both armed AFTER boot (boot itself takes badaddr() probe bus errors) then the raw-disk read is fired:

  (1) MAME exception points -- `monitor epset 2` (bus error) + `monitor epset 3` (address error).
      Verified against MAME 0.288 source: gdbstub `Rcmd` -> execute_command (debuggdbstub.cpp:1293),
      and wait_for_debugger sends the stop packet on ANY debugger halt after a `c` (:1011). epset
      halts "at the start of the exception handler" (debughlp) -- the frame is already stacked, so we
      read SR/PC/format+vector/fault-address with NO hardcoded handler PC, and the frame's vector
      field tells bus-error (2) from address-error (3) apart (that field is exactly what the m68kcpu.h
      address-error fix corrects).

  (2) Z0 software breakpoints on `_panic` / `_Debugger` (addresses from `nm /bsd`). These catch the
      ORIGINAL panic entry -- a deliberate panic()/Debugger() CALL, not a CPU exception, so epset
      cannot see it -- BEFORE the ddb `_db_lookup` secondary null-deref that the 0x1A1A breakpoint
      was catching. On a _panic hit we also read the panic format string and the A6 backtrace, i.e.
      *why* the unlabeled-raw-disk read panicked, not just where the debugger then crashed.

Whichever fires first is decoded; the A6 frame chain is walked and symbolized against `nm -n /bsd`.
"""
import threading, time, sys, os, re, bisect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serial_console import SerialConsole, SERIAL_CHD
from phase_c_gdb import Gdb, REG_NAMES

GDB_PORT = 2163
BLANK = r"C:\DocumentNoSnc\CC\hp_mame\obsd_test\blank_rsd1.chd"
HERE = os.path.dirname(os.path.abspath(__file__))


def monitor(gdb, cmd):
    """gdb 'monitor' (qRcmd): run a debugger console command; return its decoded text output."""
    r = gdb.cmd("qRcmd," + cmd.encode("latin1").hex(), timeout=15)
    if r in (None, "", "OK"):
        return r or "OK"
    if r.startswith("E"):
        return "[err %s]" % r
    try:
        return bytes.fromhex(r).decode("latin1", "replace").strip()
    except ValueError:
        return r


def read_u16(gdb, addr):
    h = gdb.cmd("m%x,2" % addr, timeout=10) or ""
    return int(h, 16) if len(h) == 4 else None


def read_str(gdb, addr, n=64):
    """Read up to n bytes of a NUL-terminated guest string."""
    h = gdb.cmd("m%x,%x" % (addr, n), timeout=10) or ""
    try:
        raw = bytes.fromhex(h)
    except ValueError:
        return None
    return raw.split(b"\x00", 1)[0].decode("latin1", "replace")


def decode_frame(gdb, a7):
    """Decode the m68k exception stack frame at SSP=a7 (present at an epset/handler stop)."""
    d = {}
    w0 = gdb.read_u32(a7)                       # SR(hi16):PC(hi16)
    d["sr"] = (w0 >> 16) & 0xffff if w0 is not None else None
    d["pc"] = gdb.read_u32(a7 + 2)              # stacked (faulting/return) PC
    fv = read_u16(gdb, a7 + 6)                  # format/vector word
    if fv is not None:
        d["format"] = (fv >> 12) & 0xf
        d["vector"] = (fv & 0x0fff) >> 2
        if d["format"] in (0xA, 0xB):           # 68030 short/long bus-fault frames
            d["ssw"] = read_u16(gdb, a7 + 0x0A)
            d["fault_addr"] = gdb.read_u32(a7 + 0x10)
    return d


def walk_a6(gdb, a6, maxframes=8):
    """Follow the m68k frame-pointer chain: [A6]=prev A6, [A6+4]=return addr."""
    out, seen = [], set()
    for _ in range(maxframes):
        if not a6 or (a6 & 1) or a6 in seen:
            break
        seen.add(a6)
        ret = gdb.read_u32(a6 + 4)
        nxt = gdb.read_u32(a6)
        if ret is None:
            break
        out.append(ret)
        if not nxt or nxt <= a6:                # frames grow upward; stop on garbage
            break
        a6 = nxt
    return out


SYM_CACHE = os.path.join(HERE, "nm_bsd_text.txt")


def _parse_syms(text):
    syms = []
    for line in text.splitlines():
        p = line.split()
        if len(p) >= 3 and re.fullmatch(r"[0-9a-fA-F]+", p[0]) and p[1] in ("t", "T"):
            syms.append((int(p[0], 16), p[2]))
    syms.sort()
    return syms


def fetch_text_syms(sc, timeout=220):
    """Numeric text-symbol map [(addr,name),...], cached to nm_bsd_text.txt (kernel is immutable here)."""
    if os.path.exists(SYM_CACHE):
        with open(SYM_CACHE, "r") as f:
            syms = _parse_syms(f.read())
        if syms:
            return syms
    out, _ = sc.run("nm -n /bsd 2>/dev/null | grep -E ' [tT] '", timeout=timeout)
    syms = _parse_syms(out)
    if syms:
        with open(SYM_CACHE, "w") as f:
            for a, n in syms:
                f.write("%08x T %s\n" % (a, n))
    return syms


def symbolize(syms, keys, addr):
    if addr is None:
        return "?"
    if not syms:
        return "0x%08x" % addr
    i = bisect.bisect_right(keys, addr) - 1
    if i < 0:
        return "0x%08x" % addr
    base, name = syms[i]
    return "%s+0x%x" % (name, addr - base) if addr != base else name


def main():
    sc = SerialConsole(log_path=os.path.join(HERE, "phase_c_epset.log"),
                       mame_log_path=os.path.join(HERE, "phase_c_epset_mame.log"))
    sc.hs.listen()
    sc.hs.launch_mame(chd=SERIAL_CHD, chd2=BLANK, seconds=900, video="none",
                      extra=["-debug", "-debugger", "gdbstub", "-debugger_port", str(GDB_PORT)])
    print("[MAME: serial CHD + blank rsd1 + gdbstub :%d]" % GDB_PORT)

    gdb = Gdb(port=GDB_PORT)
    if not gdb.connect():
        print("!! gdb connect failed"); sc.close(); return 2
    gdb.recv_packet(timeout=3); gdb.negotiate()
    gdb._send("c")                              # continue -> boot (nothing armed yet)
    print("[gdb: continue -> booting]")

    bp_addr, syms, keys = {}, [], []
    try:
        sc.hs.accept(); sc.login(timeout=700)
        print("[serial login]")
        syms = fetch_text_syms(sc); keys = [s[0] for s in syms]
        name2addr = {n: a for a, n in syms}
        for name in ("_panic", "_Debugger", "_kdb_trap"):    # panic + both ddb entry points
            if name in name2addr:
                bp_addr[name] = name2addr[name]
        print("[symbols: %d text syms] bp targets: %s" %
              (len(syms), ", ".join("%s=%08x" % (k, v) for k, v in bp_addr.items())))
    except Exception as e:
        print("[pre-arm note]:", e)

    # ---- arm AFTER boot ----
    gdb.sock.sendall(b"\x03"); gdb.recv_packet(timeout=15)
    # FINDING (empirical, this rig): on the 68030 a demand-paging / copyin fault is ALSO a vector-2 bus
    # error, so `epset 2` halts on every routine page fault (it caught a supervisor copyin of user-data
    # 0x4DCC8, SSW FC=1) -- useless for isolating a panic. So catch the panic via the _panic/_Debugger
    # breakpoints, and keep only `epset 3` (an address error is genuinely rare on the 030 and never a
    # normal page fault). That epset-over-gdbstub works at all is the validated win (Rcmd->execute_command
    # + wait_for_debugger stop, MAME 0.288). To use epset 2 for a panic you'd need a condition that
    # rejects serviceable faults (e.g. supervisor + fault address in kernel space), which the frame isn't
    # readable for at epset-eval time -- hence the breakpoint approach below.
    print("[epset 3] " + monitor(gdb, "epset 3"))
    for name, addr in bp_addr.items():
        print("[Z0 %s @%08x] %s" % (name, addr, gdb.cmd("Z0,%x,2" % addr)))

    # ---- continue + fire the raw-disk read; catch the first stop ----
    result = {}

    def cap():
        st = gdb.cont_until_stop(timeout=300); result["stop"] = st
        if st and st[0] in "TS":
            r, _ = gdb.regs(); result["regs"] = r
            pc, a7, a6 = r.get("pc"), r.get("a7"), r.get("a6")
            result["channel"] = next((n for n, a in bp_addr.items() if pc == a), None)
            if result["channel"]:               # _panic / _Debugger / _kdb_trap breakpoint
                if a7:
                    result["caller"] = gdb.read_u32(a7)             # return addr -> who entered
                    if result["channel"] == "_panic":
                        result["panic_fmt"] = read_str(gdb, gdb.read_u32(a7 + 4) or 0)
            else:                               # epset: exception frame is stacked at SSP
                result["frame"] = decode_frame(gdb, a7) if a7 else None
            result["bt"] = walk_a6(gdb, a6) if a6 else []

    t = threading.Thread(target=cap, daemon=True); t.start()
    time.sleep(1.0)
    # Escalate triggers until one actually panics. A plain rsd1c read is handled gracefully ("no disk
    # label, defining c partition as entire disk"); the null-deref path is more likely on a partition
    # OTHER than 'c', which gets no synthesized default label.
    for tg in ("disklabel rsd1 >/dev/null 2>&1",
               "dd if=/dev/rsd1a of=/dev/null bs=512 count=1 2>/dev/null",
               "dd if=/dev/rsd1d of=/dev/null bs=512 count=1 2>/dev/null",
               "dd if=/dev/rsd1g of=/dev/null bs=512 count=1 2>/dev/null",
               "dd if=/dev/rsd1c of=/dev/null bs=512 count=1"):
        if result.get("stop"):
            break
        print("[trigger] " + tg)
        sc.send(tg); time.sleep(4)
    t.join(timeout=180)

    # ---- report ----
    print("\n" + "=" * 70)
    print("STOP:", result.get("stop"))
    r = result.get("regs")
    if not r:
        print("NO CAPTURE -- read may not have faulted, or arm missed. See phase_c_epset_mame.log")
        print("=" * 70); sc.close(); return 1
    hx = lambda n: ("%08X" % r[n]) if r.get(n) is not None else "????????"
    print("D:", " ".join("%s=%s" % (n, hx(n)) for n in REG_NAMES[:8]))
    print("A:", " ".join("%s=%s" % (n, hx(n)) for n in REG_NAMES[8:16]))
    print("SR=%04X PC=%s (%s)" % (r["sr"] & 0xffff if r.get("sr") is not None else 0,
                                  hx("pc"), symbolize(syms, keys, r.get("pc"))))
    ch = result.get("channel")
    if ch:
        print("\n>>> ORIGINAL PANIC ENTRY caught at %s (before the ddb db_lookup secondary) <<<" % ch)
        print("    panic message : %r" % result.get("panic_fmt"))
        print("    called from   : %s" % symbolize(syms, keys, result.get("caller")))
    else:
        f = result.get("frame") or {}
        vec = f.get("vector")
        vname = {2: "BUS ERROR", 3: "ADDRESS ERROR"}.get(vec, "vec %s" % vec)
        print("\n>>> EXCEPTION caught via epset (image-independent) <<<")
        print("    frame format  : 0x%X   vector: %s  (%s)" % (f.get("format", -1) & 0xF, vec, vname))
        print("    faulting PC   : %s  (%s)" %
              (("%08X" % f["pc"]) if f.get("pc") is not None else "?", symbolize(syms, keys, f.get("pc"))))
        if f.get("fault_addr") is not None:
            print("    fault address : %08X   SSW: %04X" % (f["fault_addr"], f.get("ssw") or 0))
        if vec == 3:
            print("    (vector 3 correctly stacked -> confirms the m68kcpu.h address-error fix)")
    bt = result.get("bt") or []
    if bt:
        print("\n    A6 backtrace:")
        for i, a in enumerate(bt):
            print("      #%d  %08X  %s" % (i, a, symbolize(syms, keys, a)))
    print("=" * 70)
    sc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
