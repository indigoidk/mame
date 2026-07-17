-- Bake a PERSISTENT serial getty into the image (one-time, via the framebuffer console/natkeyboard).
-- Append a tty0 getty line to /etc/ttys, then sync+halt so the write commits to the CHD. Afterwards the
-- image auto-runs getty on /dev/tty0 every boot with no per-run natkeyboard edit -> a real serial console.
-- Run against a COPY (obsd22_serial.chd), never the golden image.
local phase, np = 0, 0
emu.register_periodic(function()
    local t = emu.time()
    local nk = manager.machine.natkeyboard
    if     phase==0 and t>=205 then nk:post("root\r"); phase=1; np=t+6
    elseif phase==1 and t>=np  then nk:post("\r"); phase=2; np=t+4            -- TERM = (default)
    elseif phase==2 and t>=np  then nk:post("/bin/sh\r"); phase=3; np=t+4     -- csh -> sh
    elseif phase==3 and t>=np  then nk:post("stty sane\r"); phase=4; np=t+4
    elseif phase==4 and t>=np  then
        nk:post("grep -q '^tty0[^0-9]' /etc/ttys || printf 'tty0 \"/usr/libexec/getty std.9600\" unknown on secure\\n' >> /etc/ttys\r"); phase=5; np=t+8
    elseif phase==5 and t>=np  then nk:post("sync; sync; halt\r"); phase=6    -- commit /etc/ttys + clean shutdown
    end
end)
