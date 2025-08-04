#!/bin/bash

# 静态编译脚本 - 专为Alpine Linux x64优化
# 
# 使用方法:
#   ./build-static.sh           # 使用musl libc静态编译
#   ./build-static.sh glibc     # 使用glibc静态编译
#   ./build-static.sh clean     # 清理构建文件

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检测系统类型
detect_system() {
    if [ -f /etc/alpine-release ]; then
        echo "alpine"
    elif [ -f /etc/debian_version ]; then
        echo "debian"
    elif [ -f /etc/redhat-release ]; then
        echo "redhat"
    else
        echo "unknown"
    fi
}

# 检查Alpine Linux依赖
check_alpine_dependencies() {
    print_info "检查Alpine Linux静态编译依赖..."
    
    local missing_packages=()
    
    # 检查必要的包
    if ! apk info -e cmake >/dev/null 2>&1; then
        missing_packages+=("cmake")
    fi
    
    if ! apk info -e build-base >/dev/null 2>&1; then
        missing_packages+=("build-base")
    fi
    
    if ! apk info -e musl-dev >/dev/null 2>&1; then
        missing_packages+=("musl-dev")
    fi
    
    if ! apk info -e util-linux-dev >/dev/null 2>&1; then
        missing_packages+=("util-linux-dev")
    fi
    
    if ! apk info -e linux-headers >/dev/null 2>&1; then
        missing_packages+=("linux-headers")
    fi
    
    if ! apk info -e pkgconfig >/dev/null 2>&1; then
        missing_packages+=("pkgconfig")
    fi
    
    if [ ${#missing_packages[@]} -gt 0 ]; then
        print_error "缺少以下包，请先安装："
        printf '%s\n' "${missing_packages[@]}"
        print_info "运行以下命令安装："
        echo "apk add ${missing_packages[*]}"
        exit 1
    fi
    
    print_success "Alpine Linux依赖检查完成"
}

# 检查通用依赖
check_general_dependencies() {
    print_info "检查通用静态编译依赖..."
    
    # 检查cmake
    if ! command -v cmake &> /dev/null; then
        print_error "cmake 未安装"
        exit 1
    fi
    
    # 检查编译器
    if ! command -v gcc &> /dev/null && ! command -v clang &> /dev/null; then
        print_error "未找到C++编译器 (gcc 或 clang)"
        exit 1
    fi
    
    print_success "通用依赖检查完成"
}

# 清理构建文件
clean_build() {
    print_info "清理静态构建文件..."
    
    if [ -d "build-static" ]; then
        rm -rf build-static
        print_success "静态构建目录已清理"
    else
        print_info "静态构建目录不存在，无需清理"
    fi
}

# 静态编译项目
build_static() {
    local libc_type=${1:-musl}
    
    print_info "开始静态编译 (libc类型: $libc_type)..."
    
    # 创建静态构建目录
    mkdir -p build-static
    cd build-static
    
    # 设置编译器和标志
    local cmake_args="-DCMAKE_BUILD_TYPE=Static"
    local static_flags="-static"
    
    if [ "$libc_type" = "musl" ]; then
        print_info "使用musl libc进行静态编译..."
        # musl特定的设置
        cmake_args="$cmake_args -DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++"
        static_flags="$static_flags -static-libgcc -static-libstdc++"
        
        # 设置环境变量
        export CC=gcc
        export CXX=g++
        export CFLAGS="-static"
        export CXXFLAGS="-static"
        export LDFLAGS="-static -static-libgcc -static-libstdc++"
        
    elif [ "$libc_type" = "glibc" ]; then
        print_info "使用glibc进行静态编译..."
        # glibc特定的设置
        static_flags="$static_flags -static-libgcc -static-libstdc++"
        
        export LDFLAGS="-static -static-libgcc -static-libstdc++"
    fi
    
    # 配置项目
    print_info "配置CMake..."
    cmake $cmake_args \
        -DCMAKE_EXE_LINKER_FLAGS="$static_flags" \
        -DCMAKE_FIND_LIBRARY_SUFFIXES=".a" \
        -DBUILD_SHARED_LIBS=OFF \
        ..
    
    # 编译
    print_info "编译项目..."
    local cpu_count=$(nproc 2>/dev/null || echo 4)
    print_info "使用 $cpu_count 个并行任务"
    
    make -j$cpu_count VERBOSE=1
    
    cd ..
    
    print_success "静态编译完成！"
    
    # 验证静态链接
    if [ -f "build-static/ConvergenceAnalyzer" ]; then
        print_info "验证静态链接..."
        
        local file_info=$(file build-static/ConvergenceAnalyzer)
        print_info "可执行文件信息: $file_info"
        
        local file_size=$(du -h build-static/ConvergenceAnalyzer | cut -f1)
        print_info "文件大小: $file_size"
        
        # 检查动态链接库依赖
        if command -v ldd &> /dev/null; then
            print_info "检查动态库依赖:"
            if ldd build-static/ConvergenceAnalyzer 2>/dev/null; then
                print_warning "警告: 可执行文件仍有动态库依赖"
            else
                print_success "确认: 可执行文件已完全静态链接"
            fi
        fi
        
        # 测试可执行文件
        print_info "测试可执行文件..."
        if ./build-static/ConvergenceAnalyzer --help >/dev/null 2>&1; then
            print_success "可执行文件测试通过"
        else
            print_warning "可执行文件测试失败，但文件已生成"
        fi
        
        print_success "静态编译的可执行文件: build-static/ConvergenceAnalyzer"
        print_info "此文件可以在Alpine Linux x64系统上运行"
        
    else
        print_error "静态编译失败，未找到可执行文件"
        exit 1
    fi
}

# 显示使用帮助
show_help() {
    echo "静态编译脚本 - 专为Alpine Linux x64优化"
    echo ""
    echo "使用方法:"
    echo "  $0 [选项]"
    echo ""
    echo "选项:"
    echo "  (无参数)     使用musl libc静态编译 (推荐用于Alpine)"
    echo "  musl         使用musl libc静态编译"
    echo "  glibc        使用glibc静态编译"
    echo "  clean        清理静态构建文件"
    echo "  help         显示此帮助信息"
    echo ""
    echo "Alpine Linux依赖安装:"
    echo "  apk add cmake build-base musl-dev util-linux-dev linux-headers pkgconfig"
    echo ""
    echo "Ubuntu/Debian依赖安装:"
    echo "  apt-get install cmake build-essential libc6-dev-i386 uuid-dev pkg-config"
    echo ""
    echo "示例:"
    echo "  $0              # musl静态编译 (Alpine推荐)"
    echo "  $0 glibc        # glibc静态编译"
    echo "  $0 clean        # 清理构建文件"
}

# 主函数
main() {
    local action=${1:-musl}
    local system_type=$(detect_system)
    
    print_info "检测到系统类型: $system_type"
    
    case $action in
        "musl"|"")
            if [ "$system_type" = "alpine" ]; then
                check_alpine_dependencies
            else
                check_general_dependencies
            fi
            build_static "musl"
            ;;
        "glibc")
            check_general_dependencies
            build_static "glibc"
            ;;
        "clean")
            clean_build
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            print_error "未知选项: $action"
            show_help
            exit 1
            ;;
    esac
}

# 检查是否在正确的目录
if [ ! -f "CMakeLists.txt" ]; then
    print_error "请在包含CMakeLists.txt的目录中运行此脚本"
    exit 1
fi

# 运行主函数
main "$@"
