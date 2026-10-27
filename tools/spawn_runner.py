# -*- coding: utf-8 -*-
"""spawn 模式 runner：spawn app -> attach -> hook -> 落盘"""
import frida, time, sys

OUT = open("D:/aivg188/capture_frida.jsonl", "a", encoding="utf-8")

def on_msg(m, d):
    p = m.get("payload")
    if p:
        OUT.write(p.replace("\n", "\\n") + "\n")
        OUT.flush()
        print("CAP:", p.strip().splitlines()[0][:110], flush=True)
    else:
        print("META:", str(m)[:250], flush=True)

dev = frida.get_usb_device()
pid = dev.spawn(["ai.video.generator.text.video"])
session = dev.attach(pid)
script = session.create_script(open("D:/aivg188/hook_spawn.js", encoding="utf-8").read())
script.on("message", on_msg)
script.load()
dev.resume(pid)
print("[runner] resumed pid", pid, flush=True)
while True:
    time.sleep(1)
