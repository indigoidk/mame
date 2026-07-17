# Forward-review TODO — 6-model panel (2026-07-16)

Panel: Fable + Codex 5.6-SOL (ultra) + agy Gemini 3.1 Pro + ollama cloud (deepseek-v4-pro, glm-5.2,
kimi-k2.7-code). Fable + Codex read the repo/source; the rest reviewed embedded source. Convergence noted
as (Nx). **Applied fixes** are checked; the rest is prioritized work.

## 2026-07-17 — done this session (pushed)
- **`monitor epset` over gdbstub: VALIDATED.** `epset 2`/`epset 3` (set via qRcmd -> execute_command,
  debuggdbstub.cpp:1293) halt under `-debugger gdbstub` and report a stop, and halt at the handler
  start with the frame already stacked. New harness `phase_c_epset.py`: image-independent capture (no
  hardcoded 0x1A1A), decodes format/vector/fault-address/SSW, walks the A6 chain, auto-symbolizes from
  a cached `nm -n /bsd` (`nm_bsd_text.txt`).
- **NEW FINDING — `epset 2` is too broad on the 68030.** A demand-paging / copyin fault is itself a
  vector-2 bus error, so `epset 2` stops on every routine page fault (caught a supervisor copyin of
  user-data 0x4DCC8, SSW FC=1). Catch panics via `_panic`/`_Debugger`/`_kdb_trap` breakpoints; keep
  `epset 3` (address error — never a normal page fault).
- **NEW FINDING — a raw `rsd1c` read does NOT reliably panic.** OpenBSD 2.2 synthesizes a default label
  ("no disk label, defining `c' partition as entire disk") and reads fine. The old `0x10C26` = `_db_lookup`
  capture was the ddb *secondary*, not the origin. The #3 "bad kernel read at 0x0" needs a more specific
  trigger (a partition with no default label, or a corrupt-label state) — under investigation.
- **hp98644 hardening + m68k address-error fix: applied, rebuilt, regression-passed** (boots + reads a
  raw disk over serial). Upstream PR branches pushed: `hp98644-dio-irq`, `m68k-address-error-vector`.

## Key correction (Fable + Codex, source-verified)
The earlier claim "the 68030 PMMU-fault bus error bypasses `debugger_exception_hook`" is **FALSE**. The
MMU-enabled path calls `m68ki_init_exception(EXCEPTION_BUS_ERROR)` (`m68kcpu.cpp:957`) → the hook
(`m68kcpu.h:1164`); exception-point actions run via `debugcpu.cpp:766`. The real blocker was `-debugger none`
auto-resume. Nuance: the hook fires **before** the stack frame is built, so an `epset` action can *detect*
the fault + discriminate vector 2 vs 3 but can't read the stacked PC — pair `monitor epset` with a `bpset`
on the handler to read the frame. [README + `m68k_fault.lua` corrected.]

## BUGS
- [x] `phase_c_gdb.py` fault-SR parse: SR is the HIGH 16 of u32@A7 (`>>16`), not the low half (3x: agy/Fable/Codex).
- [x] `serial_console.py` `login()` TERM expect matched a bare `#/$` from the MOTD → premature/desync (2x: Fable/Codex).
- [x] `hp98644.cpp`: add `device_post_load()` re-driving the DIO IRQ after a savestate, and call `update_irq(false)`
      in `device_reset()` to deassert (5x: agy/deepseek/glm/Fable/Codex). DONE — pushed on `hp98644-dio-irq`.
- [ ] gdb RSP client (`phase_c_gdb.py`): validate checksums, handle NACK/escaping/retransmit, use `Z0,addr,2`
      (not kind 4), reliable socket/`z` cleanup, reconcile worker deadline vs join (2x: Codex/Fable, +kimi).
- [ ] `fire_portmap_serial.py`: `payload; echo FIRED` reports `echo`'s RC, not the payload's; transport failures
      classed as findings. Preserve payload RC, distinguish timeout/reset/crash, emit JSON (Codex).
- [ ] `hp_ser_io.py` `expect(since=None)` starts at current buffer end → can miss an already-received prompt (Codex/kimi).

## ARCH "truing" — real MAME bugs, upstream-PR candidates (mostly Codex, source-cited)
- [x] **68030 address-error frame encodes vector 2, not 3** — `m68ki_exception_address_error` passes
      `EXCEPTION_BUS_ERROR` to the frame builders (`m68kcpu.h:1655/1660/1664/1668`); should be `EXCEPTION_ADDRESS_ERROR`
      (offset 0x0C). DONE — pushed on `m68k-address-error-vector` (5x).
- [ ] **DIO shared IRQ/DMAR not wired-OR** — bus drives the CPU line from the last card's raw transition; aggregate
      accessor uses `~m_bus_index` not `~(1U<<m_bus_index)` (`hp_dio.cpp:153`, `hp_dio.h:112`). Affects the 98644 IRQ
      if a slot shares a level (Codex).
- [ ] **hp360 (DIO32) CPU RESET not wired + IRQ6 double-driven** — `DIO32_SLOT` path omits reset (`hp9k_3xx.cpp:267`
      vs `:252`); PTM + DIO both drive IRQ6 directly → use `INPUT_MERGER_ANY_HIGH` (`hp9k_3xx.cpp:323`) (Codex).
- [ ] **gdbstub MMU-crossing `m`/`M`** translate only the first page then increment physical → wrong across
      non-contiguous PMMU pages; `M` translates with `TR_READ` (`debuggdbstub.cpp:1169/1214`) (Codex).
- [ ] **98644 register accuracy** — ID reversed (normal should be 0x42, emulation 0x02; `hp98644.cpp:244`), fake
      1-byte loopback bypasses the INS8250's real loopback (`:275`), modem-enable DIP ignored (`:130`) (Codex).
      NOTE: OUT2/MCR_IEN gate is DISPUTED — Fable says add it (dca.c warns of deadlock); Codex cites the HP 310
      spec that OUT2 is *unconnected* on the 98644A → do NOT gate. Codex's hardware citation likely wins.
- [ ] hp360 unmapped-read tagged as write (`buserror_r` passes `false`; `hp9k_3xx.cpp:295`) → corrupts SSW R/W (Codex).
- [ ] Lower priority: 98550 IRQ bitmap ORs unshifted data (`hp98550.cpp:235`); 98620 DMA reset incomplete/no
      arbitration (`hp98620.cpp:190`); **MB87030 disconnect may fall through to Idle + double `scsi_disconnect`**
      (`mb87030.cpp:317` — related to the earlier SCSI patch, worth a look); 98265A switches unread (Codex).

## FEATURES (all converge)
- [ ] **Capture the ORIGINAL fault, not `_db_lookup`** [top feature, 6x]: the sd-path enters ddb via a
      `panic()`/`Debugger()` call (not a CPU fault, so no exception there). `nm /bsd` → `monitor bpset <panic>/<Debugger>`,
      walk the A6 frame chain (`a6→prev_a6`, `a6+4→ret`), keep the earliest relevant stop. Pairs with `monitor epset`.
- [ ] **Serial kernel console** so panic/DDB text reaches the socket. Try the modeled 98644 "Remote" DIP first
      (after the ID fix it reads 0xc2); do NOT assume a generic `SERCONSOLE` option — inspect OpenBSD `consinit` (Codex).
- [ ] **Auto-symbolize**: cache one numeric `nm -n /bsd` map keyed by kernel hash; binary-search fault/return PCs.
      Fix `phase4_symbol.py` (hard-codes one addr, queries the guest every run).
- [ ] Capture the bus-error **fault address** + decode the frame (format/vector @A7+6, SSW @+0x0a, addr @+0x10;
      dump 32 bytes for format A / 92 for B).
- [ ] Watchpoints exist (gdbstub `Z2/Z3/Z4`) — reinstall after remap/savestate (stale physical addr).
- [ ] Savestate replay: first serialize the MB87030 FIFO (`mb87030.cpp:526` omits it) + rewind socket/CHD; then
      drive `statesave`/`stateload` via gdb `qRcmd`.
- [ ] A shared robust RSP client + a trustworthy multi-run headless fire runner (JSON: SHAs, CHD/kernel hashes,
      registers, raw frame, symbols; fresh disk clone per run; dynamic ports).

## Highest-value next steps
1. **`monitor epset 2/3` over gdbstub** (image-independent, vector-discriminating) + **capture the original panic**
   (`bpset` on `_panic`/`_Debugger` + A6 walk) — the two Fable/Codex source-verified wins. Testable in an hour.
2. **Upstream PR: 68030 address-error vector** (`m68kcpu.h:1655/1660/1664/1668`) — smallest, cleanest, high-confidence.
3. hp98644 hardening (`device_post_load` + reset deassert) folded into the existing IRQ PR.

**PR split (Codex):** keep the 98644 IRQ repair focused; submit DIO wired-OR, hp9k SSW read/write, m68k
address-error vector, gdbstub MMU translation, reset/IRQ merging, and broader 98644 truing as independent,
test-backed PRs.
