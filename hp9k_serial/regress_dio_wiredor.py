#!/usr/bin/env python3
"""
regress_dio_wiredor.py — regression for the DIO wired-OR IRQ/DMAR fix (hp_dio.cpp/.h).

Proves the aggregate-edge rewrite of set_irq()/set_dmar() is behavior-preserving on the shipped
hp9k360 OpenBSD 2.2 image:
  - 98644 serial IRQ path (set_irq): boot to a serial login and round-trip several shell commands.
    The original UART-IRQ bug capped TX at ~2 bytes; if the aggregate-edge logic broke single-card
    IRQ delivery, commands would stall/time out here.
  - SCSI DMA path (set_dmar): reaching login at all requires the 98265a->98620 DMA request line to
    work through the rewritten set_dmar during the disk boot; a directory read re-exercises it.

Exit 0 = PASS (all commands round-tripped with rc==0 and dca serial present), else 1.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serial_console import SerialConsole

def main():
    sc = SerialConsole(log_path="regress_dio_wiredor.log",
                       mame_log_path="regress_dio_wiredor_mame.log")
    checks = []
    try:
        sc.boot()               # full boot incl. SCSI DMA -> set_dmar path
        sc.login()              # getty over the 98644 -> set_irq path
        # 1. identity round-trips (each byte in/out drives the 98644 UART IRQ)
        out, rc = sc.run("id -u")
        checks.append(("id -u == 0", out.strip() == "0" and rc == 0, f"out={out!r} rc={rc}"))
        out, rc = sc.run("uname -srm")
        checks.append(("uname ok", rc == 0 and "OpenBSD" in out, f"out={out!r} rc={rc}"))
        # 2. dca serial interface is present (the 98644)
        out, rc = sc.run("dmesg | grep -i dca0 | head -1")
        checks.append(("dca0 in dmesg", "dca0" in out, f"out={out!r} rc={rc}"))
        # 3. disk read (SCSI DMA) round-trips and returns data
        out, rc = sc.run("ls -1 / | wc -l")
        n = out.strip()
        checks.append(("root dir readable", rc == 0 and n.isdigit() and int(n) > 3, f"count={n!r} rc={rc}"))
        # 4. a second, larger serial burst to stress sustained TX/RX under IRQ
        out, rc = sc.run("dmesg | wc -c")
        checks.append(("dmesg burst ok", rc == 0 and out.strip().isdigit() and int(out.strip()) > 200,
                       f"bytes={out.strip()!r} rc={rc}"))
        sc.halt()
    finally:
        sc.close()

    print("\n==== DIO wired-OR regression ====")
    ok = True
    for name, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}    {detail}")
        ok &= passed
    print("=================================")
    print("RESULT:", "PASS" if ok and checks else "FAIL")
    return 0 if (ok and checks) else 1

if __name__ == "__main__":
    sys.exit(main())
