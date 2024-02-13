#!/usr/bin/env python3

from time import sleep
import subprocess
import selectors
import os
import sys

proc = subprocess.Popen([ sys.executable, "-m", "charm4py.interactive"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        )

sel = selectors.DefaultSelector()
sel.register(proc.stdout, selectors.EVENT_READ, "stdout")
sel.register(proc.stderr, selectors.EVENT_READ, "stderr")

with open("test1.in", "rb") as input:
    for line in input:
        print("--> ", line.decode())
        proc.stdin.write(line)
        proc.stdin.flush()

        events = sel.select()
        for key, mask in events:
            data = os.read(key.fd, 128)
            print(f"<-- {key.data}:", data.decode())

proc.stdin.close()
proc.wait()