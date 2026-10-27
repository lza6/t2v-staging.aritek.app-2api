# -*- coding: utf-8 -*-
"""attach 已运行 AIVG 进程，hook 落盘"""
import frida, sys, time

PID = int(sys.argv[1])
d = frida.get_usb_device()
s = d.attach(PID)
sc = s.create_script(open("D:/aivg188/hook_bundle.js", encoding="utf-8").read())
f = open("D:/aivg188/capture_frida.jsonl", "a", encoding="utf-8")

def on(m, dd):
    p = m.get("payload")
    if p:
        f.write(p.replace("\n", "\\n") + "\n")
        f.flush()
        print("CAP:", p.strip().splitlines()[0][:110], flush=True)
    else:
        print("META:", str(m)[:250], flush=True)

sc.on("message", on)
sc.load()
print("[*] hooked pid", PID, flush=True)
while True:
    time.sleep(1)
