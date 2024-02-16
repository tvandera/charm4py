import subprocess
import sys
import os
import json
import logging
from itertools import product

logging.basicConfig(level=logging.INFO)

# ----------------------------------------------------------------------------------
NUM_PARALLEL = 12
TIMEOUT = 60  # timeout for each test (in seconds)
COMMON_ARGS = ['++local']
DEFAULT_NPROCS = int(os.environ.get('CHARM4PY_TEST_NUM_PROCESSES', 4))
INTERFACES = ['ctypes', 'cython']
CONFIG_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "test_config.json")
with open(CONFIG_FILE, 'r') as infile:
        ALL_TESTS = json.load(infile)

def is_enabled(test):
    try:
        import numba
        numbaInstalled = True
    except:
        numbaInstalled = False

    if 'condition' in test:
        if test['condition'] == 'numbaInstalled' and not numbaInstalled:
            return False
        if test['condition'] == 'not numbaInstalled' and numbaInstalled:
            return False

        return test['condition']

    return True

def test_run(name, interface):
    test = ALL_TESTS[name]
    fullname = name.replace("/", "_") + '-' + interface

    charmrun = 'charmrun'
    prefix = test.get('prefix') # extra args before 'python'
    python = sys.executable  # python interpreter path
    path = test['path'] # .py test file
    args = test.get('args', '').split(' ') + COMMON_ARGS
    nproc = str(max(test.get('force_min_processes', DEFAULT_NPROCS), DEFAULT_NPROCS))

    cmd = [ charmrun, prefix, python, path ] + args + [ '+p', nproc, '+libcharm_interface', interface ]

    # remove empty strings from list
    cmd = [ arg for arg in cmd if arg ]

    os.makedirs("test_output", exist_ok=True)
    error_file = f"test_output/{fullname}.err"
    output_file = f"test_output/{fullname}.out"

    logging.debug("Command:\n%s", " ".join(cmd))
    logging.debug("output log in: %s", output_file)
    logging.debug("errror log in: %s", error_file)

    with open(output_file, "w") as stderr, open(error_file, "w") as stdout:
        subprocess.check_call(cmd, stderr=stderr, stdout=stdout, timeout=TIMEOUT)

def pytest_generate_tests(metafunc):
    names = [ name for name,config in ALL_TESTS.items() if is_enabled(config) ]
    runs = product(names, INTERFACES)
    metafunc.parametrize("name,interface", runs)

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main())