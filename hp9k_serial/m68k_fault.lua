-- m68k_fault.lua v3 -- MAME 0.288 hp9k360/MC68030 crash-capture. On the 68030 a bad access is a PMMU
-- translation fault raised as a bus error that does NOT call debugger_exception_hook (m68kcpu.h: the sole
-- hook is at :1164; EXCEPTION_BUS_ERROR is "not emulated"), so `epset` misses it. Instead `bpset` on the
-- bus-error / address-error HANDLER PC (read from the vector table with a VIRTUAL readv_u32) -- a PC
-- breakpoint fires via the per-instruction hook however the fault arose. Capture is done in the bpset
-- ACTION (a debugger printf of all regs + the stacked fault PC/SR at A7), harvested from the console, at
-- the handler's first instruction (before it runs) so registers are fault-time. Needs -debug -debugger none.
local OUTFILE = "C:\\DocumentNoSnc\\CC\\mame\\hp9k_serial\\m68k_faults.log"
local ARM_AFTER = 205

local machine = manager.machine
local cpu = assert(machine.devices[":maincpu"], "no :maincpu")
local dbg = assert(machine.debugger, "requires -debug")
local cpu_debug = assert(cpu.debug, "no cpu.debug; use -debug")
local pgm = assert(cpu.spaces["program"], "no program space")
local out = assert(io.open(OUTFILE, "a")); out:setvbuf("no")
local function rv(n) local s = cpu.state[n]; return s and (s.value & 0xffffffff) or 0 end

-- debugger expression list (virtual mem reads via d@/w@); order matches the format below
local REGS = "d0,d1,d2,d3,d4,d5,d6,d7,a0,a1,a2,a3,a4,a5,a6,a7,pc,sr,d@(a7+2),w@a7,w@(a7+6)"
local function afmt(kind)
    return "M68KFLT " .. kind ..
        " D0=%08X D1=%08X D2=%08X D3=%08X D4=%08X D5=%08X D6=%08X D7=%08X" ..
        " A0=%08X A1=%08X A2=%08X A3=%08X A4=%08X A5=%08X A6=%08X A7=%08X" ..
        " PC=%08X SR=%04X FAULTPC=%08X FAULTSR=%04X FMTVEC=%04X\\n"
end

local armed, seen = false, 0

local function arm()
    if armed then return end
    dbg.visible_cpu = cpu
    local vbr = rv("VBR")
    local buserr  = pgm:readv_u32(vbr + 0x08)     -- vector 2 handler (virtual, MMU-translated read)
    local addrerr = pgm:readv_u32(vbr + 0x0c)     -- vector 3 handler
    dbg:command('bpset ' .. string.format("%X", buserr)  .. ',1,{printf "' .. afmt("BUS")  .. '",' .. REGS .. '}')
    dbg:command('bpset ' .. string.format("%X", addrerr) .. ',1,{printf "' .. afmt("ADDR") .. '",' .. REGS .. '}')
    armed = true
    out:write(string.format("--- armed: VBR=%08X buserr_handler=%08X addrerr_handler=%08X @ %.3f ---\n",
        vbr, buserr, addrerr, emu.time())); out:flush()
    print(string.format("[m68k-fault] bpset buserr=%08X addrerr=%08X", buserr, addrerr))
end

emu.register_periodic(function()
    if not armed then
        if emu.time() >= ARM_AFTER then arm() end
        return
    end
    local log = dbg.consolelog
    local n = #log
    if n < seen then seen = 0 end
    while seen < n do
        seen = seen + 1
        local line = tostring(log[seen] or "")
        if line:find("M68KFLT ", 1, true) then
            out:write(line .. "\n"); out:flush()
            print("[m68k-fault] CAPTURED " .. line)
        elseif line:find("Stopped", 1, true) or line:find("rror", 1, true) then
            out:write("CON: " .. line .. "\n"); out:flush()   -- surface Stopped/error lines for diagnosis
        end
    end
end)

cpu_debug:go()
