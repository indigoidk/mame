-- H1/H2 confirmation (Fable). Foreground-write to the DIAL-IN /dev/tty0. Per null_modem.cpp:89-91 the
-- null_modem ASSERTS DCD/DSR/CTS at reset -> ins8250 MSR DCD -> dca.c:360 sets TS_CARR_ON, so the tty0
-- open does NOT block (unlike cua0's sc_cua self-deadlock, dca.c:381). Expect EXACTLY ~1 byte ('H') at
-- the host: dcastart writes byte 1 then stalls waiting for a THRE interrupt the hp98644 never delivers
-- (no IRQ wiring). 1 byte => H1 (cua deadlock was the 0-byte cause) AND H2 (missing-IRQ cap) both confirmed.
local phase, np = 0, 0
local function snap() manager.machine.video:snapshot() end
emu.register_periodic(function()
    local t = emu.time()
    local nk = manager.machine.natkeyboard
    if     phase==0 and t>=205 then nk:post("root\r"); phase=1; np=t+6
    elseif phase==1 and t>=np  then nk:post("\r"); phase=2; np=t+4          -- TERM = (default)
    elseif phase==2 and t>=np  then nk:post("/bin/sh\r"); phase=3; np=t+4   -- csh -> sh
    elseif phase==3 and t>=np  then nk:post("stty sane\r"); phase=4; np=t+4
    elseif phase==4 and t>=np  then snap(); nk:post("printf HPSERBYTES > /dev/tty0; echo RC=$?\r"); phase=5; np=t+15
    elseif phase==5 and t>=np  then snap(); phase=6; np=t+8               -- shell likely hung in close()
    elseif phase==6 and t>=np  then snap(); phase=7
    end
end)
