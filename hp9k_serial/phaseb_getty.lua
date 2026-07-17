-- Phase B core: enable a getty on the dca serial /dev/tty0, then HUP init so it spawns. /etc/ttys ships
-- only tty00-07 (= the absent DCM mux), so add a tty0 line for our 98644 dca. After HUP, init runs
-- getty on /dev/tty0 -> "login:" over the socket; the Python side then logs in over serial (no natkeyboard).
local phase, np = 0, 0
local function snap() manager.machine.video:snapshot() end
emu.register_periodic(function()
    local t = emu.time()
    local nk = manager.machine.natkeyboard
    if     phase==0 and t>=205 then nk:post("root\r"); phase=1; np=t+6
    elseif phase==1 and t>=np  then nk:post("\r"); phase=2; np=t+4            -- TERM = (default)
    elseif phase==2 and t>=np  then nk:post("/bin/sh\r"); phase=3; np=t+4     -- csh -> sh
    elseif phase==3 and t>=np  then nk:post("stty sane\r"); phase=4; np=t+5
    elseif phase==4 and t>=np  then
        nk:post("grep -q '^tty0[^0-9]' /etc/ttys || printf 'tty0 \"/usr/libexec/getty std.9600\" unknown on secure\\n' >> /etc/ttys; echo TTYSDONE=$?\r"); phase=5; np=t+8
    elseif phase==5 and t>=np  then snap(); nk:post("kill -HUP 1\r"); phase=6; np=t+8
    elseif phase==6 and t>=np  then snap(); phase=7                          -- getty should now own /dev/tty0
    end
end)
