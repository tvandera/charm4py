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

try:
    import numba
    numbaInstalled = True
except:
    numbaInstalled = False

# search for python executables
python_implementations = set()   # python implementations can also be added here manually
searchForPython(python_implementations)

interfaces = ['ctypes']

with open('test_config.json', 'r') as infile:
    tests = json.load(infile)

os.makedirs("TestOutput", exist_ok=True)

num_tests = 0
durations = defaultdict(dict)
for test in tests:
    if 'condition' in test:
        if test['condition'] == 'numbaInstalled' and not numbaInstalled:
            continue
        if test['condition'] == 'not numbaInstalled' and numbaInstalled:
            continue
        if not test['condition']:
            continue
    num_processes = max(test.get('force_min_processes', default_num_processes), default_num_processes)
    for interface in interfaces:
        durations[interface][test['path']] = []
        for version, python in sorted(python_implementations):
            name = "-".join( [ test['path'], f"python{version}" ] ).replace("/", "_")

            if version < test.get('requires_py_version', -1):
                continue
            additionalArgs = []
            if num_tests >= CHARM_QUIET_AFTER_NUM_TESTS and '++quiet' not in commonArgs:
                additionalArgs.append('++quiet')
            cmd = ['charmrun']
            if test.get('prefix'):
                cmd += [test['prefix']]
            if not test.get('interactive', False):
                cmd += [python] + [test['path']]
            else:
                cmd += [python] + ['-m', 'charm4py.interactive']
            if 'args' in test:
                cmd += test['args'].split(' ')
            cmd += commonArgs
            cmd += ['+p' + str(num_processes), '+libcharm_interface', interface]
            cmd += additionalArgs
            startTime = time.time()
            stderr = open(f"TestOutput/{name}.err", "w")
            stdout = open(f"TestOutput/{name}.out", "w")

            if test.get('interactive', False):
                p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=stderr, stdout=stdout)

                with open(test['path']) as stdin:
                    for line in stdin:
                        print("passing to proc: ", line)
                        p.stdin.write(line)
            else:
                # non-interactive
                p = subprocess.Popen(cmd, stderr=stderr, stdout=stdout)

            try:
                rc = p.wait(TIMEOUT)
            except subprocess.TimeoutExpired:
                print(f"{name}: TIMEOUT")
                logging.warning("Timeout (" + str(TIMEOUT) + " secs) expired when running " + test['path'] + ", Killing process")
                p.kill()
                rc = -1

            stderr.close()
            stdout.close()

            if rc != 0:
                print(f"{name}: FAILED")
                logging.warning("ERROR running test " + test['path'] + " with " + python)
                logging.warning("the command that failed was:\n", cmd)
            else:
                elapsed = round(time.time() - startTime, 3)
                durations[interface][test['path']].append(elapsed)
                print(f"{name}: PASSED")
                num_tests += 1


print("ALL TESTS (" + str(num_tests) + ") PASSED")
print("Durations:")
for interface in interfaces:
    print("\n---", interface, "---")
    for test, results in sorted(durations[interface].items()):
        print(test + ": " + str(results))
