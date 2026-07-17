-- Step-0 serial-node probe (hp9k360 / OpenBSD 2.2). Log in at the framebuffer console via natkeyboard,
-- switch to /bin/sh (root's login shell is csh, in which the marker `for..do..done` would error),
-- MAKEDEV the dca nodes, then write a DISTINCT marker "HPSER_NODE_<dev>_END" + the dca dmesg to each
-- CALL-OUT node /dev/cuaN. Call-out is required: a dial-in /dev/ttyN open BLOCKS on a DCD carrier MAME
-- never asserts (guest dca.c:381), while /dev/cuaN forces TS_CARR_ON (dca.c:360). Each write is
-- backgrounded so one blocked open can't stall the loop. The host (reading the sl2 98644 -> socket 1250)
-- learns which node reaches the serial line from whichever marker arrives. Snapshots capture the dmesg
-- enumeration + node listing as out-of-band truth (login gate ~205s: proven boot-to-login is ~206s, and
-- posting keys before login: risks the hilint NULL-deref panic).
local function snap() manager.machine.video:snapshot() end
local phase, np = 0, 0
emu.register_periodic(function()
    local t = emu.time()
    local nk = manager.machine.natkeyboard
    if     phase==0  and t>=205 then nk:post("root\r"); phase=1; np=t+6
    elseif phase==1  and t>=np  then nk:post("\r"); phase=2; np=t+4              -- TERM = (default)
    elseif phase==2  and t>=np  then nk:post("/bin/sh\r"); phase=3; np=t+4       -- csh -> sh
    elseif phase==3  and t>=np  then nk:post("stty sane\r"); phase=4; np=t+4
    elseif phase==4  and t>=np  then
        nk:post("cd /dev && ./MAKEDEV dca0 dca1 dca2 dca3 2>/dev/null; cd /\r"); phase=5; np=t+15
    elseif phase==5  and t>=np  then
        nk:post("clear; dmesg | grep -i dca; ls -l /dev/tty0 /dev/tty1 /dev/cua0 /dev/cua1 /dev/cua2 /dev/cua3 2>&1\r"); phase=6; np=t+14
    elseif phase==6  and t>=np  then snap(); phase=7; np=t+6                     -- <- enumeration snapshot
    elseif phase==7  and t>=np  then
        nk:post("for d in cua0 cua1 cua2 cua3; do ( echo HPSER_NODE_${d}_END; dmesg | grep -i dca | head -2 ) > /dev/$d 2>/dev/null & done; sleep 6\r"); phase=8; np=t+30
    elseif phase==8  and t>=np  then snap(); phase=9; np=t+10
    elseif phase==9  and t>=np  then nk:post("ls -l /dev/cua* /dev/tty0 /dev/tty1 2>&1\r"); phase=10; np=t+8
    elseif phase==10 and t>=np  then snap(); phase=11
    end
end)
