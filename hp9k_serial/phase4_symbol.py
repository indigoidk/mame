#!/usr/bin/env python3
"""#3 capstone: map the raw-disk-panic faulting PC (0x00010C26) to its kernel function via nm /bsd
(addresses are zero-padded hex, so string <= comparison == numeric). Tells us which OpenBSD 2.2 hp300
routine null-derefs when reading an unlabeled raw disk."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serial_console import SerialConsole

FAULT_PC = "00010c26"


def main():
    sc = SerialConsole(log_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "phase4_symbol.log"))
    try:
        sc.boot(seconds=440).login()
        # last text-symbol at/below the faulting PC = the faulting function
        out, _ = sc.run("nm -n /bsd 2>/dev/null | grep -E ' [tT] ' | awk '$1 <= \"%s\"' | tail -4" % FAULT_PC, timeout=60)
        nxt, _ = sc.run("nm -n /bsd 2>/dev/null | grep -E ' [tT] ' | awk '$1 > \"%s\"' | head -1" % FAULT_PC, timeout=60)
        sc.halt()
        print("=" * 60)
        print("FAULTING PC 0x%s falls in:" % FAULT_PC)
        print("--- symbols at/below the fault (last = the function) ---")
        print(out.strip())
        print("--- next symbol above ---")
        print(nxt.strip())
        print("=" * 60)
        return 0
    except Exception as e:
        print("!! error:", e)
        return 1
    finally:
        sc.close()


if __name__ == "__main__":
    sys.exit(main())
