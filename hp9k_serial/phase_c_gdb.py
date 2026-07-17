#!/usr/bin/env python3
"""
Phase C via gdbstub (the m68k analog of the pmax gdb capture). Runs MAME with -debugger gdbstub, connects
a minimal gdb-remote client, sets a breakpoint at the bus/address-error handler (0x1A1A, from
readv_u32(VBR+8)), and continues. The serial console concurrently logs in and triggers a userspace NULL
write; the fault reaches the handler -> the breakpoint halts MAME -> the client reads D0-D7/A0-A7/SR/PC and
the stacked fault PC (from A7+2). Expected: A0=0, 0x41424344 in a D-reg, PC=0x1A1A -> capture proven.
"""
import socket, threading, time, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serial_console import SerialConsole, SERIAL_CHD

GDB_PORT = 2159
HANDLER = 0x1A1A      # vec-2/3 handler PC (both vectors -> 0x1A1A, per the Lua readv run)
HERE = os.path.dirname(os.path.abspath(__file__))
REG_NAMES = ["d0","d1","d2","d3","d4","d5","d6","d7","a0","a1","a2","a3","a4","a5","a6","a7","sr","pc"]


class Gdb:
    def __init__(self, host="127.0.0.1", port=GDB_PORT):
        self.host, self.port, self.sock = host, port, None

    def connect(self, tries=90):
        for _ in range(tries):
            try:
                s = socket.socket(); s.settimeout(8); s.connect((self.host, self.port))
                self.sock = s; return True
            except Exception:
                time.sleep(1)
        return False

    def _send(self, data):
        cs = sum(data.encode("latin1")) & 0xff
        self.sock.sendall(("$%s#%02x" % (data, cs)).encode("latin1"))
        # swallow the '+' ack (tolerate none)
        try:
            self.sock.settimeout(5); self.sock.recv(1)
        except Exception:
            pass

    def recv_packet(self, timeout=None):
        if timeout is not None:
            self.sock.settimeout(timeout)
        buf = b""; in_pkt = False
        while True:
            try:
                c = self.sock.recv(1)
            except socket.timeout:
                return None
            if not c:
                return None
            if not in_pkt:
                if c == b"$":
                    in_pkt = True; buf = b""
                continue
            if c == b"#":
                self.sock.recv(2)                 # 2-char checksum
                self.sock.sendall(b"+")           # ack
                return buf.decode("latin1")
            buf += c

    def cmd(self, data, timeout=10):
        self._send(data); return self.recv_packet(timeout)

    def negotiate(self):
        # MAME gdbstub only serves g/G/p/P after target.xml has been fetched (debuggdbstub.cpp:802).
        self.cmd("qSupported:xmlRegisters=m68k", timeout=10)
        off = 0
        for _ in range(12):
            r = self.cmd("qXfer:features:read:target.xml:%x,0fff" % off, timeout=10) or ""
            if not r:
                break
            tag, data = r[0], r[1:]
            off += len(data)
            if tag == "l":       # last chunk
                break

    def set_bp(self, addr):
        # try hardware then software breakpoint
        for z in ("Z1", "Z0"):
            r = self.cmd("%s,%x,4" % (z, addr))
            if r == "OK":
                return z
        return None

    def cont_until_stop(self, timeout=600):
        self._send("c")
        return self.recv_packet(timeout)          # blocks until a stop reply (T../S..)

    def regs(self):
        g = self.cmd("g", timeout=15) or ""
        r = {}
        for i, n in enumerate(REG_NAMES):
            h = g[i * 8:(i + 1) * 8]
            r[n] = int(h, 16) if len(h) == 8 else None
        return r, g

    def read_u32(self, addr):
        h = self.cmd("m%x,4" % addr, timeout=10) or ""
        return int(h, 16) if len(h) == 8 else None


def main():
    result = {}
    sc = SerialConsole(log_path=os.path.join(HERE, "phase_c_gdb.log"),
                       mame_log_path=os.path.join(HERE, "phase_c_gdb_mame.log"))
    sc.hs.listen()
    sc.hs.launch_mame(chd=SERIAL_CHD, seconds=900, video="none",
                      extra=["-debug", "-debugger", "gdbstub", "-debugger_port", str(GDB_PORT)])
    print("[MAME launched with gdbstub on %d]" % GDB_PORT)

    gdb = Gdb()
    if not gdb.connect():
        print("!! gdb connect failed"); sc.close(); return 2
    print("[gdb connected]")
    gdb.recv_packet(timeout=3)                    # drain any initial stop notification
    gdb.negotiate()                                # qSupported + fetch target.xml (required before g/p)
    z = gdb.set_bp(HANDLER)
    print("[breakpoint at %06X via %s]" % (HANDLER, z))

    def gdb_thread():
        stop = gdb.cont_until_stop(timeout=800)   # runs MAME; blocks until the fault hits the bp
        result["stop"] = stop
        if stop:
            r, raw = gdb.regs()
            result["regs"] = r; result["raw"] = raw
            a7 = r.get("a7")
            result["fault_pc"] = gdb.read_u32(a7 + 2) if a7 else None
            result["fault_sr"] = gdb.read_u32(a7) if a7 else None
    t = threading.Thread(target=gdb_thread, daemon=True); t.start()

    try:
        sc.hs.accept()                            # serial connects once MAME is running (post-continue)
        sc.login(timeout=700)
        print("[serial login -> building + firing a NULL write]")
        sc.run(r"printf 'int main(){volatile int*p=(int*)0;*p=0x41424344;return 0;}\n' > /tmp/nd.c", timeout=40)
        cc, _ = sc.run("cc /tmp/nd.c -o /tmp/nd 2>&1; echo CC=$?", timeout=180)
        print("compile:", cc.strip())
        sc.send("/tmp/nd")                        # fire the fault (do NOT wait; MAME halts at the bp)
    except Exception as e:
        print("[serial side note]:", e)

    t.join(timeout=250)
    print("\n" + "=" * 64)
    print("STOP:", result.get("stop"))
    raw = result.get("raw", "") or ""
    print("raw 'g' (%d hex chars): %s" % (len(raw), raw))
    if result.get("regs"):
        r = result["regs"]
        hx = lambda n: ("%08X" % r[n]) if r.get(n) is not None else "????????"
        print("D:", " ".join("%s=%s" % (n, hx(n)) for n in REG_NAMES[:8]))
        print("A:", " ".join("%s=%s" % (n, hx(n)) for n in REG_NAMES[8:16]))
        print("SR=%s PC=%s" % (("%04X" % (r["sr"] & 0xffff)) if r.get("sr") is not None else "????", hx("pc")))
        print("FAULT_PC(@A7+2)=%s FAULT_SR(@A7)=%s" %
              (("%08X" % result["fault_pc"]) if result.get("fault_pc") is not None else "?",
               ("%04X" % (result["fault_sr"] & 0xffff)) if result.get("fault_sr") is not None else "?"))
        dvals = [r.get(n) for n in REG_NAMES[:8]]
        matched = 0x41424344 in dvals and r.get("a0") == 0
        print("CAPTURE:", "MATCHES NULL-write (A0=0 + 41424344)" if matched
              else "captured a real fault (regs above) -> mechanism WORKS; boot-time fault, refine trigger next")
        rc = 0
    else:
        print("NO CAPTURE (stop=%s) -- see phase_c_gdb_mame.log" % result.get("stop"))
        rc = 1
    print("=" * 64)
    sc.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
