#!/usr/bin/env python3
"""
Step-0 probe: WHICH guest /dev node reaches host socket 1250 over the sl2:98644 serial line?

Launches the PATCHED hp9k360 (hp9k_patched_0288.exe, -sl4 98265a so the SCSI disk boots) on the WORK
CHD, drives probe_nodes.lua (natkeyboard) to echo a distinct marker to each CALL-OUT node /dev/cuaN,
and reports which marker(s) arrive on the serial socket.

Zero bytes is treated as INCONCLUSIVE, not proof of "no node": login/timing/MAKEDEV/carrier/reader/MAME
failures all look the same on the wire. When inconclusive, read the out-of-band snapshot
(hp_mame\\mame\\snap\\hp9k360\\) and the MAME log for ground truth.

Exit: 0 = a node identified; 1 = inconclusive (connected, no marker); 2 = MAME never connected / died.
"""
import re, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hp_ser_io import HpSerial, PORT

HERE = os.path.dirname(os.path.abspath(__file__))
LUA = os.path.join(HERE, "probe_nodes.lua")
LOG = os.path.join(HERE, "probe_serial_path.log")           # raw serial
MAME_LOG = os.path.join(HERE, "probe_mame_stdout.log")      # MAME's own stdout/stderr
SECONDS = 360   # emulated; boot-to-login ~206 + widened probe phases ~97 + margin


def _mame_log_tail(n=1200):
    try:
        with open(MAME_LOG, "rb") as f:
            return f.read()[-n:].decode("latin1", "replace")
    except OSError:
        return "(no MAME log)"


def main():
    hs = HpSerial(log_path=LOG, mame_log_path=MAME_LOG).listen()
    print("[listening on 127.0.0.1:%d]" % PORT)
    hs.launch_mame(lua=LUA, seconds=SECONDS, video="none")   # -video none still snapshots on this build
    print("[launched patched MAME hp9k360 on serial_work.chd + probe_nodes.lua]")

    if not hs.accept():
        print("!! %s" % hs.connect_error)
        print("   => MAME-side problem (launch/args/crash), NOT a guest-node question. MAME log tail:")
        print(_mame_log_tail())
        hs.close()
        return 2
    print("[serial socket connected -- MAME's 98644 reached the host]")

    status = hs.wait_mame(timeout=SECONDS + 150)
    hs.drain_and_join()                                      # consume the final marker burst, then parse
    text = hs.text()
    nodes = sorted(set(re.findall(r"HPSER_NODE_(\w+?)_END", text)))

    print("\n" + "=" * 66)
    print("MAME exit: %s | serial bytes: %d | log: %s" % (status, len(hs.buf), LOG))
    if nodes:
        print("NODE(S) REACHING THE HOST SOCKET: %s" % ", ".join("/dev/" + n for n in nodes))
        print(">>> Phase B: enable a getty on /dev/%s (dial-in /dev/tty%s) in the guest /etc/ttys."
              % (nodes[0], nodes[0].replace("cua", "")))
        rc = 0
    else:
        print("INCONCLUSIVE -- no HPSER_NODE marker arrived. This is NOT proof of 'no mapped node':")
        print("  causes that look identical on the wire: boot drift lost the login, MAKEDEV made no")
        print("  node, carrier block, reader race, or a MAME fault. Check ground truth:")
        print("   - snapshot: hp_mame\\mame\\snap\\hp9k360\\  (dmesg dca enumeration + /dev/cua* listing)")
        print("   - MAME log: %s" % MAME_LOG)
        if len(hs.buf):
            print("  Some bytes DID arrive; tail: %r" % text[-400:])
        else:
            print("  Zero bytes: if the socket connected but nothing came, the guest likely never")
            print("  reached/executed the marker loop (boot/login/timing), or no cua unit is wired here.")
        rc = 1
    print("=" * 66)
    hs.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
