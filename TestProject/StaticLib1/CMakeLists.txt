set(SOURCE_FILES_StaticLib1
    pch.cpp
    StaticLib1.cpp
)
set(HEADER_FILES_StaticLib1
    framework.h
    pch.h
)

add_library(StaticLib1 STATIC
    ${SOURCE_FILES_StaticLib1}
    ${HEADER_FILES_StaticLib1}
)

target_compile_definitions(StaticLib1 PRIVATE
    _WIN32_WINNT=0x0601
    WINVER=0x0601
    $<$<CONFIG:Debug>:_DEBUG;_LIB>
    $<$<CONFIG:Release>:NDEBUG;_LIB>
)

# Compiler options
target_compile_options(StaticLib1 PRIVATE
    /D_WIN32_WINNT=0x0601
    /DWINVER=0x0601
    $<$<CONFIG:Debug>:/W3>
    $<$<CONFIG:Debug>:/permissive->
    $<$<CONFIG:Debug>:/sdl>
    $<$<CONFIG:Release>:/Oi>
    $<$<CONFIG:Release>:/Gy>
    $<$<CONFIG:Release>:/W3>
    $<$<CONFIG:Release>:/permissive->
    $<$<CONFIG:Release>:/sdl>
)

# Linker options
target_link_options(StaticLib1 PRIVATE
    $<$<CONFIG:Debug>:/DEBUG>
    $<$<CONFIG:Release>:/DEBUG>
    $<$<CONFIG:Release>:/OPT:REF>
    $<$<CONFIG:Release>:/OPT:ICF>
)

# Output settings

# Precompiled header configuration
# PCH Header: pch.h
# PCH Source: pch.cpp
if(MSVC)
    # Add project directory to includes (VS does this implicitly for PCH)
    target_include_directories(StaticLib1 PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}
    )
    target_compile_options(StaticLib1 PRIVATE
        /Yu"pch.h"
        /FI"pch.h"  # Force include the PCH header
    )
    set_source_files_properties(pch.cpp PROPERTIES
        COMPILE_FLAGS "/Yc\"pch.h\""
    )
endif()

# File-specific compiler options
