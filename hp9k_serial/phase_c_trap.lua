-- Phase C (#2): m68k crash-capture, the m68k analog of gdb/core register capture (no guest core needed).
-- Install a READ tap on the 68030 exception vector table (VBR+8 = bus error #2, VBR+C = address error #3).
-- On a fault the CPU fetches the handler address from the vector -> the tap fires BEFORE the handler runs,
-- so D0-D7/A0-A7 still hold the fault-time values; the faulting PC/SR live in the exception frame at SSP.
-- Dump registers + the raw frame to m68k_trap.log. Cycle-accurate MAME m68k => high-fidelity crash PC.
local cpu = manager.machine.devices[":maincpu"]
local pgm = cpu.spaces["program"]
local out = io.open("C:\\DocumentNoSnc\\CC\\mame\\hp9k_serial\\m68k_trap.log", "w")
local n, installed = 0, false

local function rv(name) return cpu.state[name].value end

local function dump(kind, vec)
    n = n + 1
    local ssp = rv("SSP")
    local s = string.format("\n=== M68K TRAP #%d %s (vec@%08x) ===\n", n, kind, vec)
    s = s .. string.format("PC=%08x SR=%04x USP=%08x SSP=%08x\n", rv("PC"), rv("SR") & 0xffff, rv("USP"), ssp)
    for i = 0, 7 do s = s .. string.format("D%d=%08x ", i, rv("D" .. i)) end
    s = s .. "\n"
    for i = 0, 7 do s = s .. string.format("A%d=%08x ", i, rv("A" .. i)) end
    s = s .. "\n"
    -- 68030 exception frame @ SSP: word0=SR, long@+2=PC, word@+6=format/vector; more for bus-error frames.
    s = s .. "frame@SSP:"
    for i = 0, 15 do s = s .. string.format(" %04x", pgm:read_u16(ssp + i * 2)) end
    s = s .. "\n"
    out:write(s); out:flush()
    print(s)
end

emu.register_periodic(function()
    if installed then return end
    if emu.time() < 200 then return end                 -- wait until OpenBSD has set VBR + reached multiuser
    local vbr = rv("VBR")
    pgm:install_read_tap(vbr + 0x08, vbr + 0x0b, "m68k_buserr",  function() dump("BUS_ERROR",  vbr + 0x08) end)
    pgm:install_read_tap(vbr + 0x0c, vbr + 0x0f, "m68k_addrerr", function() dump("ADDR_ERROR", vbr + 0x0c) end)
    installed = true
    local msg = string.format("[phase-c: m68k trap taps installed @ VBR=%08x (+8 buserr, +C addrerr)]\n", vbr)
    out:write(msg); out:flush(); print(msg)
end)
