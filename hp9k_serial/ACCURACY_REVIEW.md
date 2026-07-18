# HP-MAME emulation-layer accuracy review (2026-07-18)

Scope: **only** the MAME HP 9000/300 (`hp9k3xx`) emulation layer — the machine driver, its DIO/DIO-II
bus cards, and the Musashi m68k core. The cross-arch security campaign's GXEMUL/pmax/arc and i386/QEMU
material is out of scope here; only its MAME-HP "truness" claims (L4/L17) are reconciled (§5).

Method: every candidate in `REVIEW_TODO.md` was ground-truthed against the source; the shipped fixes
were re-verified; and the open hardware-fidelity questions went to a two-model panel (Codex 5.6-SOL
xtra-high + Fable) with benign framing. **The panel converged unanimously on every item** — including
Fable dumping the Rev C boot ROM ID table locally to settle the 98644 ID question.

---

## 1. CHANGELOG — shipped this session (branch `hp9k-serial-harness`)

| Commit | Change | File | Status |
|--------|--------|------|--------|
| `3b139e5` | **B1** merge PTM+DIO IRQ6 via `INPUT_MERGER_ANY_HIGH`; **B2** wire DIO32 CPU reset | `hp9k_3xx.cpp` | built + regression PASS; **PR branch `hp9k3xx-reset-irq6` (off master), cherry-pick `ee31ff9`** |
| `f5fccee` | **C1** correct/clarify the bus-error read flag (dead-arg cleanup) | `hp9k_3xx.cpp` | built; no behavioral change |
| `e89a2ac` | **B7** drop the redundant second `scsi_disconnect` on bus-free | `mb87030.cpp` | built + regression PASS |
| `c9fbd41` | **C3** 98644 ID → native 0x42 (was 0x02); **B4** remove the fake loopback shadow | `hp98644.cpp` | built + regression PASS (getty @0x42, kernel console @0xC2); **stacked PR branch `hp98644-register-truing`** off `hp98644-dio-irq` |
| `411d28f` | **onboard-I/O** add the on-board 98620 DMA to the 330 + 332 (built-in at 0x500000, was an unserviced bus-error hole); rewrite the stale internal-I/O map | `hp9k_3xx.cpp` | built + verified (330 boots BASIC 5.1 + "DMA-C0"; 332 "DMA-C0"); **Codex+Fable APPROVE** |

Binary: rebuilt `hp9k_patched_0288.exe` (old → `.bak-preResetIrq6`). **Regression PASS**
(`regress_dio_wiredor.py`): hp9k360/OpenBSD 2.2 boots to a serial login — which *requires* the 250 kHz
PTM tick on IRQ6 to reach the CPU through the new merger — `dca0 ... ipl 5` round-trips, SCSI disk
boots, multi-line `dmesg` captured, clean halt. All 5 checks pass.

Rig fix (retires L4/L12/L17): `hp300_fire.py` (generalized serial fire runner) + `HP300_FIRE_RECIPE.md`
(migration guide: use `hp9k_patched_0288.exe` + serial console, not `mame.exe` + HIL).

---

## 2. Verified-correct prior fixes (shipped earlier, re-audited)

| # | Fix | File | Verdict |
|---|-----|------|---------|
| A1 | m68k address-error stacks vector 3 (0x0C), not bus-error (0x08), on the 010/020/030/040/070 frames | `m68kcpu.h` | correct |
| A2 | DIO wired-OR IRQ/DMAR aggregation (replaces the `& ~m_bus_index` index-as-mask accessor) | `hp_dio.cpp/.h` | correct |
| A3 | hp98644 UART IRQ routed to the DIO bus + reset deassert + `device_post_load` | `hp98644.cpp` | correct/complete |
| A4 | SCSI 0001 (nscsi IDENTIFY) + 0002 (mb87030 disconnect) | `nscsi_hle.cpp`, `mb87030.cpp` | correct (boots OBSD 2.2) |

---

## 3. Confirmed accuracy bugs — panel-unanimous

### Fixed this session
- **B1 — IRQ6 double-driven (no merger).** `hp9k300()` wired `ptm.irq_callback()` → `M68K_IRQ_6`
  (`:326`) and the DIO bus wired `irq6_out_cb` → `dio_irq6_w` → `set_input_line(M68K_IRQ_6)` (`:135`).
  MAME input lines are single-writer level state → last-writer-wins; a DIO level-6 deassert cancels a
  pending PTM tick (and the 6840 output doesn't re-edge, so the tick is *lost*). Real HW wire-ORs into
  the IPL encoder; the 6840 system clock is at level 6 on every model, and level-6 DIO sources are
  reachable (98644 DIP=6, 98620 3-7, 98550 1-7). **Fix:** `INPUT_MERGER_ANY_HIGH`. Level 6 is the only
  line with a non-DIO driver → the only one affected. *(Codex + Fable CONFIRM.)*
- **B2 — DIO32 bus never propagates a CPU `RESET`.** `add_dio16_bus()` wires `m_maincpu->reset_cb()` →
  `reset_in`; `add_dio32_bus()` did not, so hp9k320/330/340/360/370/380/382 reset no DIO-II cards on a
  guest `RESET` (the Musashi RESET opcode pulses `reset_cb` on all CPU types). **Fix:** mirror the DIO16
  wiring. *(Codex + Fable CONFIRM.)* **Caveat / follow-up:** most cards' `reset_in()` is still a stub
  (`hp_dio.h:217`), so fully honoring the pulse per card is a **separate PR** (Fable/earlier-panel:
  bus-vs-card reset-ordering needs care).
- **B7 — mb87030 redundant double `scsi_disconnect`.** On a fully-free bus the disconnect monitor
  (`:319`) and `case State::Idle` (`:326`) both fired in one `step()` (`update_state(Idle)` is
  synchronous). Idempotent (`m_ints = INTS_DISCONNECTED`), so benign — added a `return`. *(My finding;
  not in the panel brief.)*

### Confirmed — C3 + B4 now FIXED (`c9fbd41`, stacked PR branch `hp98644-register-truing`); B3/B5/B6 held
- **C3 [FIXED `c9fbd41`] — 98644 ID register polarity was INVERTED (`hp98644.cpp` io_r case 0).** Native 98644A = **0x42**,
  98626-emulation = 0x02; current code returns 0x02 base and *sets* 0x40 for 98626-emulation — backwards
  — and the DIP defaults to the emulation value. **Definitive evidence:** Fable dumped the Rev C boot ROM
  ID table from `roms\hp9k360.zip`: `02`="HP98626 (RS-232)", `42`="HP98644 (RS-232)"; Codex cites the HP
  98644A Reference Manual + DIO-II Accessory Development Guide (primary ID bits 4-0, secondary bits 6-5).
  **Safe to change:** OpenBSD `dca` accepts 0x02/0x42/0x82/0xC2 identically, so the serial console keeps
  working; the guest-visible effect today is *misidentification* (boot ROM prints "HP98626"). **Fix:**
  `ret = 0x42; if (REMOTE) ret |= 0x80; if (98626_EN) ret &= ~0x40;` *(Codex + Fable CONFIRM.)*
- **B4 [FIXED `c9fbd41`] — 98644 fake board loopback shadow.** The board's `m_loopback`/`m_data` intercept THR/RBR when
  MCR LOOP is set, bypassing the INS8250's native LOOP (no LSR THRE/DR, no IIR, no baud delay, 1 byte).
  Real card has no such register (BSD `dcareg.h`). **Fix:** delete the shadow, rely on `ins8250.cpp`
  native LOOP — **regression-test the boot-ROM serial self-test** (the shadow was in Sven's original
  commit and may have masked a then-broken ins8250 LOOP). *(Codex + Fable CONFIRM.)*
- **B3 — 98620 DMA `device_reset` incomplete (`hp98620.cpp:190`).** Doesn't disarm channels, clear
  irq/ie, restore level 3, or deassert the DIO IRQ. Per HP 98620C spec, reset clears control/ARM/INT and
  sets level 3 but **preserves address/TC** (both panels corrected my "zero address/TC / clear m_dmar[]"
  overreach — `m_dmar[]` are live external pins). `REG_GENERAL_CONTROL` RESET0/1 also only clears
  `armed`, should clear irq + `update_irq()`. *(Codex + Fable CONFIRM.)*
- **B5 — 98550 per-plane IRQ stomp — root is in `catseye.cpp`, not `hp98550.cpp`.** Both panels found
  this deeper than my original note: `catseye_device::update_int()` calls the single-arg devcb
  `m_int_write_func(m_plane)`, so in `dio32_98550_device::int_w(offset,data)` **offset is always 0** and
  `data` is the plane *number*. Any plane ≥2 assert leaves `m_ints` permanently nonzero → stuck IRQ
  (98550 is a default hp9k360/370 card). **Fix touches both files:** `catseye.cpp` →
  `m_int_write_func(m_plane, state ? 1 : 0)`; `hp98550.cpp int_w` →
  `m_ints &= ~(1<<offset); if (data) m_ints |= (1<<offset);` *(Codex + Fable CONFIRM.)*
- **B6 — 98644 "Modem line enable" DIP ignored** (`hp98644.cpp:131`) — defined, never read. Minor.

---

## 4. NEGATIVE FINDINGS — candidates that are NOT bugs (or not as described)

These are recorded so they are not re-investigated. **The panel agreed with each refutation.**

- **C1 (REFUTED as a live defect) — "unmapped access mis-tags SSW R/W."** `set_buserror_details`
  (`m68kcpu.cpp:1916`) feeds the passed `rw` **only** to the 68000 group-0 frame; the 010/020/030/040
  frames every hp9k3xx uses take R/W from the CPU's own `m_mmu_tmp_buserror_rw` — which Fable confirms is
  **re-snapshotted again** when the deferred `M68K_LINE_BUSERROR` is serviced (`m68kcpu.cpp:754-756`).
  No hp9k3xx is a plain 68000, so the argument is **dead**; only `fault_addr` survives to a guest frame.
  Cleaned up anyway (C1) for correctness, no behavioral change.
- **OUT2 / MCR_IEN interrupt gate (dispute RESOLVED — current code correct).** The 98644 gates its IRQ
  on the board IC_IE bit (`m_control & 0x80`), not INS8250 OUT2 — matching the HW (OUT2 is unconnected on
  the 98644A). No change.
- **"raw-disk panics the kernel = MAME SCSI/disk bug" (campaign L4) — NOT reproducible on a correct
  rig.** See §5.
- **DIO wired-OR `set_dmar` originator-skip** — deliberate and correct for the real topology (the 98620
  is never the requester); not a bug.

### New minor observations from the panel (not fixed, noted for completeness)
- `buserror_r/_w` compute the fault address as `offset << 2`, discarding sub-longword address bits and
  ignoring `mem_mask` (a byte probe at `…01` stacks `…00`). Latent, since the CPU frame uses its own
  captured address; worth tidying if the 98644/other truing PR touches this file. *(Fable.)*
- Multi-access instructions stack the SSW R/W of their *last* access — a core-level Musashi quirk, not
  driver-fixable. *(Fable.)*

---

## 5. Cross-arch campaign reconciliation (MAME-HP truness)

- **L4 "raw-disk read/write PANICS the kernel → MAME SCSI/disk emulation BUG": RECLASSIFY.** Reproduced
  on the **unpatched `mame.exe`** (the campaign's L15 recipe launches `mame\mame.exe`, which lacks SCSI
  patches 0001/0002). On the **patched** `hp9k_patched_0288.exe` over the serial console, `panic_hunt.py`
  ran the full raw-disk battery with **zero kernel panics** (`dd /dev/rsd1c` → default-label synthesis +
  1024 bytes; others → clean "Device not configured"). The old `0x10C26=_db_lookup` was a **ddb
  secondary** null-deref, not a raw-disk origin. → Downgrade from `[BUG]` to a wrong-binary artifact.
  **HIGH impact:** this unblocks the hp300 track. *(See `HP300_FIRE_RECIPE.md`.)*
- **L17 telnetd AYT positive-control failure (N=133, no `[Yes]`): not shown to be an emulation defect.**
  Ran over the lossy HIL channel. Re-run over the serial console (clean text I/O) to tell a real emulator
  divergence apart from a HIL/timing artifact before escalating.
- **Meta:** the campaign's hp300 fires were on the wrong binary + channel (natkeyboard + framebuffer).
  The serial console (enabled by the shipped 98644 IRQ fix) + `hp300_fire.py` give clean script-in /
  results-out and a gdbstub `_panic` capture — retiring the HIL slowness (hp300 analogue of L12) and the
  L17 failure mode.

---

## 6. Panel verdict table (Codex 5.6-SOL xtra-high + Fable — unanimous)

| Item | Codex | Fable | My call | Disposition |
|------|-------|-------|---------|-------------|
| B1 IRQ6 merger | CONFIRM | CONFIRM | CONFIRM | **fixed** `3b139e5` |
| B2 DIO32 reset | CONFIRM | CONFIRM | CONFIRM | **fixed** `3b139e5` (+ follow-up PR for per-card `reset_in`) |
| C1 bus-error rw | REFUTE (dead) | REFUTE (dead) | REFUTE | **cleaned up** `f5fccee` |
| C3 98644 ID polarity | CONFIRM (0x42) | CONFIRM (0x42, ROM-table) | was wrong → CONFIRM | **fixed** `c9fbd41` |
| B4 98644 loopback | CONFIRM | CONFIRM | CONFIRM | **fixed** `c9fbd41` |
| B3 98620 reset | CONFIRM | CONFIRM | CONFIRM | held (lower prio) |
| B5 98550 IRQ (catseye) | CONFIRM (catseye) | CONFIRM (catseye) | CONFIRM (deeper) | held (lower prio) |
| B7 mb87030 dbl-disconnect | — | — | benign redundancy | **cleaned up** `e89a2ac` |

Key HW sources: HP 9000 200/300 Peripheral Installation Guide (98644A SW1); HP DIO card-ID list
(bitsavers); Rev C boot ROM ID table (dumped from `hp9k360.zip`); HP 98620C DMA spec; INS8250 datasheet;
MC68030 UM; OpenBSD/NetBSD hp300 `dca`/`dcareg`/`catseye`/`topcat` drivers.

---

## 7. Recommended next steps
1. **Push `hp9k3xx-reset-irq6` + open the upstream PR** (B1+B2) — validated, source-cited, unanimous.
2. **On your go:** implement C3 (98644 ID) + B4 (loopback) + B6 (modem DIP) as an "hp98644 register
   truing" PR; and B3 (98620 reset) + B5 (98550/catseye) as their own PRs. All fixes are specified above.
3. Repoint the campaign's hp300 fires at `hp300_fire.py` (patched binary + serial console).
