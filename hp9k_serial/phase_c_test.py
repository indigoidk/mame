#!/usr/bin/env python3
"""
Phase C validation: boot the serial console WITH the m68k trap hook (phase_c_trap.lua) armed, then over
serial compile + run a userspace NULL write (*(int*)0 = 0x41424344). That faults the m68k -> the hook's
vector read-tap fires and dumps D0-D7/A0-A7/PC/SR to m68k_trap.log. Expected in the dump: A0=0 (the fault
address) and 0x41424344 in a D-register (the value being stored) -> proves the capture reflects the
faulting instruction. This is the m68k crash-capture that unblocks #239/#87 (guest cores don't dump).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serial_console import SerialConsole

HERE = os.path.dirname(os.path.abspath(__file__))
LUA = os.path.join(HERE, "m68k_fault.lua")
TRAPLOG = os.path.join(HERE, "m68k_faults.log")


def main():
    try:
        os.remove(TRAPLOG)
    except OSError:
        pass
    sc = SerialConsole(log_path=os.path.join(HERE, "phase_c.log"),
                       mame_log_path=os.path.join(HERE, "phase_c_mame.log"))
    try:
        sc.boot(seconds=700, lua=LUA, extra=["-debug", "-debugger", "none"]).login(timeout=600)
        print("[serial up + exception-point hook armed -> building a NULL-write faulter and running it]\n")
        sc.run(r"printf 'int main(){volatile int *p=(int*)0; *p=0x41424344; return 0;}\n' > /tmp/nd.c", timeout=40)
        cc, _ = sc.run("cc /tmp/nd.c -o /tmp/nd 2>&1; echo CC=$?", timeout=180)
        print("compile:", cc.strip())
        run, _ = sc.run("/tmp/nd; echo EXIT=$?", timeout=60)
        print("run    :", run.strip())
        sc.run("sleep 1")   # let the trap dump flush
        sc.halt()
    except Exception as e:
        print("!! driver error:", e)
    finally:
        sc.close()

    print("\n" + "=" * 64)
    print("=== m68k_trap.log (captured at the fault) ===")
    try:
        log = open(TRAPLOG).read()
        print(log)
        ok = "0x41424344" in log.lower() or "41424344" in log
        print("CAPTURE VALID:", "YES — 0x41424344 present in a register (faulting store operand)"
              if ok else "check the dump above (no 41424344 match)")
    except OSError:
        print("(no m68k_trap.log — the hook may not have fired; check phase_c_mame.log)")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
