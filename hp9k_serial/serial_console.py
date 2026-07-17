#!/usr/bin/env python3
"""
serial_console.py — reusable serial-console session for MAME-HP over the socket.

Boots the persistent serial CHD (obsd22_serial.chd, which auto-runs a getty on /dev/tty0 — no Lua/
natkeyboard needed), logs in as root over the socket, disables terminal echo for clean capture, and
runs shell commands returning their output. This is the foundation for porting the fire batch off the
natkeyboard(~10 cps)+PNG-snapshot method to clean serial text I/O.

Usage:
    from serial_console import SerialConsole
    sc = SerialConsole(log_path="sess.log").boot().login()
    print(sc.run("uname -a"))
    print(sc.run("rpcinfo -p 127.0.0.1"))
    sc.halt(); sc.close()
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hp_ser_io import HpSerial

SERIAL_CHD = r"C:\DocumentNoSnc\CC\hp_mame\obsd_test\obsd22_serial.chd"


class SerialConsole:
    def __init__(self, log_path=None, mame_log_path=None):
        self.hs = HpSerial(log_path=log_path, mame_log_path=mame_log_path)
        self._n = 0

    def boot(self, seconds=600):
        self.hs.listen()
        # NO -autoboot_script: the baked-in getty presents login: over serial on its own.
        self.hs.launch_mame(chd=SERIAL_CHD, seconds=seconds, video="none")
        if not self.hs.accept():
            raise RuntimeError("MAME did not connect: %s" % self.hs.connect_error)
        return self

    def login(self, user="root", timeout=260):
        if not self.hs.expect(r"login:", timeout=timeout):
            raise RuntimeError("no serial login: prompt (getty didn't come up)")
        self.hs.send(user)
        # 'unknown' terminal type -> login asks "Terminal type? [unknown]"; take the default.
        self.hs.expect(r"[Tt]erminal|TERM|[%#\$]", timeout=25)
        self.hs.send("")
        self.hs.expect(r"[%#\$]", timeout=25)
        self.hs.send("/bin/sh")
        self.hs.expect(r"[#\$]", timeout=15)
        self.hs.send("stty sane; stty -echo")   # -echo => captured serial is command OUTPUT only
        self.hs.wait(1)
        return self

    def run(self, cmd, timeout=45):
        """Run a shell command; return its stdout (echo disabled, so no input echo in the capture)."""
        self._n += 1
        tag = "__RC_%d__" % self._n
        mark = self.hs.mark()
        self.hs.send("%s; echo %s$?" % (cmd, tag))
        got = self.hs.expect(re.escape(tag) + r"(\d+)", timeout=timeout, since=mark)
        raw = self.hs.text(mark)
        out = re.split(tag, raw)[0]
        rc = int(got.group(1)) if got else None
        # normalize CRLF and trim
        return out.replace("\r\n", "\n").replace("\r", "\n").strip("\n"), rc

    def send(self, s, **kw):
        return self.hs.send(s, **kw)

    def expect(self, pat, timeout=30, since=None):
        return self.hs.expect(pat, timeout=timeout, since=since)

    def halt(self):
        try:
            self.hs.send("sync; halt")
        except Exception:
            pass
        self.hs.wait_mame(timeout=90)
        self.hs.drain_and_join()

    def close(self):
        self.hs.close()
