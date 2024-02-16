import sys
import os
from os.path import join as join_path
import subprocess
import setuptools
from setuptools.command.build_ext import build_ext
from setuptools.command.build_py import build_py
from setuptools.command.install import install
from distutils.errors import DistutilsSetupError
from distutils import log
import distutils
import numpy

import ctypes

log.set_verbosity(log.INFO)

# configuration defaults
# these can be overriden via environment variabels
CONFIG_SETTINGS = {
    # disable numpy
    "NUMPY_ENABLED": True,

    # pre-compiled charmrun and libcharm from CHARM_ROOT
    # try to compile from src when set to None
    "CHARM_ROOT": "charm_src/charm",

    # charm++ source archive to use when building libcharm from source
    "CHARM_SOURCE_ARCHIVE": "charm_src/charm.tar.gz",

    # arguments to pass to "./build" when building charm
    # when not set, try to find a good default
    "CHARM_BUILD_OPTS" : None,

    # what package to use for wrapping the C++ code
    # valid options: cython, cffi, ctypes
    "CHARM4PY_WRAPPER_TYPE":  "cython",
}


class CharmBuilder(build_ext, object):
    VALID_WRAPPERS = [ "cython", "cffi", "ctypes", ]

    def __init__(self, dist, *args):
        self.set_config()
        super().__init__(dist, *args)

    def run(self):
        charm_version = self.find_charm(must_exist=False)
        if charm_version:
            log.info(f"Found charm version {charm_version}. Not building")
            self.validate_charm_version(charm_version)
        else:
            log.info(f"Building charm in tree")
            self.build_libcharm()

        log.info("Now building python extension")
        super().run()

    def determin_triplet(self):
        if self.build_triplet is not None:
            return

        import platform
        comm = "netlrts" # always netlrts (aka tcp)
        system = {
            "Darwin" : "darwin",
            "Linux" : "linux",
            "Windows" : "win",
        }[platform.system()]
        arch =  {
            "arm64" : "arm8",
            "AMD64" : "x86_64",
        }[platform.machine()]

        self.build_triplet = "-".join((comm, system, arch))

    def __getitem__(self, key):
        return self.__config__[key]

    def validate_config(self):
        assert self.wrapper_type in self.VALID_WRAPPERS, \
            f"Unknown wrapper type: {self.wrapper_type}, choose from {self.VALID_WRAPPERS}"

    @property
    def charm_root(self):
        return self["CHARM_ROOT"]

    @property
    def wrapper_type(self):
        return self["CHARM4PY_WRAPPER_TYPE"]

    @property
    def build_opts(self):
        return self["CHARM_BUILD_OPTS"]

    @property
    def numpy_enabled(self):
        return self["NUMPY_ENABLED"]

    def libcharm_filenames(self):
        return {
                "windows" : "charm.dll",
                "darwin" : "libcharm.dylib",
                "linux" : "libcharm.so",
        }[sys.platform.lower()]

    def libcharm_fullpath(self, prefix):
        fname = self.libcharm_filenames()
        return join_path(prefix, "lib", fname)

    def find_charm(self, prefix = None, must_exist = False):
        if prefix is None:
            prefix = self.charm_root

        library_path = self.libcharm_fullpath(prefix)
        log.info(f"Looking for {library_path}")
        try:
            dll = ctypes.CDLL(library_path)
            commit_id_str = ctypes.c_char_p.in_dll(dll, "CmiCommitID").value.decode()
            version = [int(n) for n in commit_id_str.split("-")[0][1:].split(".")]
            return tuple(version)
        except:
            pass

        if must_exist:
            raise DistutilsSetupError(f"Could not find libcharm. '{library_path}' does not exist")

        return None

    def check_charm_version(self, actual):
        with open(os.path.join(os.getcwd(), "src", "charm4py", "libcharm_version"), "r") as f:
            required = tuple(int(n) for n in f.read().split("."))

        if actual < required:
            raise DistutilsSetupError(
                f"Charm++ version >= {required} required. Existing version is {actual}"
            )

    def build_libcharm(self) :
        source_archive = self["CHARM_SOURCE_ARCHIVE"]
        if not os.path.exists(source_archive):
            raise DistutilsSetupError(f"Source archive {source_archive} does not exist")

        import tempfile
        with tempfile.TemporaryDirectory() as build_dir:
            log.info(f"Uncompressing {source_archive}")
            subprocess.check_call([ "tar", "xf", source_archive])

            log.info(f"Building in {build_dir}")
            subprocess.check_call(["./build", "charm4py", "--with-production" ])

            # verify that the version of charm++ that was built is same or greater than the
            # one required by charm4py
            built_version = self.find_charm(build_dir)
            self.check_charm_version(built_version)


# compile C-extension module (from cython)
from Cython.Build import cythonize

my_include_dirs = []
my_lib_dirs = []
extra_link_args = []

charmpp_dir = os.environ.get("CHARMPP_DIR", "charm_src/charm")

my_include_dirs += [
    numpy.get_include(),
    os.path.join(charmpp_dir, "include")]
my_lib_dirs += [os.path.join(charmpp_dir, "lib")]

extension = cythonize(
        setuptools.Extension(
            "charm4py.charmlib.charmlib_cython",
            sources=["src/charm4py/charmlib/charmlib_cython.pyx"],
            include_dirs=my_include_dirs,
            library_dirs=my_lib_dirs,
            libraries=["charm"],
            extra_compile_args=["-g0", "-O3"],
            extra_link_args=extra_link_args,
        ),
        build_dir="build",
        compile_time_env={'HAVE_NUMPY': True},
    )

setuptools.setup(
    ext_modules=extension,
    cmdclass={
        "build_ext": CharmBuilder,
    },
)
