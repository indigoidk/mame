#!/usr/bin/env python3
"""
panic_capture_validate.py — prove the ORIGINAL-panic capture pipeline works on the current exe.

The panic machinery in phase_c_epset.py (Z0 on _panic/_Debugger/_kdb_trap, regs, A6 backtrace,
symbolize) was never exercised against a real stop because the raw-disk read it targeted doesn't
reliably panic. This validates the whole capture pipeline end-to-end against a DETERMINISTIC,
benign kernel breakpoint (_namei, hit on any path lookup): arm after login, fire `ls`, and confirm
we halt exactly at _namei with a sane, symbolized A6 backtrace up through the syscall path.

If this passes, the identical pipeline will capture a real panic the moment one is triggered
(fire-batch or a mid-boot arm) — the only missing ingredient was ever a reproducible panic, not the
tool. PASS/FAIL on: (1) stop at the armed PC, (2) PC symbolizes to _namei, (3) backtrace non-trivial.
"""
import threading, time, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serial_console import SerialConsole, SERIAL_CHD
from phase_c_gdb import Gdb, REG_NAMES
from phase_c_epset import fetch_text_syms, walk_a6, symbolize

GDB_PORT = 2165
HERE = os.path.dirname(os.path.abspath(__file__))
TEST_SYM = "_namei"          # deterministic: any path lookup calls it


def main():
    sc = SerialConsole(log_path=os.path.join(HERE, "panic_capture_validate.log"),
                       mame_log_path=os.path.join(HERE, "panic_capture_validate_mame.log"))
    sc.hs.listen()
    sc.hs.launch_mame(chd=SERIAL_CHD, seconds=900, video="none",
                      extra=["-debug", "-debugger", "gdbstub", "-debugger_port", str(GDB_PORT)])
    print("[MAME: serial CHD + gdbstub :%d]" % GDB_PORT)

    gdb = Gdb(port=GDB_PORT)
    if not gdb.connect():
        print("!! gdb connect failed"); sc.close(); return 2
    gdb.recv_packet(timeout=3); gdb.negotiate()
    gdb._send("c")
    print("[gdb: continue -> booting]")

    sc.hs.accept(); sc.login(timeout=700)
    print("[serial login]")
    syms = fetch_text_syms(sc); keys = [s[0] for s in syms]
    name2addr = {n: a for a, n in syms}
    targets = {n: name2addr[n] for n in (TEST_SYM, "_panic", "_Debugger", "_kdb_trap") if n in name2addr}
    print("[symbols: %d] arming: %s" % (len(syms), ", ".join("%s=%08x" % kv for kv in targets.items())))

    # ---- interrupt, arm breakpoints AFTER boot (kernel now resident in RAM) ----
    gdb.sock.sendall(b"\x03"); gdb.recv_packet(timeout=15)
    for name, addr in targets.items():
        print("[Z0 %s @%08x] %s" % (name, addr, gdb.cmd("Z0,%x,2" % addr)))

    result = {}

    def cap():
        st = gdb.cont_until_stop(timeout=180); result["stop"] = st
        if st and st[0] in "TS":
            r, _ = gdb.regs(); result["regs"] = r
            pc, a6 = r.get("pc"), r.get("a6")
            result["channel"] = next((n for n, a in targets.items() if pc == a), None)
            result["bt"] = walk_a6(gdb, a6) if a6 else []

    t = threading.Thread(target=cap, daemon=True); t.start()
    time.sleep(1.0)
    sc.send("ls -la /etc >/dev/null 2>&1")     # path lookups -> _namei
    t.join(timeout=120)

    # ---- report ----
    print("\n" + "=" * 70)
    r = result.get("regs")
    if not r:
        print("FAIL: no stop captured (STOP=%s). See panic_capture_validate_mame.log" % result.get("stop"))
        print("=" * 70); sc.close(); return 1
    pc = r.get("pc"); ch = result.get("channel"); bt = result.get("bt") or []
    hx = lambda n: ("%08X" % r[n]) if r.get(n) is not None else "????????"
    print("STOP:", result.get("stop"))
    print("D:", " ".join("%s=%s" % (n, hx(n)) for n in REG_NAMES[:8]))
    print("A:", " ".join("%s=%s" % (n, hx(n)) for n in REG_NAMES[8:16]))
    print("SR=%04X PC=%s (%s)  channel=%s" %
          (r.get("sr", 0) & 0xffff, hx("pc"), symbolize(syms, keys, pc), ch))
    print("\nA6 backtrace:")
    for i, a in enumerate(bt):
        print("  #%d  %08X  %s" % (i, a, symbolize(syms, keys, a)))

    pc_ok = (ch == TEST_SYM) and (pc == name2addr[TEST_SYM])
    sym_ok = symbolize(syms, keys, pc).startswith(TEST_SYM)
    bt_ok = len(bt) >= 2
    print("\n---- pipeline checks ----")
    print("  [%s] halted at armed breakpoint (%s)" % ("PASS" if pc_ok else "FAIL", TEST_SYM))
    print("  [%s] PC symbolizes to %s" % ("PASS" if sym_ok else "FAIL", TEST_SYM))
    print("  [%s] non-trivial backtrace (>=2 frames): %d" % ("PASS" if bt_ok else "FAIL", len(bt)))
    ok = pc_ok and sym_ok and bt_ok
    print("RESULT:", "PASS - panic-capture pipeline validated on current exe" if ok else "FAIL")
    print("=" * 70)
    sc.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
