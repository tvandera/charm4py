import sys
import os
import shutil
import platform
import subprocess
import setuptools
from setuptools.command.build_ext import build_ext
from setuptools.command.build_py import build_py
from setuptools.command.install import install
from distutils.errors import DistutilsSetupError
from distutils import log
import distutils
import numpy

build_mpi = False

system = platform.system()
libcharm_filename2 = None
if system == "Windows" or system.lower().startswith("cygwin"):
    libcharm_filename = "charm.dll"
    libcharm_filename2 = "charm.lib"
    charmrun_filename = "charmrun.exe"
elif system == "Darwin":
    libcharm_filename = "libcharm.dylib"
    charmrun_filename = "charmrun"
else:
    libcharm_filename = "libcharm.so"
    charmrun_filename = "charmrun"


def charm_built(charm_src_dir):
    library_path = os.path.join(charm_src_dir, "charm", "lib", libcharm_filename)
    if not os.path.exists(library_path):
        return False
    charmrun_path = os.path.join(charm_src_dir, "charm", "bin", charmrun_filename)
    if not os.path.exists(charmrun_path):
        return False
    return True


def check_libcharm_version(charm_src_dir):
    import ctypes

    library_path = os.path.join(charm_src_dir, "charm", "lib", libcharm_filename)
    lib = ctypes.CDLL(library_path)
    with open(os.path.join(os.getcwd(), "src", "charm4py", "libcharm_version"), "r") as f:
        req_version = tuple(int(n) for n in f.read().split("."))
    commit_id_str = ctypes.c_char_p.in_dll(lib, "CmiCommitID").value.decode()
    version = [int(n) for n in commit_id_str.split("-")[0][1:].split(".")]
    try:
        version = tuple(version + [int(commit_id_str.split("-")[1])])
    except:
        version = tuple(version + [0])
    if version < req_version:
        req_str = ".".join([str(n) for n in req_version])
        cur_str = ".".join([str(n) for n in version])
        raise DistutilsSetupError(
            "Charm++ version >= " + req_str + " required. "
            "Existing version is " + cur_str
        )


def check_cffi():
    try:
        import cffi

        version = tuple(int(v) for v in cffi.__version__.split("."))
        if version < (1, 7):
            raise DistutilsSetupError(
                "Charm4py requires cffi >= 1.7. "
                "Installed version is " + cffi.__version__
            )
    except ImportError:
        raise DistutilsSetupError("cffi is not installed")


def build_libcharm(charm_src_dir, build_dir):

    lib_output_dirs = []
    charmrun_output_dirs = []
    lib_output_dirs.append(os.path.join(build_dir, "charm4py", ".libs"))
    lib_output_dirs.append(os.path.join(os.getcwd(), "charm4py", ".libs"))
    charmrun_output_dirs.append(os.path.join(build_dir, "charmrun"))
    charmrun_output_dirs.append(os.path.join(os.getcwd(), "charmrun"))
    for output_dir in lib_output_dirs + charmrun_output_dirs:
        distutils.dir_util.mkpath(output_dir)

    if not os.path.exists(charm_src_dir) or not os.path.isdir(charm_src_dir):
        raise DistutilsSetupError("charm sources dir " + charm_src_dir + " not found")

    if not charm_built(charm_src_dir):

        if system == "Windows" or system.lower().startswith("cygwin"):
            raise DistutilsSetupError(
                "Building charm++ from setup.py not currently supported on Windows."
                " Please download a Charm4py binary wheel (64-bit Python required)"
            )

        if os.path.exists(os.path.join(charm_src_dir, "charm.tar.gz")):
            log.info("Uncompressing charm.tar.gz...")
            cmd = ["tar", "xf", "charm.tar.gz"]
            p = subprocess.Popen(cmd, cwd=charm_src_dir, shell=False)
            rc = p.wait()
            if rc != 0:
                raise DistutilsSetupError(
                    "An error occured while building charm library"
                )

        # divide by 2 to not hog the system. On systems with hyperthreading, this will likely
        # result in using same # cores as physical cores (therefore not all the logical cores)
        import multiprocessing

        build_num_cores = max(
            int(
                os.environ.get(
                    "CHARM_BUILD_PROCESSES", multiprocessing.cpu_count() // 2
                )
            ),
            1,
        )
        extra_build_opts = os.environ.get("CHARM_EXTRA_BUILD_OPTS", "")
        if system == "Darwin":
            if build_mpi:
                cmd = (
                    "./build charm4py mpi-darwin-x86_64 -j"
                    + str(build_num_cores)
                    + " --with-production "
                    + extra_build_opts
                )
            else:
                cmd = (
                    "./build charm4py netlrts-darwin-x86_64 tcp -j"
                    + str(build_num_cores)
                    + " --with-production "
                    + extra_build_opts
                )
        else:
            try:
                arch = os.uname()[4]
            except:
                arch = None
            if arch is not None and arch.startswith("arm"):
                import re

                regexp = re.compile("armv(\d+).*")
                m = regexp.match(arch)
                if m:
                    version = int(m.group(1))
                    if version < 8:
                        cmd = (
                            "./build charm4py netlrts-linux-arm7 tcp -j"
                            + str(build_num_cores)
                            + " --with-production "
                            + extra_build_opts
                        )
                    else:
                        cmd = (
                            "./build charm4py netlrts-linux-arm8 tcp -j"
                            + str(build_num_cores)
                            + " --with-production "
                            + extra_build_opts
                        )
                else:
                    cmd = (
                        "./build charm4py netlrts-linux-arm7 tcp -j"
                        + str(build_num_cores)
                        + " --with-production "
                        + extra_build_opts
                    )
            elif arch == "ppc64le":
                if build_mpi:
                    cmd = (
                        "./build charm4py mpi-linux-ppc64le -j"
                        + str(build_num_cores)
                        + " --with-production "
                        + extra_build_opts
                    )
                else:
                    cmd = (
                        "./build charm4py netlrts-linux-ppc64le tcp -j"
                        + str(build_num_cores)
                        + " --with-production "
                        + extra_build_opts
                    )
            else:
                if build_mpi:
                    cmd = (
                        "./build charm4py mpi-linux-x86_64 -j"
                        + str(build_num_cores)
                        + " --with-production "
                        + extra_build_opts
                    )
                else:
                    cmd = (
                        "./build charm4py netlrts-linux-x86_64 tcp -j"
                        + str(build_num_cores)
                        + " --with-production "
                        + extra_build_opts
                    )
        p = subprocess.Popen(
            cmd.rstrip().split(" "),
            cwd=os.path.join(charm_src_dir, "charm"),
            shell=False,
        )
        rc = p.wait()
        if rc != 0:
            raise DistutilsSetupError("An error occured while building charm library")

        if system == "Darwin":
            old_file_path = os.path.join(charm_src_dir, "charm", "lib", "libcharm.so")
            new_file_path = os.path.join(
                charm_src_dir, "charm", "lib", libcharm_filename
            )
            shutil.move(old_file_path, new_file_path)
            cmd = [
                "install_name_tool",
                "-id",
                "@rpath/../.libs/" + libcharm_filename,
                new_file_path,
            ]
            p = subprocess.Popen(cmd, shell=False)
            rc = p.wait()
            if rc != 0:
                raise DistutilsSetupError("install_name_tool error")

    # verify that the version of charm++ that was built is same or greater than the
    # one required by charm4py
    check_libcharm_version(charm_src_dir)

    # ---- copy libcharm ----
    lib_src_path = os.path.join(charm_src_dir, "charm", "lib", libcharm_filename)
    for output_dir in lib_output_dirs:
        log.info(
            "copying "
            + os.path.relpath(lib_src_path)
            + " to "
            + os.path.relpath(output_dir)
        )
        shutil.copy(lib_src_path, output_dir)
    if libcharm_filename2 is not None:
        lib_src_path = os.path.join(charm_src_dir, "charm", "lib", libcharm_filename2)
        for output_dir in lib_output_dirs:
            log.info(
                "copying "
                + os.path.relpath(lib_src_path)
                + " to "
                + os.path.relpath(output_dir)
            )
            shutil.copy(lib_src_path, output_dir)

    # ---- copy charmrun ----
    charmrun_src_path = os.path.join(charm_src_dir, "charm", "bin", charmrun_filename)
    for output_dir in charmrun_output_dirs:
        log.info(
            "copying "
            + os.path.relpath(charmrun_src_path)
            + " to "
            + os.path.relpath(output_dir)
        )
        shutil.copy(charmrun_src_path, output_dir)


class custom_install(install, object):

    user_options = install.user_options + [("mpi", None, "Build libcharm with MPI")]

    def initialize_options(self):
        install.initialize_options(self)
        self.mpi = False

    def finalize_options(self):
        global build_mpi
        if not build_mpi:
            build_mpi = bool(self.mpi)
        install.finalize_options(self)

    def run(self):
        install.run(self)


class custom_build_py(build_py, object):

    user_options = build_py.user_options + [("mpi", None, "Build libcharm with MPI")]

    def initialize_options(self):
        build_py.initialize_options(self)
        self.mpi = False

    def finalize_options(self):
        global build_mpi
        if not build_mpi:
            build_mpi = bool(self.mpi)
        build_py.finalize_options(self)

    def run(self):
        if not self.dry_run:
            build_libcharm(os.path.join(os.getcwd(), "charm_src"), self.build_lib)
            shutil.copy(
                os.path.join(os.getcwd(), "LICENSE"),
                os.path.join(self.build_lib, "charm4py"),
            )
        super(custom_build_py, self).run()


class custom_build_ext(build_ext, object):

    user_options = build_ext.user_options + [("mpi", None, "Build libcharm with MPI")]

    def initialize_options(self):
        build_ext.initialize_options(self)
        self.mpi = False

    def finalize_options(self):
        global build_mpi
        if not build_mpi:
            build_mpi = bool(self.mpi)
        build_ext.finalize_options(self)

    def run(self):
        if not self.dry_run:
            build_libcharm(os.path.join(os.getcwd(), "charm_src"), self.build_lib)
        super(custom_build_ext, self).run()


extensions = []
py_impl = platform.python_implementation()

if py_impl == "PyPy":
    os.environ["CHARM4PY_BUILD_CFFI"] = "1"
elif "CPY_WHEEL_BUILD_UNIVERSAL" not in os.environ:
    # compile C-extension module (from cython)
    from Cython.Build import cythonize

    my_include_dirs = []
    my_lib_dirs = []
    extra_link_args = []

    if "CHARMPP_DIR" in os.environ:
        charmpp_dir = os.environ["CHARMPP_DIR"]
    else:
        charmpp_dir = "charm_src/charm"

    my_include_dirs += [
        numpy.get_include(),
        os.path.join(charmpp_dir, "include")]
    my_lib_dirs += [os.path.join(charmpp_dir, "lib")]

    extensions.extend(
        cythonize(
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
    )

additional_setup_keywords = {}
if os.environ.get("CHARM4PY_BUILD_CFFI") == "1":
    check_cffi()
    additional_setup_keywords["cffi_modules"] = (
        "charm4py/charmlib/charmlib_cffi_build.py:ffibuilder"
    )

setuptools.setup(
    ext_modules=extensions,
    cmdclass={
        "build_py": custom_build_py,
        "build_ext": custom_build_ext,
        "install": custom_install,
    },
    **additional_setup_keywords
)
