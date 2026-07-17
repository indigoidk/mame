#!/usr/bin/env python3
"""
#4 recon: attach the blank unlabeled disk as a 2nd SCSI disk (rsd1) and identify the disks over serial,
WITHOUT reading the raw device yet (that's the panic trigger, done separately with the register hook).
Confirms: (a) the guest still boots with a label-less 2nd disk attached (i.e. boot-time probe doesn't
panic), and (b) which /dev/sdN / rsdN is the blank one to target for the raw-disk-panic repro.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serial_console import SerialConsole

HERE = os.path.dirname(os.path.abspath(__file__))
BLANK = r"C:\DocumentNoSnc\CC\hp_mame\obsd_test\blank_rsd1.chd"


def main():
    sc = SerialConsole(log_path=os.path.join(HERE, "phase4_recon.log"),
                       mame_log_path=os.path.join(HERE, "phase4_recon_mame.log"))
    try:
        sc.boot(seconds=440, chd2=BLANK).login()
        print("[booted WITH label-less 2nd SCSI disk -> boot-probe did NOT panic; identifying disks]\n")
        for cmd in ["dmesg | grep -iE 'sd[0-9]|scsibus|SCSI' | head -12",
                    "ls -l /dev/rsd0c /dev/rsd1c /dev/sd0c /dev/sd1c 2>&1",
                    "sysctl hw.disknames 2>/dev/null; ls /dev/rsd* 2>/dev/null | head"]:
            out, rc = sc.run(cmd, timeout=30)
            print("$ %s   (rc=%s)\n%s\n----------" % (cmd, rc, out.strip()))
        sc.halt()
        print("\n=> next: read /dev/rsd1c (the blank) to trigger the panic + capture m68k regs via the hook.")
        return 0
    except Exception as e:
        print("!! recon error:", e)
        try:
            print("tail:", repr(sc.hs.text()[-500:]))
        except Exception:
            pass
        return 1
    finally:
        sc.close()


if __name__ == "__main__":
    sys.exit(main())
