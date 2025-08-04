cmake_minimum_required(VERSION 3.16)
project(ConvergenceAnalyzer VERSION 1.0.0 LANGUAGES CXX)

# 包含必要的CMake模块
include(CheckCXXSourceCompiles)
include(CheckCXXCompilerFlag)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# 优先使用clang++-20编译器
find_program(CLANG_20 clang++-20)
if(CLANG_20)
    set(CMAKE_CXX_COMPILER ${CLANG_20})
    message(STATUS "Found clang++-20: ${CLANG_20}")
else()
    find_program(CLANG_LATEST clang++)
    if(CLANG_LATEST)
        set(CMAKE_CXX_COMPILER ${CLANG_LATEST})
        message(STATUS "clang++-20 not found, using: ${CLANG_LATEST}")
    else()
        message(STATUS "No clang++ found, using default compiler: ${CMAKE_CXX_COMPILER}")
    endif()
endif()

# 设置C++标准 (使用C++20确保兼容性)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 检测libc++是否可用
set(LIBCXX_AVAILABLE FALSE)
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    # 测试libc++是否可用
    include(CheckCXXSourceCompiles)
    set(CMAKE_REQUIRED_FLAGS "-stdlib=libc++")
    check_cxx_source_compiles("
        #include <iostream>
        int main() { std::cout << \"test\"; return 0; }
    " LIBCXX_TEST)

    if(LIBCXX_TEST)
        set(LIBCXX_AVAILABLE TRUE)
        message(STATUS "libc++ is available and will be used")
    else()
        message(STATUS "libc++ is not available, using default standard library")
    endif()
    unset(CMAKE_REQUIRED_FLAGS)
endif()

# Clang特定的编译选项
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    # 基础编译选项
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Wextra -Wpedantic")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wno-unused-parameter -Wno-sign-compare")

    # 如果libc++可用，则使用它
    if(LIBCXX_AVAILABLE)
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -stdlib=libc++")
        # 添加libc++库路径和链接选项
        set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -L/usr/lib/llvm-20/lib -L/usr/lib/x86_64-linux-gnu -lc++ -lc++abi")
        message(STATUS "Using Clang with C++20 and libc++")
    else()
        message(STATUS "Using Clang with C++20 and default standard library")
    endif()

    # 优化选项
    set(CMAKE_CXX_FLAGS_DEBUG "-g -O0 -DDEBUG")
    set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG")
    set(CMAKE_CXX_FLAGS_RELWITHDEBINFO "-O2 -g -DNDEBUG")
    set(CMAKE_CXX_FLAGS_STATIC "-O3 -DNDEBUG -static")

    # 只在支持的情况下启用sanitizers和LTO
    if(CMAKE_BUILD_TYPE STREQUAL "Debug")
        # 检查sanitizer支持
        check_cxx_compiler_flag("-fsanitize=address" HAS_ASAN)
        check_cxx_compiler_flag("-fsanitize=undefined" HAS_UBSAN)

        if(HAS_ASAN)
            set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} -fsanitize=address")
        endif()
        if(HAS_UBSAN)
            set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} -fsanitize=undefined")
        endif()
    elseif(CMAKE_BUILD_TYPE STREQUAL "Release")
        # 检查LTO支持
        check_cxx_compiler_flag("-flto" HAS_LTO)
        if(HAS_LTO)
            set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -flto")
        endif()
    endif()

else()
    # 其他编译器的选项
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Wextra -O2")
    set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} -g -O0 -DDEBUG")
    set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -O3 -DNDEBUG")
    set(CMAKE_CXX_FLAGS_STATIC "${CMAKE_CXX_FLAGS_STATIC} -O3 -DNDEBUG -static")

    message(STATUS "Using ${CMAKE_CXX_COMPILER_ID} compiler")
endif()

# 查找必要的包
# 设置线程库查找选项
set(CMAKE_THREAD_PREFER_PTHREAD TRUE)
set(THREADS_PREFER_PTHREAD_FLAG TRUE)

# 如果使用libc++，需要添加库路径
if(LIBCXX_AVAILABLE)
    # 添加libc++库路径到链接器搜索路径
    link_directories(/usr/lib/llvm-20/lib)
    link_directories(/usr/lib/x86_64-linux-gnu)
endif()

find_package(Threads REQUIRED)
if(NOT Threads_FOUND)
    message(FATAL_ERROR "Threads library not found. Please install pthread development libraries.")
endif()

find_package(PkgConfig REQUIRED)

# 查找uuid库
pkg_check_modules(UUID REQUIRED uuid)
if(NOT UUID_FOUND)
    message(FATAL_ERROR "UUID library not found. Please install libuuid-dev (Ubuntu/Debian) or libuuid-devel (CentOS/RHEL)")
endif()

# 包含目录
include_directories(${CMAKE_CURRENT_SOURCE_DIR})
include_directories(${UUID_INCLUDE_DIRS})

# 源文件
set(SOURCES
    main.cpp
    convergence_monitor.cpp
    logger.cpp
    netlink_monitor.cpp
)

# 头文件
set(HEADERS
    convergence_monitor.h
    logger.h
    netlink_monitor.h
)

# 创建主可执行文件
add_executable(${PROJECT_NAME} ${SOURCES} ${HEADERS})

# 创建测试可执行文件
set(TEST_SOURCES
    test_unified_monitor.cpp
    convergence_monitor.cpp
    logger.cpp
    netlink_monitor.cpp
)

add_executable(test_unified_monitor ${TEST_SOURCES} ${HEADERS})

# 静态链接特殊处理
if(CMAKE_BUILD_TYPE STREQUAL "Static")
    # 设置静态链接选项
    set_target_properties(${PROJECT_NAME} PROPERTIES
        LINK_FLAGS "-static -static-libgcc -static-libstdc++"
    )

    # 对于静态链接，需要特殊处理某些库
    set(CMAKE_FIND_LIBRARY_SUFFIXES ".a")
    set(BUILD_SHARED_LIBS OFF)
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -static")
endif()

# 链接库
target_link_libraries(${PROJECT_NAME}
    Threads::Threads
    ${UUID_LIBRARIES}
)

# 为测试程序链接库
target_link_libraries(test_unified_monitor
    Threads::Threads
    ${UUID_LIBRARIES}
)

# 如果使用Clang，可能需要额外的链接库
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    # 如果使用libc++，可能需要libc++abi
    if(LIBCXX_AVAILABLE)
        find_library(LIBCXXABI_LIBRARY c++abi)
        if(LIBCXXABI_LIBRARY)
            target_link_libraries(${PROJECT_NAME} ${LIBCXXABI_LIBRARY})
            message(STATUS "Linking with libc++abi: ${LIBCXXABI_LIBRARY}")
        endif()
    endif()

    # 对于sanitizers，需要在编译和链接时都指定
    if(CMAKE_BUILD_TYPE STREQUAL "Debug")
        if(HAS_ASAN)
            target_link_options(${PROJECT_NAME} PRIVATE -fsanitize=address)
        endif()
        if(HAS_UBSAN)
            target_link_options(${PROJECT_NAME} PRIVATE -fsanitize=undefined)
        endif()
    endif()

    # 对于LTO，需要在链接时也指定
    if(CMAKE_BUILD_TYPE STREQUAL "Release" AND HAS_LTO)
        target_link_options(${PROJECT_NAME} PRIVATE -flto)
    endif()
endif()

# 链接目录
if(UUID_LIBRARY_DIRS)
    target_link_directories(${PROJECT_NAME} PRIVATE ${UUID_LIBRARY_DIRS})
endif()

# 编译定义
if(UUID_CFLAGS_OTHER)
    target_compile_definitions(${PROJECT_NAME} PRIVATE ${UUID_CFLAGS_OTHER})
endif()

# 安装规则
install(TARGETS ${PROJECT_NAME}
    RUNTIME DESTINATION bin
)

# 创建日志目录
install(DIRECTORY DESTINATION /var/log/frr
    DIRECTORY_PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE
                         GROUP_READ GROUP_EXECUTE
                         WORLD_READ WORLD_EXECUTE
)

# 打印配置信息
message(STATUS "=== Build Configuration ===")
message(STATUS "Project: ${PROJECT_NAME}")
message(STATUS "Version: ${PROJECT_VERSION}")
message(STATUS "C++ Compiler: ${CMAKE_CXX_COMPILER}")
message(STATUS "Compiler ID: ${CMAKE_CXX_COMPILER_ID}")
message(STATUS "Compiler Version: ${CMAKE_CXX_COMPILER_VERSION}")
message(STATUS "C++ Standard: ${CMAKE_CXX_STANDARD}")
message(STATUS "Build Type: ${CMAKE_BUILD_TYPE}")
message(STATUS "CXX Flags: ${CMAKE_CXX_FLAGS}")
if(CMAKE_BUILD_TYPE STREQUAL "Debug")
    message(STATUS "Debug Flags: ${CMAKE_CXX_FLAGS_DEBUG}")
elseif(CMAKE_BUILD_TYPE STREQUAL "Release")
    message(STATUS "Release Flags: ${CMAKE_CXX_FLAGS_RELEASE}")
endif()
message(STATUS "UUID Libraries: ${UUID_LIBRARIES}")
message(STATUS "UUID Include Dirs: ${UUID_INCLUDE_DIRS}")
message(STATUS "=== End Configuration ===")

# 添加自定义目标用于清理
add_custom_target(clean-all
    COMMAND ${CMAKE_BUILD_TOOL} clean
    COMMAND ${CMAKE_COMMAND} -E remove_directory ${CMAKE_BINARY_DIR}/CMakeFiles
    COMMAND ${CMAKE_COMMAND} -E remove ${CMAKE_BINARY_DIR}/CMakeCache.txt
    COMMAND ${CMAKE_COMMAND} -E remove ${CMAKE_BINARY_DIR}/cmake_install.cmake
    COMMAND ${CMAKE_COMMAND} -E remove ${CMAKE_BINARY_DIR}/Makefile
)

# 添加格式化目标（如果有clang-format）
find_program(CLANG_FORMAT clang-format)
if(CLANG_FORMAT)
    add_custom_target(format
        COMMAND ${CLANG_FORMAT} -i ${SOURCES} ${HEADERS}
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
        COMMENT "Formatting source code with clang-format"
    )
endif()

# 添加静态分析目标（如果有cppcheck）
find_program(CPPCHECK cppcheck)
if(CPPCHECK)
    add_custom_target(cppcheck
        COMMAND ${CPPCHECK} --enable=all --std=c++17 --verbose --quiet
                --error-exitcode=1 ${SOURCES}
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
        COMMENT "Running static analysis with cppcheck"
    )
endif()

# 设置默认构建类型
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

message(STATUS "Build configuration complete!")
