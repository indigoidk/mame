#!/usr/bin/env python3
"""
hp_ser_io.py -- bidirectional serial-console driver for MAME hp9k360 (OpenBSD 2.2, m68k).

The 98644 async serial card (DIO slot sl2) is wired in MAME as:
    -sl2 98644 -sl2:98644:rs232 null_modem -bitb socket.127.0.0.1:1250
`socket.HOST:PORT` makes MAME the TCP *client* that connects OUT to HOST:PORT -- VERIFIED empirically:
launching with `-bitb socket.127.0.0.1:<unused>` and no listener yields MAME
"Unable to load image 'socket...'" (a failed connect; a server would have bound silently). So THIS
side must LISTEN on 1250, accept MAME's one persistent connection, and drive login/commands over it,
replacing the natkeyboard(~10 cps)+PNG-snapshot ceiling with clean text I/O.

Launch facts from CC_HP-CDROM/RUN_OBSD22.md (the disk only boots on the PATCHED build; slot defaults
sl1=video sl2=serial sl3=98620-DMA sl4=SCSI sl5=free):
  exe = hp_mame\\hp9k_patched_0288.exe   (run with cwd = hp_mame, -rp mame\\roms)
  need -sl4 98265a (SCSI) + -skip_gameinfo; -video none still writes snapshots.

Guest node fact (guest MAKEDEV + dca.c): the 98644 is the `dca` driver -> /dev/tty0 (dial-in, char
major 12) and /dev/cua0 (call-out). A dial-in open BLOCKS on a DCD carrier MAME never asserts
(dca.c:381), so drive the CALL-OUT node /dev/cua0. (tty00-03 are DCM mux, major 15 -- a different card.)

Reviewed 2026-07-16 by Fable + Codex 5.6-SOL(ultra) + agy Gemini-3.1-Pro(High); their converging fixes
(no PIPE deadlock, poll MAME in accept, absolute expect() offsets, join reader before parse, log raw)
are applied below.
"""
import socket, subprocess, threading, time, re, sys, os

# --- asset locations (outside the mame repo; absolute so CWD is irrelevant) ---
MAME_EXE = r"C:\DocumentNoSnc\CC\hp_mame\hp9k_patched_0288.exe"  # patched: SCSI disk actually boots
MAME_DIR = r"C:\DocumentNoSnc\CC\hp_mame"                        # cwd: exe + mame\roms live here
GOLDEN_CHD = r"C:\DocumentNoSnc\CC\hp_mame\obsd_test\obsd22_disk.chd"  # never probe this directly
WORK_CHD = r"C:\DocumentNoSnc\CC\hp_mame\obsd_test\serial_work.chd"    # MAME writes here (a copy)
PORT = 1250


def mame_hp9k360_args(chd=WORK_CHD, chd2=None, port=PORT, lua=None, seconds=None,
                      video="none", extra=None):
    """Standard hp9k360 + 98644-serial-to-socket launch argv (the disk-booting recipe).
    chd2 attaches a SECOND SCSI disk at scsibus:5 (-> guest rsd1), for the raw-disk-panic repro (#3)."""
    a = [MAME_EXE, "hp9k360",
         "-rp", r"mame\roms",
         "-sl4", "98265a"]                 # SCSI controller (disk won't boot without it)
    if chd2:
        a += ["-sl4:98265a:scsibus:5", "harddisk", "-hard1", chd, "-hard2", chd2]
    else:
        a += ["-hard", chd]
    a += ["-sl2", "98644", "-sl2:98644:rs232", "null_modem",
         "-bitb", "socket.127.0.0.1:%d" % port,
         "-video", video, "-sound", "none", "-nothrottle", "-skip_gameinfo"]
    if lua:
        a += ["-autoboot_script", lua, "-autoboot_delay", "0"]
    if seconds:
        a += ["-seconds_to_run", str(seconds)]
    if extra:
        a += list(extra)
    return a


class HpSerial:
    """Host end of the 98644 serial line. Listens on `port`, (optionally) launches MAME (its stdout
    goes to a FILE, never an undrained PIPE), accepts the one persistent connection while polling the
    child, and runs a reader thread that logs RAW bytes but buffers 7-bit-masked bytes for matching."""

    def __init__(self, port=PORT, log_path=None, mame_log_path=None, echo=True):
        self.port = port
        self.log = open(log_path, "wb", 0) if log_path else None
        self.mame_log_path = mame_log_path
        self._mame_log = None
        self.echo = echo
        self.buf = bytearray()          # 7-bit-masked, for matching
        self.lock = threading.Lock()
        self.sock = None
        self.conn = None
        self.proc = None
        self.connect_error = None
        self._stop = False
        self._reader = None

    # -- lifecycle -----------------------------------------------------------
    def listen(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", self.port))
        self.sock.listen(1)
        return self

    def launch_mame(self, **kw):
        """Popen MAME with the serial wired to our port. MAME stdout/stderr -> a log FILE so the OS
        pipe buffer can never fill and deadlock the emulator (Fable/Codex/agy #1)."""
        if self.mame_log_path:
            self._mame_log = open(self.mame_log_path, "wb")
            out = self._mame_log
        else:
            out = subprocess.DEVNULL
        self.proc = subprocess.Popen(
            mame_hp9k360_args(port=self.port, **kw),
            cwd=MAME_DIR, stdout=out, stderr=subprocess.STDOUT)
        return self.proc

    def accept(self, connect_timeout=180):
        """Wait for MAME's connection, but bail early (with the child's exit code) if MAME dies first,
        instead of blocking the full timeout on a crashed launch (Codex/agy #4)."""
        self.sock.settimeout(2)
        t0 = time.time()
        while self.conn is None and time.time() - t0 < connect_timeout:
            try:
                self.conn, _ = self.sock.accept()
            except socket.timeout:
                if self.proc is not None and self.proc.poll() is not None:
                    self.connect_error = "MAME exited (code %s) before connecting" % self.proc.returncode
                    return False
                continue
            except OSError as e:
                self.connect_error = "accept error: %s" % e
                return False
        if self.conn is None:
            self.connect_error = "no connection within %ss" % connect_timeout
            return False
        self.conn.settimeout(1)
        self._log_meta(b"[serial socket connected]\n")
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        return True

    def _read_loop(self):
        while not self._stop:
            try:
                d = self.conn.recv(4096)
                if not d:
                    break
                if self.log:                     # log RAW (keep parity/framing evidence)
                    self.log.write(d)
                m = bytes(b & 0x7f for b in d)    # mask to clean ASCII for matching
                with self.lock:
                    self.buf.extend(m)
                if self.echo:
                    sys.stdout.buffer.write(m); sys.stdout.flush()
            except socket.timeout:
                continue
            except Exception as e:
                self._log_meta(("[reader: %s]\n" % e).encode())
                break

    def _log_meta(self, b):
        if self.log:
            self.log.write(b)
        if self.echo:
            sys.stdout.buffer.write(b); sys.stdout.flush()

    # -- I/O -----------------------------------------------------------------
    def mark(self):
        """Absolute buffer length. Capture this BEFORE send() so expect() can't miss a fast reply."""
        with self.lock:
            return len(self.buf)

    def _require_conn(self):
        if self.conn is None:
            raise RuntimeError("HpSerial: not connected -- call listen()/launch_mame()/accept() first")

    def send(self, s, eol="\r", slow=False, cps=10):
        """Write a line to the guest. slow=True types char-by-char (~cps) for ddb, whose 1-byte
        polled input drops burst-sent characters."""
        self._require_conn()
        data = (s + eol).encode("latin1")
        if slow:
            for ch in data:
                self.conn.sendall(bytes([ch])); time.sleep(1.0 / cps)
        else:
            self.conn.sendall(data)
        self._log_meta(b"\n[>> %s]\n" % s.encode("latin1", "replace"))

    def send_raw(self, b):
        """Send raw bytes (e.g. the single 0x1C ddb-escape)."""
        self._require_conn()
        self.conn.sendall(b)
        self._log_meta(b"\n[>> raw %r]\n" % b)

    def expect(self, pattern, timeout=30, since=None):
        """Wait until `pattern` (str/bytes regex) appears at/after absolute offset `since`. Returns the
        re.Match with ABSOLUTE indices (search the whole buffer with pos=start, never a slice), so
        chaining `since=m.end()` works (Fable/Codex/agy #3)."""
        pat = pattern.encode("latin1") if isinstance(pattern, str) else pattern
        rx = re.compile(pat)
        start = self.mark() if since is None else since
        t0 = time.time()
        while time.time() - t0 < timeout:
            with self.lock:
                data = bytes(self.buf)
            m = rx.search(data, start)          # pos=start keeps offsets absolute
            if m:
                return m
            if self.proc and self.proc.poll() is not None:
                self.drain_and_join()
                with self.lock:
                    data = bytes(self.buf)
                return rx.search(data, start)
            time.sleep(0.2)
        return None

    def text(self, since=0):
        with self.lock:
            return bytes(self.buf[since:]).decode("latin1", "replace")

    def wait(self, secs):
        time.sleep(secs)

    def drain_and_join(self, timeout=12):
        """Let the reader consume the final TCP burst (the markers) and terminate before anyone reads
        the buffer -- otherwise parse races the socket drain (Codex/agy #2). Call after wait_mame()."""
        r = self._reader
        if r and r.is_alive():
            r.join(timeout=timeout)
            if r.is_alive():                    # reader stuck (MAME didn't close socket) -> force it
                self._stop = True
                try:
                    self.conn.close()
                except Exception:
                    pass
                r.join(timeout=3)

    def wait_mame(self, timeout=None):
        if self.proc:
            try:
                return self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                return "TIMEOUT"

    def kill_mame(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=10)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass

    def close(self):
        self._stop = True
        self.kill_mame()                        # never strand MAME holding the CHD + port
        for c in (self.conn, self.sock):
            try:
                if c:
                    c.close()
            except Exception:
                pass
        for f in (self.log, self._mame_log):
            try:
                if f:
                    f.close()
            except Exception:
                pass


# --- CLI: quick monitor (launch MAME on the work CHD, log serial for N seconds) --------------------
if __name__ == "__main__":
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 360
    lua = sys.argv[2] if len(sys.argv) > 2 else None
    here = os.path.dirname(os.path.abspath(__file__))
    hs = HpSerial(log_path=os.path.join(here, "ser_monitor.log"),
                  mame_log_path=os.path.join(here, "mame_stdout.log")).listen()
    hs.launch_mame(lua=lua, seconds=secs)
    print("[listening on %d; launched patched MAME hp9k360 on work CHD]" % PORT)
    if not hs.accept():
        print("[accept failed] %s" % hs.connect_error)
    else:
        hs.wait_mame(timeout=secs + 120)
        hs.drain_and_join()
    print("\n=== %d serial bytes captured ===" % len(hs.buf))
    hs.close()
