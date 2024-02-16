import sys, os, subprocess
from glob import iglob
from os.path import join as join_path
import setuptools
from setuptools import Extension
from setuptools.command.build_ext import build_ext
from distutils.errors import DistutilsSetupError
from distutils import log
from pathlib import Path

from Cython.Build import cythonize
from Cython.Build.Dependencies import default_create_extension

log.set_verbosity(log.INFO)


def check_path(p, must_exist = True):
    if p is None:
        if must_exist:
            raise FileNotFoundError(p)

        return p

    p = Path(p)
    if p.exists():
        return p.absolute()

    if must_exist:
        raise FileNotFoundError(p)

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

    def initialize_options(self):
        self.numpy_enabled = True
        self.charm_source_archive = None
        self.charm_root = None
        self.charm_build_triplet =  None
        self.charm_build_opts = [ '--with-production', '-j12', '--force' ]
        self.wrapper_types = [ "ctypes", "cffi", "cython" ]
        build_ext.initialize_options(self)

    def check_paths(self):
        src = self.charm_source_archive
        root = self.charm_root

        # build unless proven found
        self.libcharm_found = False

        if src is not None and root is not None:
            raise DistutilsSetupError("--charm-root and --charm-source-archive are exclusive")

        if src is not None:
            self.charm_source_archive = check_path(src)
            return # build from source

        if root is not None:
            version = self.find_libcharm(root, must_exist=True)
            return # use found libcharm

        # try defaults
        default_root = check_path("charm_src/charm", must_exist=False)
        if default_root is not None:
            version  = self.find_libcharm(default_root, must_exist=False)
            if version is not None:
                return # use found libcharm

        default_src = check_path("charm_src/charm.tar.gz", must_exist=False)
        if default_src is not None:
            self.charm_source_archive = default_src
        else:
            raise DistutilsSetupError(
                "Could not find existing libcharm, nor source archive."
                "Use --charm-root or --charm-source-archive"
            )

    def finalize_options(self):
        self.check_paths()
        self.determine_triplet()
        super().finalize_options()

    def cythonize(self, ext):
        log.info(f"Cythonizing extension {ext.name}")

        if self.numpy_enabled:
            import numpy
            ext.include_dirs.append(numpy.get_include())

        ext, = cythonize(
                        ext,
                        build_dir="build",
                        compile_time_env= { 'HAVE_NUMPY': self.numpy_enabled }
                    )

        return ext

    def cythonize_extensions(self):
        self.extensions = [ self.cythonize(e) for e in self.extensions ]

    def update_extension(self, ext):
        log.info(f"Updating extensions {ext.name} after libcharm was built/found")

        # libcharm
        ext.include_dirs += [ str(self.libcharm / "include") ]
        ext.library_dirs += [ str(self.libcharm / "lib") ]
        ext.libraries += [ "charm" ]
        ext.extra_compile_args += ["-g0", "-O3"]

        return ext

    def run(self):
        self.build_libcharm_if_needed()

        self.extensions = [ self.update_extension(e) for e in self.extensions ]

        log.info("Now building python extension")
        super().run()

    def determine_triplet(self):
        if self.charm_build_triplet is not None:
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

        self.charm_build_triplet = "-".join((comm, system, arch))

    def libcharm_path(self, prefix):
        fname = {
                "windows" : "charm.dll",
                "darwin" : "libcharm.dylib",
                "linux" : "libcharm.so",
        }[sys.platform.lower()]

        return Path(prefix) / "lib" / fname

    def find_libcharm(self, prefix, must_exist = False):
        if prefix is None:
            if must_exist:
                raise FileNotFoundError(f"prefix: {prefix}")

            return None

        library_path = self.libcharm_path(prefix)
        log.info(f"Looking for {library_path}")
        if not library_path.exists() and must_exist:
            raise DistutilsSetupError(f"Could not find libcharm. '{library_path}' does not exist")

        try:
            import ctypes
            dll = ctypes.CDLL(library_path)
            commit_id_str = ctypes.c_char_p.in_dll(dll, "CmiCommitID").value.decode()
            version = tuple([int(n) for n in commit_id_str.split("-")[0][1:].split(".")])
        except Exception as e:
            if must_exist:
                raise DistutilsSetupError(f"Error deducing version from CmiCommitID\n{e}")

            return None

        if len(version) == 1 and version[0] >= 10000:
            v, = version
            version = ( v // 10000, (v // 100) % 100, v % 100 )
        log.info(f"Found charm version {version}")

        with open(os.path.join(os.getcwd(), "src", "charm4py", "libcharm_version"), "r") as f:
            required = tuple(int(n) for n in f.read().split("."))
            if len(required) < 3:
                raise DistutilsSetupError(f"Unexpect version format: {required}")

        log.info(f"Charm++ version >= {required} required. Existing version is {version}")

        if version < required:
            raise DistutilsSetupError(
                f"Charm++ version >= {required} required. Existing version is {version}"
            )

        self.libcharm_found = True
        self.libcharm_version = version
        self.libcharm = Path(prefix)

        return version

    def build_libcharm_if_needed(self) :
        if self.libcharm:
            log.info(f"libcharm version %s found in %s - not building", self.libcharm_version, self.libcharm)
            return

        source_archive = self.charm_source_archive
        if not os.path.exists(source_archive):
            raise DistutilsSetupError(f"Source archive {source_archive} does not exist")

        stage_dir = self.build_lib
        log.info(f"Uncompressing {source_archive} in {stage_dir}")
        os.makedirs(stage_dir, exist_ok=True)
        subprocess.check_call([ "tar", "xf", source_archive], cwd=stage_dir)

        build_dir = next(iglob(join_path(stage_dir, "charm*")))
        log.info(f"Building in {build_dir}")
        build_cmd = ["./build", "charm4py", self.charm_build_triplet ] + self.charm_build_opts
        log.info(f"Build cmd {build_cmd}")
        subprocess.check_call(build_cmd, cwd=build_dir)

        # verify that the version of charm++ that was built is same or greater than the
        # one required by charm4py
        self.find_libcharm(build_dir, must_exist=True)



def detect_numpy():
    try:
        import numpy
        return True, numpy.get_include()
    except:
        log.warn('WARNING: Building charmlib C-extension module without numpy support (numpy not found or import failed)')
        return False, []

have_numpy, numpy_include_dir = detect_numpy()

setuptools.setup(
    ext_modules=cythonize(
        Extension(
            'charm4py.charmlib.charmlib_cython',
            sources = [ "src/charm4py/charmlib/charmlib_cython.pyx" ],
            include_dirs = [ numpy_include_dir ]
        ),
        compile_time_env={'HAVE_NUMPY': have_numpy}
    ),
    cmdclass={
        "build_ext": CharmBuilder,
    },
)
