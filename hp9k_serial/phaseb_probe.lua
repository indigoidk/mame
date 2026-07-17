-- Phase B step 1: TX now works, so use the serial line itself to (a) dump the guest /etc/ttys to the
-- host over /dev/tty0, and (b) round-trip test RX (host->guest): print __RXREADY__, block reading a line
-- from /dev/tty0, echo it back as __RXGOT__[...]. If the host's "PING" comes back, RX is confirmed and the
-- interrupt fix is fully bidirectional (prerequisite for a getty).
local phase, np = 0, 0
local function snap() manager.machine.video:snapshot() end
emu.register_periodic(function()
    local t = emu.time()
    local nk = manager.machine.natkeyboard
    if     phase==0 and t>=205 then nk:post("root\r"); phase=1; np=t+6
    elseif phase==1 and t>=np  then nk:post("\r"); phase=2; np=t+4            -- TERM = (default)
    elseif phase==2 and t>=np  then nk:post("/bin/sh\r"); phase=3; np=t+4     -- csh -> sh
    elseif phase==3 and t>=np  then nk:post("stty sane\r"); phase=4; np=t+4
    elseif phase==4 and t>=np  then
        nk:post("cat /etc/ttys > /dev/tty0; echo __TTYS_END__ > /dev/tty0\r"); phase=5; np=t+12
    elseif phase==5 and t>=np  then snap()
        nk:post("echo __RXREADY__ > /dev/tty0; read L < /dev/tty0; echo __RXGOT__[$L] > /dev/tty0\r"); phase=6; np=t+30
    elseif phase==6 and t>=np  then snap(); phase=7
    end
end)
