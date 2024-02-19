cmake_minimum_required(VERSION 3.15...3.26)
project(${SKBUILD_PROJECT_NAME} LANGUAGES C)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_SOURCE_DIR}/cmake")
find_package(Charm REQUIRED)

find_program(CYTHON "cython")

CONFIGURE_FILE(
  libcharm_config.py.in
  ${CMAKE_CURRENT_BINARY_DIR}/libcharm_config.py
  @ONLY
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/libcharm_config.py
        DESTINATION ${SKBUILD_PLATLIB_DIR}/charm4py/charmlib)

option(ENABLE_NUMPY "Enable support for numpy" ON)

if (ENABLE_NUMPY)
   set(NUMPY_COMPONENT "NumPy")
   set(HAVE_NUMPY 1)
else(ENABLE_NUMPY)
   set(NUMPY_COMPONENT "")
   set(HAVE_NUMPY 0)
endif(ENABLE_NUMPY)

find_package(
  Python
  COMPONENTS Interpreter Development.Module ${NUMPY_COMPONENT}
  REQUIRED
)

find_program(CYTHON "cython")

add_custom_command(
  OUTPUT ./charm4py/charmlib/charmlib_cython.c
  DEPENDS ./src/charm4py/charmlib/charmlib_cython.pyx
  VERBATIM
  COMMAND "${CYTHON}"
          -I${Python_NumPy_INCLUDE_DIRS}
          --compile-time-env HAVE_NUMPY=${HAVE_NUMPY}
          --output-file "${CMAKE_CURRENT_BINARY_DIR}/charm4py/charmlib/charmlib_cython.c"
          "${CMAKE_CURRENT_SOURCE_DIR}/src/charm4py/charmlib/charmlib_cython.pyx"
)

python_add_library(charmlib_cython
                   MODULE "${CMAKE_CURRENT_BINARY_DIR}/charm4py/charmlib/charmlib_cython.c"
                   WITH_SOABI)

target_link_libraries(charmlib_cython PUBLIC LibCharm::LibCharm)

if (ENABLE_NUMPY)
  target_link_libraries(charmlib_cython PUBLIC Python::NumPy)
endif(ENABLE_NUMPY)


install(
  TARGETS
  charmlib_cython
  DESTINATION charm4py/charmlib
)
