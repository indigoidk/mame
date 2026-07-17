# hp9k_serial — MAME-HP (hp9k360 / OpenBSD 2.2) serial-console + m68k crash-capture harness

Branch: `hp9k-serial-harness` (off `hp9k-mb87030-selection`). Goal: raise MAME-HP bug-finding from the
natkeyboard (~10 cps) + PNG-snapshot ceiling to clean bidirectional serial text I/O plus cycle-accurate
m68k register capture at faults, bringing hp300 to parity with the pmax/arc/amiga fire rigs.

## Status

- [x] **Phase A — serial byte path: SOLVED.** `printf HPSERBYTES > /dev/tty0` now delivers all 10 bytes to
  the host socket (was 0, then 2). Root cause was a genuine **MAME device bug** — the HP 98644 card never
  wired the INS8250 interrupt to the DIO bus — fixed in `../src/devices/bus/hp_dio/hp98644.cpp`.
- [x] **Phase B — DONE (#1 fully achieved).** (a) Bidirectional serial login console (RX+TX). (b) getty
  baked into `obsd22_serial.chd` (persists across boots, no natkeyboard — `bake_getty.lua`). (c) reusable
  `serial_console.py` (`SerialConsole`: boot → login → `run()` with clean `stty -echo` capture). (d) fire
  batch ported: `fire_portmap_serial.py` fires #2 portmap AUTH_UNIX over serial and drops portmap
  (9 svcs UP → DOWN), reproducing the finding. Any `fire_*_nk.lua` ports the same way via `run()`.
- [x] **Phase C (#2) — m68k fault register capture: DONE (via `-debugger gdbstub`).** `phase_c_gdb.py` is a
  minimal gdb-remote client: connect, fetch `target.xml` (MAME serves `g`/`p` only after that), `Z1`
  breakpoint on the bus-error handler PC (`0x1A1A`), arm AFTER boot, fire the fault, and read
  D0-D7/A0-A7/SR/PC + the stacked fault PC — the m68k analog of the pmax gdb capture. (Dead ends, kept in
  `m68k_fault.lua`: the 68030 PMMU-fault bus error bypasses `debugger_exception_hook` so `epset` misses it;
  `bpset` actions don't run under `-debugger none`.)
- [x] **#3 (raw-disk panic): reproduced + characterized.** `phase4_panic.py` attaches a blank unlabeled
  `rsd1` and reads `/dev/rsd1c`, capturing a kernel null-deref (`A5=0`, SR supervisor) at `FAULT_PC=0x10C26`
  = **`_db_lookup`** (via `phase4_symbol.py`/`nm /bsd`): reading the label-less raw disk drops into DDB and
  DDB's symbol lookup null-derefs (null in-kernel symtab). Workaround: pre-write a disklabel on the 2nd
  disk, or use the cd9660 ISO channel.
- [x] **#5 (DDBSER kernel): SUPERSEDED** — `-debugger gdbstub` gives m68k crash register capture with no
  guest kernel rebuild; the DDBSER port is only needed for in-guest ddb state gdb/MAME can't provide.

## Serial-console usage (the fire-batch foundation)
```python
from serial_console import SerialConsole
sc = SerialConsole(log_path="s.log").boot().login()      # boots obsd22_serial.chd, getty auto-login over socket
print(sc.run("uname -a"))                                # ('OpenBSD obsd22 2.2 GENERIC#5 hp300', 0)
sc.run("perl -e '...fire...'"); print(sc.run("rpcinfo -p 127.0.0.1"))
sc.halt(); sc.close()
```
(Minor: a cosmetic `WinError 10038` can print from the reader thread during teardown after `halt` — harmless.)

## Root cause of the 0-byte serial (confirmed: 3-reviewer panel + guest source + empirical tests)

Found via Fable + Codex 5.6-SOL ultra + agy Gemini 3.1 Pro High, then proven end-to-end. Two real bugs
(plus two red herrings from earlier probes that are now settled):

1. **MAME: the 98644 never delivered interrupts.** `hp98644.cpp` bound TX/DTR/RTS but never
   `out_int_callback` → no `irqN_out`, no `IC_IR` status bit. OpenBSD's `dca` is interrupt-driven, so
   `dcastart()` sent the first byte(s) then stalled forever waiting for a THRE interrupt. **Fix:** wire the
   INS8250 int → `update_irq` → the selected DIO IRQ (gated by `IC_IE` = control bit 7 + the "Interrupt
   level" DIP, which already defaults to 5 = dmesg `ipl 5`), expose `IC_IR 0x40` in `io_r` case 1 (status
   reads `0xe0`, not `0xa0`), and reset the child UART on card reset — mirroring `hp98265a.cpp`.
2. **Guest: use `/dev/tty0`, not `/dev/cua0`.** A blocking `open(/dev/cua0)` **deadlocks** on the `sc_cua`
   self-block (`dca.c:381`, missing NetBSD's `!DCACUA` guard). The null_modem *asserts* DCD
   (`null_modem.cpp:89`), so the dial-in `/dev/tty0` opens fine and is the node to drive.

Settled non-issues: the stock `mame\mame.exe` doesn't boot the SCSI disk (use `hp9k_patched_0288.exe`);
`tty00-03` are DCM mux (major 15), not the 98644's `dca` (major 12); host-listens/MAME-connects is correct
(`-bitb socket.HOST:PORT` = MAME is the client — verified). Baud is 9600/9600; the byte path itself always
worked (Codex injected `A` via the debugger).

## Layout

| File | Role |
|------|------|
| `hp_ser_io.py` | Reusable bidirectional driver (`HpSerial`): listens on 1250, launches the patched MAME (stdout→file, not an undrained PIPE), `accept()` polls MAME, `send`/`expect`(absolute offsets)/slow-send(ddb), logs raw + masks for matching, kills MAME + joins reader on teardown. |
| `probe_tty0.lua` | The Phase-A confirmation: foreground `printf … > /dev/tty0` — the test that proved the fix. |
| `probe_serial_path.py` / `probe_nodes.lua` | Step-0 node-discovery probe (superseded now that the node is known to be `/dev/tty0`; kept for reference). |

## Rebuild (folders MOVED — old `build_hp9k.sh` paths are stale)

MSYS2: `C:\DocumentNoSnc\CC\msys64` · build tree: `C:\DocumentNoSnc\CC\mame_build\mame0288src`.
```
MSYSTEM=MINGW64 /c/DocumentNoSnc/CC/msys64/usr/bin/bash.exe -lc \
  'export OS=Windows_NT; cd /c/DocumentNoSnc/CC/mame_build/mame0288src && \
   make SUBTARGET=hp9k SOURCES=src/mame/hp/hp9k_3xx.cpp PYTHON_EXECUTABLE=python NOWERROR=1 REGENIE=1 -j12'
```
`export OS=Windows_NT` is essential (Git-Bash→MSYS2 drops it → `makefile:235 Unable to detect OS`). Output
`hp9k.exe` → copy over `C:\DocumentNoSnc\CC\hp_mame\hp9k_patched_0288.exe` (back up first).

## External assets (NOT in the repo)

- Patched exe: `C:\DocumentNoSnc\CC\hp_mame\hp9k_patched_0288.exe` (pre-fix backup: `.bak-preIRQ`)
- ROMs: `…\hp_mame\mame\roms` · golden image (never probed): `…\hp_mame\obsd_test\obsd22_disk.chd`
- Work copy (MAME writes here): `…\hp_mame\obsd_test\serial_work.chd`

## Disk-booting launch recipe (in `hp_ser_io.mame_hp9k360_args`)
```
hp9k_patched_0288.exe hp9k360 -rp mame\roms -sl4 98265a -hard <copy>.chd \
  -sl2 98644 -sl2:98644:rs232 null_modem -bitb socket.127.0.0.1:1250 \
  -video none -sound none -nothrottle -skip_gameinfo
```
Slot defaults: sl1 video, sl2 serial(98644=dca0), **sl3 98620 DMA (do not evict → panic)**, sl4 SCSI, sl5 free.
