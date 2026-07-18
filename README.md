# HP 9000 emulation — restoration & accuracy fixes (this fork)

This is a fork of MAME with a focused effort to **restore Hewlett-Packard HP 9000/300 (`hp9k3xx`)
emulation to a working state** and true up its device/CPU accuracy. Before this work every `hp9k3xx`
model was flagged `MACHINE_NOT_WORKING` and could not boot a real operating system. With the fixes below
the 9000/360 and 9000/370 boot **OpenBSD 2.2** and **HP-UX 9.10** to multiuser, and one of them resolves
the open upstream report [mamedev/mame#15076](https://github.com/mamedev/mame/issues/15076) (hp9k370
HP-UX SCSI panic — reproduced and fixed here).

Two SCSI patches restore booting; the remaining eleven are device/CPU **accuracy fixes** discovered and
adversarially verified during an **OpenBSD 2.2 emulation audit** (multi-model review — Codex 5.6-SOL +
Fable — cross-checked against HP hardware manuals and the NetBSD/OpenBSD hp300 drivers). The full audit,
negative findings, and an applyable `git am` patch series are on the **`hp9k-serial-harness`** branch
(`hp9k_serial/ACCURACY_REVIEW.md`, `hp9k_serial/patches/`); the same commits, linearized, are on
**`hp9k-emulation-fixes`**. Every fix rebases cleanly onto current upstream `master`.

### Restoring boot — SCSI fixes
| Fix | What was broken |
|-----|-----------------|
| **nscsi: clear stored IDENTIFY at new selection** | a stale LUN leaked across nexuses → the polled HP boot ROM saw the wrong LUN and the disk never enumerated |
| **mb87030: no deferred disconnect outside selection** | the 0.285 `b50b19b459` state-blind 10 ms auto-disconnect timer broke the polled boot ROM → "System Search Mode" and the HP-UX `scsi_if_isr: Service Req'd and no owner` panic — **the fix for #15076** |

### Accuracy fixes found in the OpenBSD 2.2 audit
| Fix | What was wrong |
|-----|-----------------|
| **hp98644: wire the INS8250 IRQ to the DIO bus** | the serial UART interrupt was never routed → interrupt-driven `dca` stalled after 1–2 bytes |
| **hp98644: deassert DIO IRQ on reset + re-drive after savestate** | the IRQ was left asserted across reset and not restored after a savestate |
| **m68k: address error stacks vector 3, not bus error** | the 010/020/030/040 frame encoded offset 0x008 (bus error) instead of 0x00C (address error) |
| **hp_dio: wired-OR the shared IRQ/DMAR lines** | an index-used-as-mask accessor masked real card bits; the CPU line followed the last writer |
| **hp9k3xx: merge IRQ6 + wire the DIO32 CPU reset** | the PTM and DIO both drove IRQ6 directly (lost timer ticks); DIO-II cards never received a CPU `RESET` |
| **hp9k3xx: correct the bus-error read/write flag** | inconsistent/dead R/W arguments (harmless on 010+, documented) |
| **mb87030: drop the redundant second scsi_disconnect** | bus-free could call `scsi_disconnect()` twice in one step |
| **hp98644: native card ID 0x42 + remove fake loopback** | the ID polarity was inverted (native should read 0x42, not 0x02) and a fake 1-byte loopback shadow bypassed the INS8250's real LOOP |
| **hp98620: disarm DMA channels + drop IRQ on reset** | reset left the DMA channels armed and a DIO IRQ possibly asserted |
| **hp98550 / catseye: fix per-plane interrupt aggregation** | a single-argument devcb collapsed every video plane onto one bit → a stuck interrupt |
| **hp98644: honor the "Modem line enable" DIP** | the DIP was read nowhere (when off it must strap CTS/DSR/RI/CD asserted) |

Each fix is built into a native hp9k binary and regression-verified (OpenBSD 2.2 boots to a serial login;
HP-UX 9.10 boots past the SCSI disk probe into fsck). Multi-model review verdicts were unanimous; refuted
candidates (negative findings) are recorded in the audit.

---

# MAME

## What is MAME?

MAME is a multi-purpose emulation framework.

MAME's purpose is to preserve decades of software history. As electronic technology continues to rush forward, MAME prevents this important "vintage" software from being lost and forgotten. This is achieved by documenting the hardware and how it functions. The source code to MAME serves as this documentation. The fact that the software is usable serves primarily to validate the accuracy of the documentation (how else can you prove that you have recreated the hardware faithfully?). Over time, MAME (originally stood for Multiple Arcade Machine Emulator) absorbed the sister-project MESS (Multi Emulator Super System), so MAME now documents a wide variety of (mostly vintage) computers, video game consoles and calculators, in addition to the arcade video games that were its initial focus.

## Where can I find out more?

* [Official MAME Development Team Site](https://www.mamedev.org/) (includes binary downloads, wiki, forums, and more)
* [MAME Testers](https://mametesters.org/) (official bug tracker for MAME)

### Community

* [MAME Forums on bannister.org](https://forums.bannister.org/ubbthreads.php?ubb=cfrm&c=5)
* [r/MAME](https://www.reddit.com/r/MAME/) on Reddit
* [MAMEWorld Forums](https://www.mameworld.info/ubbthreads/)

## Development

![Alt](https://repobeats.axiom.co/api/embed/8461d8ae4630322dafc736fc25782de214b49630.svg "Repobeats analytics image")

### CI status and code scanning

[![CI (Linux)](https://github.com/mamedev/mame/workflows/CI%20(Linux)/badge.svg)](https://github.com/mamedev/mame/actions/workflows/ci-linux.yml) [![CI (Windows](https://github.com/mamedev/mame/workflows/CI%20(Windows)/badge.svg)](https://github.com/mamedev/mame/actions/workflows/ci-windows.yml) [![CI (macOS)](https://github.com/mamedev/mame/workflows/CI%20(macOS)/badge.svg)](https://github.com/mamedev/mame/actions/workflows/ci-macos.yml) [![Compile UI translations](https://github.com/mamedev/mame/workflows/Compile%20UI%20translations/badge.svg)](https://github.com/mamedev/mame/actions/workflows/language.yml) [![Build documentation](https://github.com/mamedev/mame/workflows/Build%20documentation/badge.svg)](https://github.com/mamedev/mame/actions/workflows/docs.yml)  [![Coverity Scan Status](https://scan.coverity.com/projects/5727/badge.svg?flat=1)](https://scan.coverity.com/projects/mame-emulator)

### How to compile?

If you're on a UNIX-like system (including Linux and macOS), it could be as easy as typing

```
make
```

for a full build,

```
make SUBTARGET=tiny
```

for a build including a small subset of supported systems.

See the [Compiling MAME](http://docs.mamedev.org/initialsetup/compilingmame.html) page on our documentation site for more information, including prerequisites for macOS and popular Linux distributions.

For recent versions of macOS you need to install [Xcode](https://developer.apple.com/xcode/) including command-line tools and [SDL 2.0](https://github.com/libsdl-org/SDL/releases/latest).

For Windows users, we provide a ready-made [build environment](http://www.mamedev.org/tools/) based on MinGW-w64.

Visual Studio builds are also possible, but you still need [build environment](http://www.mamedev.org/tools/) based on MinGW-w64.
In order to generate solution and project files just run:

```
make vs2022
```
or use this command to build it directly using msbuild

```
make vs2022 MSBUILD=1
```

### Coding standard

MAME source code should be viewed and edited with your editor set to use four spaces per tab. Tabs are used for initial indentation of lines, with one tab used per indentation level. Spaces are used for other alignment within a line.

Some parts of the code follow [Allman style](https://en.wikipedia.org/wiki/Indent_style#Allman_style); some parts of the code follow [K&R style](https://en.wikipedia.org/wiki/Indent_style#K.26R_style) -- mostly depending on who wrote the original version. **Above all else, be consistent with what you modify, and keep whitespace changes to a minimum when modifying existing source.** For new code, the majority tends to prefer Allman style, so if you don't care much, use that.

All contributors need to either add a standard header for license info (on new files) or inform us of their wishes regarding which of the following licenses they would like their code to be made available under: the [BSD-3-Clause](http://opensource.org/licenses/BSD-3-Clause) license, the [LGPL-2.1](http://opensource.org/licenses/LGPL-2.1), or the [GPL-2.0](http://opensource.org/licenses/GPL-2.0).

See more specific [C++ Coding Guidelines](https://docs.mamedev.org/contributing/cxx.html) on our documentation web site.

## License

The MAME project as a whole is made available under the terms of the
[GNU General Public License, version 2](http://opensource.org/licenses/GPL-2.0)
or later (GPL-2.0+), since it contains code made available under multiple
GPL-compatible licenses.  A great majority of the source files (over 90%
including core files) are made available under the terms of the
[3-clause BSD License](http://opensource.org/licenses/BSD-3-Clause), and we
would encourage new contributors to make their contributions available under the
terms of this license.

Please note that MAME is a registered trademark of Gregory Ember, and permission
is required to use the "MAME" name, logo, or wordmark.

<a href="http://opensource.org/licenses/GPL-2.0" target="_blank">
<img align="right" width="100" src="https://opensource.org/wp-content/uploads/2009/06/OSIApproved.svg">
</a>

    Copyright (c) 1997-2026  MAMEdev and contributors

    This program is free software; you can redistribute it and/or modify it
    under the terms of the GNU General Public License version 2, as provided in
    docs/legal/GPL-2.0.

    This program is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
    FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
    more details.

Please see [COPYING](COPYING) for more details.
