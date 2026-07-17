#!/usr/bin/env python3
"""
Verify the baked-in serial console + demo the fire-batch pattern over serial.

Boots obsd22_serial.chd with NO natkeyboard/Lua: if the getty line persisted into /etc/ttys, init
auto-spawns getty on /dev/tty0 and presents login: over the socket. We log in and run recon commands
(uname/id/rpcinfo) — exactly what the natkeyboard fire drivers did, but over clean serial text I/O.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serial_console import SerialConsole

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    sc = SerialConsole(log_path=os.path.join(HERE, "serial_console.log"),
                       mame_log_path=os.path.join(HERE, "serial_console_mame.log"))
    try:
        sc.boot(seconds=520)
        print("[booted obsd22_serial.chd; waiting for the BAKED-IN getty login: (no natkeyboard)]")
        sc.login()
        print("[logged in over serial -> running recon, capturing over the socket]\n")
        for cmd in ["uname -a",
                    "id",
                    "rpcinfo -p 127.0.0.1 2>&1 | head -8",
                    "ifconfig -a 2>&1 | grep -E 'flags|inet' | head -6"]:
            out, rc = sc.run(cmd)
            print("$ %s   (rc=%s)" % (cmd, rc))
            print(out.strip() or "(no output)")
            print("-" * 50)
        sc.halt()
        print("\n=== PERSISTENT SERIAL CONSOLE: WORKING ===")
        print("getty auto-ran from the baked /etc/ttys; logged in + ran recon over the socket, no natkeyboard.")
        return 0
    except Exception as e:
        print("!! FAILED:", e)
        try:
            print("tail:", repr(sc.hs.text()[-500:]))
        except Exception:
            pass
        return 1
    finally:
        sc.close()


if __name__ == "__main__":
    sys.exit(main())
