# hp300 fire rig — correct recipe (retires L4 / L12 / L17)

The cross-arch campaign's hp300 (m68k) track has been running on the **wrong binary and the wrong I/O
channel**. Three "limitations" attributed to MAME are actually rig-config artifacts and are retired by
switching to the SCSI-patched binary + the serial console that the `hp9k_serial/` harness already
provides. This is the emulation-accuracy reconciliation from 2026-07-18.

## TL;DR — do this, not that

| | ❌ old rig (L14/L15) | ✅ correct rig |
|---|---|---|
| binary | `mame\mame.exe` (stock, **unpatched** SCSI) | `hp9k_patched_0288.exe` (patches 0001+0002) |
| disk | `boot_run*.chd` + install media | `obsd_test\obsd22_serial.chd` (installed multiuser + baked serial getty) |
| input | natkeyboard (HIL ~10 cps), dense one-liners only | serial getty over the socket, arbitrary commands |
| output | framebuffer PNG snapshots (lossy) | serial text capture (full, clean) |
| crash capture | read panic text off a snapshot | gdbstub `_panic` breakpoint → registers + backtrace |
| driver | `fire_*_hp300.lua` (natkeyboard state machine) | `hp300_fire.py` / `serial_console.py` |

## What each limitation actually was

- **L4 — "raw-disk read/write panics the kernel → MAME SCSI/disk emulation BUG."**
  Reproduced on the **unpatched `mame.exe`**. The stock binary lacks SCSI patch 0001 (nscsi clears a
  stale IDENTIFY at a new selection) and 0002 (mb87030 restores the prompt bus-free disconnect the HP
  boot ROM polls for). On the **patched** `hp9k_patched_0288.exe`, `panic_hunt.py` ran the full raw-disk
  battery over serial: `dd /dev/rsd1c` → *"no disk label, defining `c' partition as entire disk"* +
  1024 bytes transferred; `rsd1a/d/g`, whole-disk, `mount ffs` → clean *"Device not configured"*;
  `sync; halt` clean. **Zero kernel panics.** The earlier `FAULT_PC=0x10C26=_db_lookup` capture was a
  **ddb secondary null-deref** (ddb's own symbol lookup on a null in-kernel symtab), not a raw-disk
  origin. → **L4 is a wrong-binary artifact; downgrade from `[BUG]`.**
- **L12 (hp300 analogue) — HIL ~10 cps + lossy framebuffer.** An artifact of the natkeyboard +
  snapshot channel, not the CPU. The serial getty (enabled by the upstreamable 98644 IRQ fix that made
  the `dca` interrupt-driven path work) returns full multi-line output. → retired by the serial rig.
- **L17 — telnetd AYT positive-control failed under MAME (N=133, no `[Yes]`).** Ran over the lossy HIL
  channel. Re-run it over the serial console: if `recv_ayt` is now reached (single AYT echoes `[Yes]`),
  L17 was a HIL/timing artifact; if it still fails on a clean channel, only THEN is it a candidate
  emulator-divergence worth escalating.

## How to run a fire

```python
from hp300_fire import Fire, run_fire
r = run_fire(Fire(
    name="portmap-authunix",
    probe="rpcinfo -p 127.0.0.1 >/dev/null 2>&1 && echo UP || echo DOWN",  # echoes UP iff sink healthy
    up="UP",
    setup=["ifconfig lo0 127.0.0.1 up"],                                   # optional pre-fire setup
    fire=r"""perl -e 'socket(S,2,2,0); ... send malformed datagram ...'""",
))
print(r)   # {name, before, after, delivered, verdict}
```

`verdict`: `SURVIVED` (UP→UP), `TARGET_DOWN` (UP→DOWN = candidate finding), `NOT_REACHED`
(target unhealthy before the fire → a rig/setup bug, **never** record as a refute), `ERROR`.

Smoke test (proves the whole rig end-to-end on the patched binary): `python hp300_fire.py` runs the #2
portmap AUTH_UNIX fire (the confirmed BIG-endian datapoint).

## Crash / panic findings

For a fire expected to panic (not just take a daemon down), arm the gdbstub capture instead of / in
addition to the A/B probe:

```
python phase_c_epset.py     # Z0 on _panic/_Debugger/_kdb_trap; on hit dumps D0-D7/A0-A7/PC/SR,
                            # walks the A6 frame chain, symbolizes against nm_bsd_text.txt
```

Do **not** use the serial *kernel* console (`panic_cfg`, the 98644 "Remote" DIP) and the interactive
getty at the same time — console syslog spam desyncs the expect-based login (harness-architecture note
in `panic_hunt.py`). Drive fires over the clean getty; catch panics via the gdb `_panic` breakpoint.

## Porting an existing `fire_*_hp300.lua`

The natkeyboard Lua state machines type a perl script via a heredoc then snapshot. The serial port is
mechanical: the perl payload becomes `Fire.fire`, the PMAP_UP/DOWN (or equivalent) check becomes
`Fire.probe`, and any `ifconfig`/inetd bring-up becomes `Fire.setup`. No heredoc, no snapshots, no
`-seconds_to_run` race against ~10 cps typing.
