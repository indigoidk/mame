# HP 9000/300 MAME emulation-layer fixes — patch series

13 device/CPU **accuracy fixes** for the HP 9000/300 (`hp9k3xx`), discovered and resolved in the
2026-07-18 emulation-layer audit and adversarially verified with the Codex 5.6-SOL (xtra-high) + Fable
review panel. Full audit incl. **negative findings** (refuted candidates): [`../ACCURACY_REVIEW.md`](../ACCURACY_REVIEW.md).

- **Flattened branch:** `hp9k-emulation-fixes` — the same 13 commits, linear, src-only, off `master`.
- **Apply the series:** `git am 00*.patch` onto a clean `master` checkout. They are an *ordered series*
  (several touch a common file — e.g. four cumulative `hp98644.cpp` changes — so apply in number order,
  not individually).
- Every fix is compiled into `hp9k_patched_0288.exe` and regression-verified (OpenBSD 2.2 boots over the
  serial console; the Remote-DIP kernel console + raw-disk reads verified).

## All fixes discovered & resolved

| # | Fix | What was wrong | Resolution | File(s) |
|---|-----|----------------|------------|---------|
| 0001 | SCSI: nscsi stale IDENTIFY | a LUN from a prior nexus leaked across selections; the polled HP boot ROM saw the wrong/absent LUN → disk not enumerated | clear the stored IDENTIFY at each new selection; fall back to LUN 0 / CDB LUN | `nscsi_hle.cpp` |
| 0002 | SCSI: mb87030 disconnect | a state-blind 10 ms auto-disconnect timer (added 0.285) broke the polled HP boot ROM → "System Search Mode", no boot | restore the prompt bus-free disconnect, exempting the whole arbitration/selection window | `mb87030.cpp` |
| 0003 | 98644 UART IRQ | the INS8250 interrupt was never wired to the DIO bus → OpenBSD's interrupt-driven `dca` stalled after 1–2 bytes | route UART int → board IC_IE gate → the DIP-selected DIO IRQ (mirrors hp98265a) | `hp98644.cpp` |
| 0004 | 98644 IRQ reset/savestate | the DIO IRQ was left asserted across reset and not re-driven after a savestate restore | `update_irq(false)` on reset + a `device_post_load` re-drive | `hp98644.cpp` |
| 0005 | m68k address error | the 010/020/030/040/070 stack frame encoded the **bus-error** vector (offset 0x008) instead of address-error (0x00C) | pass `EXCEPTION_ADDRESS_ERROR` to the frame builders | `m68kcpu.h` |
| 0006 | DIO shared IRQ/DMAR | the pull accessors used `& ~m_bus_index` (index-used-as-mask) which masked out real card bits; the line was driven by the last card's raw state (last-writer-wins) | maintain a per-source bitmap, drive the true wired-OR, transition only on a real line change | `hp_dio.cpp/.h` |
| 0007 | hp9k3xx IRQ6 + DIO32 reset | the 6840 PTM and any level-6 DIO card both drove `M68K_IRQ_6` directly (last-writer-wins, lost ticks); the DIO32 bus never received a CPU `RESET` | combine IRQ6 through `INPUT_MERGER_ANY_HIGH`; wire the DIO32 `reset_cb` like DIO16 | `hp9k_3xx.cpp` |
| 0008 | hp9k3xx bus-error R/W flag | the four bus-error handlers passed inconsistent/incorrect read/write args | make them correct + document why they are otherwise dead on the 010/020/030/040 (see audit §4 — a *negative* finding: it does not corrupt the guest SSW) | `hp9k_3xx.cpp` |
| 0009 | mb87030 double disconnect | on a fully-free bus the monitor and the `Idle` case both called `scsi_disconnect()` in one `step()` | `return` after the monitor fires (idempotent, so cosmetic) | `mb87030.cpp` |
| 0010 | 98644 card ID + loopback | the DIO card ID polarity was inverted (returned 0x02 natively where the real 98644A reports **0x42**, defaulting to the 98626-emulation value); a fake 1-byte board loopback shadow bypassed the INS8250's real LOOP | native ID 0x42 / 98626-emulation 0x02; delete the shadow → native 8250 LOOP | `hp98644.cpp` |
| 0011 | 98620 DMA reset | `device_reset` left the DMA channels armed and a DIO IRQ possibly asserted | disarm both channels, clear IRQ/enable, restore IRQ level 3 + byte size, `update_irq()` (address/TC preserved per the 98620C spec) | `hp98620.cpp` |
| 0012 | 98550/catseye per-plane IRQ | `catseye::update_int()` called the devcb with a single arg (offset 0, plane# as data) → every plane collapsed onto `m_ints` bit 0; deasserts left a stuck interrupt | pass `(plane, state)`; OR the shifted bit in `int_w`; re-evaluate on `m_intreg`/reset | `hp98550.cpp`, `catseye.cpp` |
| 0013 | 98644 modem DIP | the "Modem line enable" DIP (SW3) was read nowhere | off ⇒ strap CTS/DSR/RI/CD asserted on the board; on ⇒ follow the RS-232 peer (per 98644A ref manual p.3-3 / Fig 12-1) | `hp98644.cpp` |

## Provenance

Each fix maps 1:1 to a former per-fix PR branch (now flattened): 0001 `hp9k-nscsi-identify`, 0002
`hp9k-mb87030-selection`, 0003+0004 `hp98644-dio-irq`, 0005 `m68k-address-error-vector`, 0006
`hp98644-dio-wiredor`, 0007 `hp9k3xx-reset-irq6`, 0010+0013 (+0004) `hp98644-register-truing`, 0011
`hp98620-dma-reset`, 0012 `hp98550-catseye-irq`. 0008/0009 were hygiene commits on `hp9k-serial-harness`.
The panel verdict table (unanimous) and refuted candidates are in `../ACCURACY_REVIEW.md`.
