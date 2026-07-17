#!/usr/bin/env python3
"""
#3 (raw-disk panic) + Phase C targeted capture. Boots WITH the blank unlabeled 2nd SCSI disk (rsd1),
logs in over serial, then ARMS the m68k bus-error breakpoint AFTER boot (so it catches the intended
fault, not a boot-time device-probe bus error), fires the raw-disk read (`dd if=/dev/rsd1c ...`), and
captures the crash registers via gdbstub. FAULT_PC tells us WHERE in the kernel sd/scsi path it faults
-> whether the "bad kernel read at 0x0" is a real OpenBSD 2.2 hp300 defect.
"""
import sys, os, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serial_console import SerialConsole, SERIAL_CHD
from phase_c_gdb import Gdb, REG_NAMES, HANDLER, GDB_PORT

HERE = os.path.dirname(os.path.abspath(__file__))
BLANK = r"C:\DocumentNoSnc\CC\hp_mame\obsd_test\blank_rsd1.chd"


def arm_after_boot_and_capture(sc, gdb, trigger_cmd, label):
    """Interrupt the running (booted) guest, set the bus-error bp, continue, fire trigger_cmd over serial,
    and capture registers when the bp halts MAME."""
    result = {}
    gdb.sock.sendall(b"\x03")                     # interrupt the running target
    gdb.recv_packet(timeout=15)                   # consume the interrupt stop reply
    z = gdb.set_bp(HANDLER)
    print("[%s: armed bp @ %06X via %s]" % (label, HANDLER, z))

    def cap():
        st = gdb.cont_until_stop(timeout=300)     # runs the guest; blocks until the bp fires
        result["stop"] = st
        if st and st.startswith("T"):
            r, raw = gdb.regs()
            result["regs"], result["raw"] = r, raw
            a7 = r.get("a7")
            if a7:
                w0 = gdb.read_u32(a7)             # frame word0=SR(hi16), long PC@+2
                result["fault_sr"] = (w0 >> 16) & 0xffff if w0 is not None else None
                result["fault_pc"] = gdb.read_u32(a7 + 2)
    t = threading.Thread(target=cap, daemon=True); t.start()
    time.sleep(1.0)
    sc.send(trigger_cmd)                          # fire the fault (do NOT wait; MAME halts at the bp)
    t.join(timeout=200)
    return result


def main():
    sc = SerialConsole(log_path=os.path.join(HERE, "phase4_panic.log"),
                       mame_log_path=os.path.join(HERE, "phase4_panic_mame.log"))
    sc.hs.listen()
    sc.hs.launch_mame(chd=SERIAL_CHD, chd2=BLANK, seconds=900, video="none",
                      extra=["-debug", "-debugger", "gdbstub", "-debugger_port", str(GDB_PORT)])
    print("[MAME launched: serial CHD + blank rsd1 + gdbstub :%d]" % GDB_PORT)

    gdb = Gdb()
    if not gdb.connect():
        print("!! gdb connect failed"); sc.close(); return 2
    gdb.recv_packet(timeout=3); gdb.negotiate()
    gdb._send("c")                                # continue -> MAME boots (bp NOT yet set)
    print("[gdb: continue -> booting]")

    try:
        sc.hs.accept()
        sc.login(timeout=700)
        print("[serial login]")
        dm, _ = sc.run("dmesg | grep -iE 'sd[0-9]' | head", timeout=40)
        print("disks:\n" + dm.strip())
        ls, _ = sc.run("ls -l /dev/rsd1c 2>&1", timeout=20)
        print("rsd1c:", ls.strip())
    except Exception as e:
        print("[serial pre-trigger note]:", e)

    # fire the raw-disk read of the UNLABELED rsd1 -> the panic (bad kernel read)
    res = arm_after_boot_and_capture(
        sc, gdb, "dd if=/dev/rsd1c of=/dev/null bs=512 count=1", "rawdisk")

    print("\n" + "=" * 66)
    print("STOP:", res.get("stop"))
    if res.get("regs"):
        r = res["regs"]
        hx = lambda n: ("%08X" % r[n]) if r.get(n) is not None else "????????"
        print("D:", " ".join("%s=%s" % (n, hx(n)) for n in REG_NAMES[:8]))
        print("A:", " ".join("%s=%s" % (n, hx(n)) for n in REG_NAMES[8:16]))
        print("SR=%04X  PC=%s (bus-error handler)" % (r["sr"] & 0xffff, hx("pc")))
        fp = res.get("fault_pc"); fs = res.get("fault_sr")
        print("FAULTING PC = %s   FAULT SR = %s" %
              (("%08X" % fp) if fp is not None else "?", ("%04X" % fs) if fs is not None else "?"))
        print("=> raw-disk panic characterized: the kernel faults at PC=%s reading unlabeled /dev/rsd1c."
              % (("%08X" % fp) if fp is not None else "?"))
        rc = 0
    else:
        print("no capture (stop=%s) -- the read may not have faulted, or bp missed; see logs" % res.get("stop"))
        rc = 1
    print("=" * 66)
    sc.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
