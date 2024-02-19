cmake_minimum_required(VERSION 3.15...3.26)
project(${SKBUILD_PROJECT_NAME} LANGUAGES C)

option(HAVE_NUMPY "Enable support for numpy" ON)

find_package(
  Python
  COMPONENTS Interpreter Development.Module
  REQUIRED)

find_program(CYTHON "cython")

add_custom_command(
  OUTPUT ./charmlib_cython.c
  DEPENDS ./src/charm4py/charmlib/charmlib_cython.pyx
  VERBATIM
  COMMAND "${CYTHON}"
          --compile-time-env HAVE_NUMPY=${HAVE_NUMPY}
          --output-file "${CMAKE_CURRENT_BINARY_DIR}/charmlib_cython.c"
          "${CMAKE_CURRENT_SOURCE_DIR}/src/charm4py/charmlib/charmlib_cython.pyx"
)

python_add_library(charmlib_cython MODULE "${CMAKE_CURRENT_BINARY_DIR}/charmlib_cython.c"
                   WITH_SOABI)

install(TARGETS charmlib_cython DESTINATION .)