#!/usr/bin/env python3
"""
hp300_fire.py -- reusable hp300 (MC68030 / OpenBSD 2.2, BIG-endian) fire runner over the CLEAN serial
console. Replaces the campaign's natkeyboard(~10 cps HIL) + framebuffer-snapshot method
(fire_*_hp300.lua + run_hp2_fire.py) with clean serial text I/O on the SCSI-patched binary.

WHY (emulation-accuracy reconciliation, 2026-07-18) -- this is the rig that retires L4/L12/L17:
  * Use hp9k_patched_0288.exe (SCSI patches 0001 nscsi-IDENTIFY + 0002 mb87030-disconnect), NOT the
    stock mame.exe. The campaign's L15 recipe launches mame\\mame.exe; on that UNPATCHED SCSI stack the
    disk path misbehaves, and THAT -- not a fundamental MAME defect -- is the origin of the campaign's
    "L4: raw-disk read/write panics the kernel". On the patched binary raw-disk reads do NOT panic
    (hp9k_serial/panic_hunt.py: every trigger that executed returned a clean default-label synthesis or
    a plain 'Device not configured'; 0 kernel panics). => L4 is a wrong-binary artifact, not a truness
    [BUG]. The old 0x10C26=_db_lookup capture was a ddb *secondary* null-deref, not a raw-disk origin.
  * Drive over the serial getty (obsd22_serial.chd), NOT the HIL keyboard + framebuffer snapshots.
    Serial capture returns full multi-line output reliably => retires the hp300 HIL-slowness / lossy
    channel (the hp300 analogue of L12) and lets #3 telnetd's failed HIL positive-control (L17) be
    re-run over a clean channel to tell an emulator divergence apart from a HIL/timing artifact.
  * For crash findings, arm the gdbstub _panic capture (hp9k_serial/phase_c_epset.py: Z0 on
    _panic/_Debugger/_kdb_trap + register + A6-backtrace + symbolize) so a panic yields registers and a
    symbolized backtrace instead of vanishing into the framebuffer.

A fire = optional SETUP commands, a liveness PROBE (before), the FIRE payload, the same PROBE (after)
-> an A/B verdict. UP->UP = SURVIVED; UP->DOWN = TARGET_DOWN (candidate finding, reproduce + capture);
!UP before = NOT_REACHED (rig/setup problem, never a refute). Generalized from fire_portmap_serial.py so
any fire_*_hp300.lua / fire_*_nk.lua becomes a few-line Fire() spec:

    from hp300_fire import Fire, run_fire
    r = run_fire(Fire(
        name="portmap-authunix",
        probe="rpcinfo -p 127.0.0.1 >/dev/null 2>&1 && echo UP || echo DOWN",
        up="UP",
        fire=r'''perl -e 'socket(S,2,2,0); ...' ''',
    ))
    print(r["verdict"])   # SURVIVED | TARGET_DOWN | NOT_REACHED | ERROR
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serial_console import SerialConsole


class Fire:
    """One hp300 fire specification. `probe` is a shell command that echoes `up` iff the target sink
    is healthy (e.g. a daemon still bound). `fire` is the (benign) trigger payload. `setup` is a list
    of shell commands run once before the before-probe (e.g. bring up a minimal inetd)."""
    def __init__(self, name, fire, probe, up="UP", setup=None, fire_timeout=30, settle=2):
        self.name = name
        self.fire = fire
        self.probe = probe
        self.up = up
        self.setup = list(setup or [])
        self.fire_timeout = fire_timeout
        self.settle = settle


def run_fire(f, seconds=560, log_dir=None):
    """Boot the serial rig, log in, probe/fire/probe, return a JSON-able result dict."""
    log_dir = log_dir or os.path.dirname(os.path.abspath(__file__))
    sc = SerialConsole(log_path=os.path.join(log_dir, "hp300_fire_%s.log" % f.name),
                       mame_log_path=os.path.join(log_dir, "hp300_fire_%s_mame.log" % f.name))
    res = {"name": f.name, "binary": "hp9k_patched_0288.exe", "channel": "serial",
           "before": None, "after": None, "delivered": False, "verdict": "ERROR"}
    try:
        sc.boot(seconds=seconds).login()
        for cmd in f.setup:
            sc.run(cmd)
        before, _ = sc.run(f.probe)
        res["before"] = before.strip()
        sc.run(f.fire + "; echo __FIRED__", timeout=f.fire_timeout)
        res["delivered"] = True
        sc.hs.wait(f.settle)
        after, _ = sc.run(f.probe)
        res["after"] = after.strip()
        if res["before"] != f.up:
            res["verdict"] = "NOT_REACHED"      # target unhealthy BEFORE the fire -> setup/reach bug, never a refute
        elif res["after"] == f.up:
            res["verdict"] = "SURVIVED"         # fire delivered, target still healthy
        else:
            res["verdict"] = "TARGET_DOWN"      # candidate finding -- reproduce single-shot + arm phase_c_epset.py
        sc.halt()
    except Exception as e:
        res["error"] = repr(e)
        try:
            res["tail"] = sc.hs.text()[-400:]
        except Exception:
            pass
    finally:
        sc.close()
    return res


# Default smoke test = the #2 portmap AUTH_UNIX fire (the proven m68k BIG-endian datapoint), ported
# verbatim from fire_portmap_serial.py. Proves the whole serial rig end-to-end on the patched binary.
_SMOKE = Fire(
    name="portmap-authunix-smoke",
    probe="rpcinfo -p 127.0.0.1 >/dev/null 2>&1 && echo UP || echo DOWN",
    up="UP",
    fire=(r"""perl -e 'socket(S,2,2,0);for(1..8){send(S,"""
          r"""pack(q{N12},1,0,2,100000,2,0,1,8,0,4294967295,0,0),0,"""
          r"""pack(q{CCnC4x8},16,2,111,127,0,0,1))}'"""),
)


if __name__ == "__main__":
    r = run_fire(_SMOKE)
    print(json.dumps(r, indent=2))
    # SURVIVED or TARGET_DOWN are both valid fire outcomes; ERROR / NOT_REACHED are rig problems.
    sys.exit(0 if r["verdict"] in ("SURVIVED", "TARGET_DOWN") else 1)
