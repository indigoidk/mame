#!/usr/bin/env python3
"""
Phase B core test: log in over the serial socket (NO natkeyboard). phaseb_getty.lua adds a getty on
/dev/tty0 and HUPs init; this waits for the serial "login:" and drives root login + a shell command,
proving a real bidirectional serial console.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hp_ser_io import HpSerial

HERE = os.path.dirname(os.path.abspath(__file__))
LUA = os.path.join(HERE, "phaseb_getty.lua")


def main():
    hs = HpSerial(log_path=os.path.join(HERE, "phaseb_getty.log"),
                  mame_log_path=os.path.join(HERE, "phaseb_getty_mame.log")).listen()
    hs.launch_mame(lua=LUA, seconds=460, video="none")
    if not hs.accept():
        print("ACCEPT FAIL:", hs.connect_error); hs.close(); return 2

    if not hs.expect(r"login:", timeout=240):
        print("!! no serial 'login:' prompt (getty didn't come up)"); hs.wait_mame(60); hs.drain_and_join()
        print("tail:", repr(hs.text()[-500:])); hs.close(); return 1
    print("[serial 'login:' seen -> logging in as root over the socket]")

    hs.send("root")
    # getty type 'unknown' -> login asks "Terminal type?"; answer with default (blank line). Harmless if
    # it was already a shell prompt.
    hs.expect(r"[Tt]erminal|TERM|[%#\$]", timeout=25)
    hs.send("")
    if not hs.expect(r"[%#\$]", timeout=25):
        print("!! no shell prompt after login"); print("tail:", repr(hs.text()[-500:]))
    hs.send("/bin/sh")
    hs.expect(r"[#\$]", timeout=15)
    hs.send("stty sane")
    mark = hs.mark()
    hs.send("echo SERIAL_CONSOLE_OK=$(id -u); uname -sr")
    ok = hs.expect(r"SERIAL_CONSOLE_OK=0", timeout=25, since=mark) is not None
    uname = hs.expect(r"OpenBSD", timeout=10, since=mark)
    # clean shutdown so the FFS on the work CHD isn't left dirty
    hs.send("sync; halt")

    hs.wait_mame(timeout=90)
    hs.drain_and_join()
    print("\n" + "=" * 64)
    print("SERIAL LOGIN CONSOLE: %s" % ("WORKING (logged in as uid 0 over serial)" if ok else "INCOMPLETE"))
    if uname:
        print("uname over serial:", uname.group(0))
    print("--- last 600 bytes of the serial session ---")
    print(hs.text()[-600:])
    print("=" * 64)
    hs.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
