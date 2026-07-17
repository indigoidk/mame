#!/usr/bin/env python3
"""
serial_kernel_console.py — thread 4: make the OpenBSD 2.2 KERNEL/DDB console the serial dca.

Mechanism (verified against hp300 dca.c:dca_console_scan + dev/cons.h):
  the ite framebuffer console is CN_INTERNAL(2); the dca only outranks it if its ID register reads
  a REMOTE id (DCAREMID0=0x82 / DCAREMID1=0xC2) => CN_REMOTE(3). MAME's 98644 ID = 0x02|0x80(Remote)
  = 0x82 = DCAREMID0. So enabling the 98644 "Remote" DIP (via panic_cfg/hp9k360.cfg, a SEPARATE
  cfg dir so the normal getty harness is unaffected) makes the kernel pick the dca as console.

This confirms it: boot with -cfg_directory panic_cfg and check whether KERNEL boot messages (not just
the getty login) arrive on the socket. If they do, a panic/DDB session will likewise print there.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hp_ser_io import HpSerial
from serial_console import SERIAL_CHD

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_DIR = "panic_cfg"     # relative to the MAME cwd (hp_mame), holds the Remote-DIP hp9k360.cfg

# Kernel-console signatures that only appear on the socket if the dca IS the kernel console.
# (Currently, with the framebuffer console, the socket is silent until getty prints "login:".)
KERNEL_SIGS = ["OpenBSD 2.2 (GENERIC)", "real mem", "avail mem", "dca0 at", "root on", "Copyright (c)"]


def main():
    hs = HpSerial(log_path=os.path.join(HERE, "serial_kernel_console.log"),
                  mame_log_path=os.path.join(HERE, "serial_kernel_console_mame.log"))
    hs.listen()
    hs.launch_mame(chd=SERIAL_CHD, seconds=200, video="none",
                   extra=["-cfg_directory", CFG_DIR])
    print("[MAME: serial CHD + -cfg_directory %s (Remote DIP on)]" % CFG_DIR)
    if not hs.accept():
        print("!! MAME did not connect:", hs.connect_error); hs.close(); return 2

    # Capture the boot for ~110s and inspect what reached the socket.
    print("[capturing boot output on socket ~110s]")
    for _ in range(110):
        if hs.proc.poll() is not None:
            break
        time.sleep(1)
    data = hs.text(0)

    found = [s for s in KERNEL_SIGS if s in data]
    print("\n" + "=" * 70)
    print("bytes on socket: %d" % len(data))
    print("kernel-console signatures found: %s" % found)
    # Show the first kernel-ish lines for evidence
    lines = [ln for ln in data.replace("\r", "").split("\n") if ln.strip()]
    print("--- first 25 non-blank lines on socket ---")
    for ln in lines[:25]:
        print("  " + ln)
    print("=" * 70)
    ok = len(found) >= 2
    print("RESULT:", "PASS - dca is the kernel console; panic/DDB text now reaches the socket"
          if ok else "FAIL - socket saw no kernel console output (DIP/cfg not applied?)")
    try:
        hs.close()
    except Exception:
        pass
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
