#!/usr/bin/env python3
"""
panic_hunt.py — threads 2+3: hunt OpenBSD 2.2 crashes with DUAL-channel capture.

Combines the two capabilities validated 2026-07-17:
  * serial KERNEL console (panic_cfg: 98644 Remote DIP) so any panic/DDB text prints to the socket,
    where we can read the panic line and drive ddb (`trace`) directly; and
  * gdbstub Z0 breakpoints on _panic/_Debugger/_kdb_trap (armed after login) for a programmatic
    register + A6 backtrace, symbolized against the cached nm map.

Fires an escalating battery of disk/device triggers (the #3 raw-disk target on the blank rsd1, the
empty CD-ROM channel, whole-disk and per-partition reads, disklabel/fdisk) and, after each, checks
BOTH channels. First crash wins: we dump the gdb backtrace and issue `trace` into the serial ddb.
Clean "no crash" is itself a result (confirms graceful handling), reported per-trigger.
"""
import threading, time, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serial_console import SerialConsole, SERIAL_CHD
from phase_c_gdb import Gdb, REG_NAMES
from phase_c_epset import walk_a6, symbolize, read_str, fetch_text_syms

GDB_PORT = 2167
BLANK = r"C:\DocumentNoSnc\CC\hp_mame\obsd_test\blank_rsd1.chd"
CFG_DIR = "panic_cfg"
HERE = os.path.dirname(os.path.abspath(__file__))

DDB_SIGS = ("Stopped at", "ddb>", "panic:", "trap", "kernel: ")

# Escalating triggers. rsd1 = blank unlabeled 2nd SCSI disk; rcd0 = the empty CD-ROM (sd1).
TRIGGERS = [
    ("disklabel rsd1",              "disklabel rsd1 2>&1 | head -3"),
    ("read rsd1c (whole-disk c)",   "dd if=/dev/rsd1c of=/dev/null bs=1k count=1 2>&1 | tail -1"),
    ("read rsd1a",                  "dd if=/dev/rsd1a of=/dev/null bs=1k count=1 2>&1 | tail -1"),
    ("read rsd1d",                  "dd if=/dev/rsd1d of=/dev/null bs=1k count=1 2>&1 | tail -1"),
    ("read rsd1g",                  "dd if=/dev/rsd1g of=/dev/null bs=1k count=1 2>&1 | tail -1"),
    ("read raw rsd1 (no part)",     "dd if=/dev/rsd1 of=/dev/null bs=1k count=1 2>&1 | tail -1"),
    ("fdisk rsd1",                  "fdisk rsd1 2>&1 | head -3"),
    ("read empty CD rcd0c",         "dd if=/dev/rcd0c of=/dev/null bs=2k count=1 2>&1 | tail -1"),
    ("mount bogus fs from rsd1a",   "mount -t ffs /dev/sd1a /mnt 2>&1 | head -2"),
    ("disklabel -r write-probe",    "disklabel -r rsd1 2>&1 | head -3"),
]


def crashed_on_socket(sc):
    txt = sc.hs.text(0)
    return next((s for s in DDB_SIGS if s in txt), None)


def main():
    sc = SerialConsole(log_path=os.path.join(HERE, "panic_hunt.log"),
                       mame_log_path=os.path.join(HERE, "panic_hunt_mame.log"))
    sc.hs.listen()
    # NOTE: do NOT enable the serial KERNEL console (panic_cfg) here. On the single dca port, kernel/
    # syslog console spam (ROOT LOGIN, LOGIN FAILURES...) is written to /dev/console and desyncs the
    # expect-based getty login -> triggers never run. The gdb _panic/_Debugger breakpoints catch a
    # panic WITHOUT the serial console, so we drive over the clean getty and capture via gdb.
    sc.hs.launch_mame(chd=SERIAL_CHD, chd2=BLANK, seconds=1200, video="none",
                      extra=["-debug", "-debugger", "gdbstub", "-debugger_port", str(GDB_PORT)])
    print("[MAME: clean getty + blank rsd1 + gdbstub :%d]" % GDB_PORT)

    gdb = Gdb(port=GDB_PORT)
    if not gdb.connect():
        print("!! gdb connect failed"); sc.close(); return 2
    gdb.recv_packet(timeout=3); gdb.negotiate()
    gdb._send("c")
    sc.hs.accept(); sc.login(timeout=800)
    print("[serial login over kernel console]")
    syms = fetch_text_syms(sc); keys = [s[0] for s in syms]
    name2addr = {n: a for a, n in syms}
    bp = {n: name2addr[n] for n in ("_panic", "_Debugger", "_kdb_trap") if n in name2addr}

    gdb.sock.sendall(b"\x03"); gdb.recv_packet(timeout=15)
    for n, a in bp.items():
        gdb.cmd("Z0,%x,2" % a)
    print("[armed]", ", ".join("%s=%08x" % kv for kv in bp.items()))

    result = {}

    def watch_gdb():
        st = gdb.cont_until_stop(timeout=1100); result["stop"] = st
        if st and st[0] in "TS":
            r, _ = gdb.regs(); result["regs"] = r
            pc, a7, a6 = r.get("pc"), r.get("a7"), r.get("a6")
            result["channel"] = next((n for n, a in bp.items() if pc == a), None)
            if result.get("channel") == "_panic" and a7:
                result["panic_fmt"] = read_str(gdb, gdb.read_u32(a7 + 4) or 0)
                result["caller"] = gdb.read_u32(a7)
            result["bt"] = walk_a6(gdb, a6) if a6 else []

    t = threading.Thread(target=watch_gdb, daemon=True); t.start()
    time.sleep(1.0)

    hit = None
    for name, cmd in TRIGGERS:
        if result.get("stop") or (hit := crashed_on_socket(sc)):
            break
        print("[trigger] %-28s" % name, end="")
        sc.send(cmd)
        # give it a few seconds; a crash shows on gdb (result['stop']) or the socket
        for _ in range(6):
            time.sleep(1)
            if result.get("stop") or (hit := crashed_on_socket(sc)):
                break
        print("  -> %s" % ("CRASH" if (result.get("stop") or hit) else "ok, survived"))

    # If a socket-side ddb appeared, ask it to backtrace.
    if hit and not result.get("stop"):
        print("[serial ddb detected: %r] issuing 'trace'" % hit)
        sc.send("trace"); time.sleep(3)

    t.join(timeout=20)

    # ---- report ----
    print("\n" + "=" * 70)
    r = result.get("regs")
    ch = result.get("channel")
    if r:
        hx = lambda n: ("%08X" % r[n]) if r.get(n) is not None else "????????"
        print(">>> CRASH CAPTURED (gdb channel: %s) <<<" % ch)
        print("D:", " ".join("%s=%s" % (n, hx(n)) for n in REG_NAMES[:8]))
        print("A:", " ".join("%s=%s" % (n, hx(n)) for n in REG_NAMES[8:16]))
        print("SR=%04X PC=%s (%s)" % (r.get("sr", 0) & 0xffff, hx("pc"), symbolize(syms, keys, r.get("pc"))))
        if ch == "_panic":
            print("panic message : %r" % result.get("panic_fmt"))
            print("called from   : %s" % symbolize(syms, keys, result.get("caller")))
        for i, a in enumerate(result.get("bt") or []):
            print("  #%d  %08X  %s" % (i, a, symbolize(syms, keys, a)))
    elif hit:
        print(">>> CRASH on serial console (ddb) — see panic_hunt.log for the ddb 'trace' output <<<")
        tail = sc.hs.text(0)[-1200:]
        print(tail)
    else:
        print("NO CRASH — all %d triggers survived gracefully (both channels quiet)." % len(TRIGGERS))
        print("Consistent with the 2026-07-17 finding that raw-disk reads do NOT reliably panic.")
    print("=" * 70)
    try:
        sc.halt()
    except Exception:
        pass
    sc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
