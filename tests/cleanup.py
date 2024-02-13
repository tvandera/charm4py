#!/usr/bin/env python3

import json

CONFIG_FILE = "test_config.json"

with open(CONFIG_FILE, 'r') as infile:
    tests = json.load(infile)

named_tests = {
    f"{i}-" + t["path"] : t
    for i,t in enumerate(tests)
}

print(json.dumps(named_tests))