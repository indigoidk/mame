#!/usr/bin/env python3
"""
Phase B step 1: validate bidirectional serial and capture the guest /etc/ttys over the (now working)
serial line. Drives phaseb_probe.lua: the guest cats /etc/ttys to /dev/tty0, then blocks reading a line
from /dev/tty0; this host sends "PING" and checks it echoes back as __RXGOT__[PING] -> RX confirmed.
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hp_ser_io import HpSerial

HERE = os.path.dirname(os.path.abspath(__file__))
LUA = os.path.join(HERE, "phaseb_probe.lua")


def main():
    hs = HpSerial(log_path=os.path.join(HERE, "phaseb.log"),
                  mame_log_path=os.path.join(HERE, "phaseb_mame.log")).listen()
    hs.launch_mame(lua=LUA, seconds=300, video="none")
    if not hs.accept():
        print("ACCEPT FAIL:", hs.connect_error); hs.close(); return 2
    print("[connected]")

    if not hs.expect("__TTYS_END__", timeout=180):
        print("!! never saw __TTYS_END__ (guest may not have reached the dump)")
    r = hs.expect("__RXREADY__", timeout=60)
    rx_ok = False
    if r:
        print("[guest is reading /dev/tty0 -> sending PING from host]")
        hs.send("PING")                                  # host -> guest, eol=\r
        rx_ok = hs.expect(r"__RXGOT__\[PING", timeout=40) is not None
    else:
        print("!! never saw __RXREADY__")

    hs.wait_mame(timeout=90)
    hs.drain_and_join()
    full = hs.text()

    print("\n" + "=" * 64)
    print("RX (host->guest): %s" % ("CONFIRMED" if rx_ok else "NOT CONFIRMED"))
    idx = full.find("__TTYS_END__")
    print("--- guest /etc/ttys (received over serial) ---")
    if idx > 0:
        # strip the connect banner + show the ttys body
        body = full[:idx]
        body = body.split("]\n", 1)[-1] if "]\n" in body[:60] else body
        print(body.strip()[-1600:])
    else:
        print("(not captured)")
    print("--- RX echo line ---")
    for line in full.splitlines():
        if "__RXGOT__" in line:
            print("  " + line)
    print("=" * 64)
    hs.close()
    return 0 if rx_ok else 1


if __name__ == "__main__":
    sys.exit(main())
