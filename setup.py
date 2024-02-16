import sys
import os
from glob import iglob
from os.path import join as join_path
import subprocess
import setuptools
from setuptools.command.build_ext import build_ext
from distutils.errors import DistutilsSetupError
from distutils import log

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

def if_exists(path):
    from pathlib import Path

    path = Path(path)
    if not path.is_absolute():
        path = Path(__file__).parent / path

    if path.exists():
        return path

    return None


class CharmBuilder(build_ext):
    user_options = (
        build_ext.user_options +
        [
            ( "disable-numpy", None, "Disable numpy support" ),
            ( "charm-root=", None, "Existing pre-built charm++ prefix" ),
            ( "charm-source-archive=", None, "Charm++ source archive to build" ),
            ( "charm-build-triplet=", None, "Charm++ build triplet" ),
            ( "charm-build-opts=", None, "Extra options to pass to ./build after triplet" ),
            ( "charm-wappers=", None, "cython, ctypes, and/or cffi" ),
        ]
    )

    charmroot = "woopp"

    def initialize_options(self):
        print("Initiliazing options")
        self.numpy_enabled = True
        self.charm_root = "blubber" # if_exists("charm_src/charm")
        self.charm_source_archive = if_exists("charm_src/charm.tar.gz")
        self.charm_build_triplet =  None
        self.charm_build_opts =  None
        self.wrapper_types = [ "ctypes", "cffi", "cython" ]
        build_ext.initialize_options(self)

    def finalize_options(self) -> None:
        build_ext.finalize_options(self)

    def run(self):
        print("self.charm_root = ", self.charm_root)

        charm_version = self.find_charm(must_exist=False)
        if charm_version:
            log.info(f"Found charm version {charm_version}. Not building")
            self.validate_charm_version(charm_version)
        else:
            log.info(f"Building charm in tree")
            self.build_libcharm()

        log.info("Now building python extension")

        # from Cython.Build import cythonize
        # self.distribution.extensions = cythonize(
        #     setuptools.Extension(
        #         "charm4py.charmlib.charmlib_cython",
        #         sources=["src/charm4py/charmlib/charmlib_cython.pyx"],
        #         include_dirs = [ numpy.get_include() ],
        #         library_dirs = [],
        #         libraries = [],
        #         extra_compile_args=["-g0", "-O3"],
        #         extra_link_args= [],
        #     ),
        #     build_dir="build",
        #     compile_time_env={'HAVE_NUMPY': True},
        # )

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

        if prefix is None:
            return None

        library_path = self.libcharm_fullpath(prefix)
        log.info(f"Looking for {library_path}")
        try:
            dll = ctypes.CDLL(library_path)
            commit_id_str = ctypes.c_char_p.in_dll(dll, "CmiCommitID").value.decode()
            version = tuple([int(n) for n in commit_id_str.split("-")[0][1:].split(".")])
        except:
            if must_exist:
                raise DistutilsSetupError(f"Could not find libcharm. '{library_path}' does not exist")

            return None

        if len(version) == 1 and version[0] >= 10000:
            v, = version
            version = ( v // 10000, (v // 100) % 100, v % 100 )

        log.info(f"Found charm version {version}")
        self.validate_charm_version(version)

        self.include_dirs.append(join_path(prefix, 'include'))
        self.library_dirs.append(join_path(prefix, 'lib'))
        self.extra_link_args.append("-Wl,-rpath," + join_path(prefix, 'lib'))
        self.libraries.append('charm')

        return version

    def validate_charm_version(self, actual):
        assert len(actual) >= 3, f"Invalid version format for actual: {actual}"
        with open(os.path.join(os.getcwd(), "src", "charm4py", "libcharm_version"), "r") as f:
            required = tuple(int(n) for n in f.read().split("."))

        log.info(f"Charm++ version >= {required} required. Existing version is {actual}")

        if actual < required:
            raise DistutilsSetupError(
                f"Charm++ version >= {required} required. Existing version is {actual}"
            )

    def build_libcharm(self) :
        source_archive = self["CHARM_SOURCE_ARCHIVE"]
        if not os.path.exists(source_archive):
            raise DistutilsSetupError(f"Source archive {source_archive} does not exist")

        stage_dir = self.build_lib
        log.info(f"Uncompressing {source_archive} in {stage_dir}")
        subprocess.check_call([ "tar", "xf", source_archive], cwd=stage_dir)

        build_dir = next(iglob(join_path(stage_dir, "charm*")))
        log.info(f"Building in {build_dir}")
        build_cmd = ["./build", "charm4py", self.build_triplet ] + self.build_opts
        log.info(f"Build cmd {build_cmd}")
        subprocess.check_call(build_cmd, cwd=build_dir)

        # verify that the version of charm++ that was built is same or greater than the
        # one required by charm4py
        built_version = self.find_charm(build_dir, must_exist=True)
        self.validate_charm_version(built_version)



setuptools.setup(
    cmdclass={
        "build_ext": CharmBuilder,
    },
)
