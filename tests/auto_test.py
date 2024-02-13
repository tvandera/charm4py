import time
import subprocess
import sys
import os
import shutil
from collections import defaultdict
import json
import logging

logging.basicConfig(level=logging.INFO)

# ----------------------------------------------------------------------------------
TIMEOUT = 60  # timeout for each test (in seconds)

commonArgs = ['++local']
default_num_processes = int(os.environ.get('CHARM4PY_TEST_NUM_PROCESSES', 4))

def is_enabled(test):
    if 'condition' in test:
        if test['condition'] == 'numbaInstalled' and not numbaInstalled:
            return False
        if test['condition'] == 'not numbaInstalled' and numbaInstalled:
            return False

        return test['condition']

    return True


def run_test(name, cmd):
    error_file = f"TestOutput/{name}.err"
    output_file = f"TestOutput/{name}.out"

    logging.debug("Command:\n%s", " ".join(cmd))
    logging.debug("output log in: %s", output_file)
    logging.debug("errror log in: %s", error_file)

    with open(output_file, "w") as stderr, open(error_file, "w") as stdout:
        try:
            subprocess.check_call(cmd, stderr=stderr, stdout=stdout, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            print(f"{name}: TIMEOUT")
        except subprocess.CalledProcessError:
            print(f"{name}: FAILED")
        else:
            print(f"{name}: PASSED")

try:
    import numba
    numbaInstalled = True
except:
    numbaInstalled = False

interfaces = ['ctypes', 'cython']

with open('test_config.json', 'r') as infile:
    tests = json.load(infile)

os.makedirs("TestOutput", exist_ok=True)

python = sys.executable

tests = [ t for t in tests if is_enabled(t) ]
for test in tests:
    nproc = max(test.get('force_min_processes', default_num_processes), default_num_processes)
    for interface in interfaces:
        name = test['path'].replace("/", "_") + '-' + interface

        cmd = [ 'charmrun', test.get('prefix', ''), python, test['path'], ] \
            + test.get('args', '').split(' ') \
            + commonArgs \
            + [ '+p', str(nproc), '+libcharm_interface', interface ]

        cmd = [ arg for arg in cmd if arg ]

        run_test(name, cmd)

