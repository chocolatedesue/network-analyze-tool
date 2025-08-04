#include <iomanip>
#include <iostream>
#include <memory>
#include <signal.h>
#include <getopt.h>
#include <unistd.h>
#include <pwd.h>
#include <chrono>
#include <thread>
#include <atomic>
#include <csignal>

#include "convergence_monitor.h"
#include "logger.h"

// Global shutdown flag
std::atomic<bool> shutdown_requested{false};
std::unique_ptr<ConvergenceMonitor> global_monitor;

void signal_handler(int signal) {
    std::cout << "\n🛑 接收到信号 " << signal << "，正在优雅关闭...\n";
    shutdown_requested.store(true);

    // 立即停止监控器以中断阻塞的系统调用
    if (global_monitor) {
        global_monitor->stop_monitoring();
    }
}

void print_usage(const char* program_name) {
    std::cout << "异步路由收敛时间监控工具 - C++多线程版本\n\n";
    std::cout << "使用说明:\n";
    std::cout << "  触发策略:\n";
    std::cout << "    1. 启动监控工具: " << program_name << " --threshold 3000 --router-name router1\n";
    std::cout << "    2. 触发事件策略:\n";
    std::cout << "       - 在IDLE状态: 任何事件(Netem或路由变更)都会立即触发新的收敛测量会话\n";
    std::cout << "       - 在监控状态: 新事件会被当作路由事件添加到当前会话中\n";
    std::cout << "       - 支持的触发事件:\n";
    std::cout << "         * Netem命令: tc qdisc add dev eth0 root netem delay 10ms\n";
    std::cout << "         * 路由添加: ip route add 192.168.1.0/24 via 10.0.0.1\n";
    std::cout << "         * 路由删除: ip route del 192.168.1.0/24\n";
    std::cout << "    3. 观察路由收敛过程和时间测量\n\n";
    std::cout << "  C++多线程特性:\n";
    std::cout << "    - 多线程并发处理netlink事件\n";
    std::cout << "    - 原子操作和无锁数据结构\n";
    std::cout << "    - 高性能事件处理和日志记录\n";
    std::cout << "    - 线程安全的状态管理\n\n";
    std::cout << "  使用Ctrl+C停止监控并查看统计报告\n";
    std::cout << "  结构化日志将以JSON格式保存到指定路径或默认路径\n\n";
    std::cout << "示例:\n";
    std::cout << "  " << program_name << " --threshold 3000 --router-name spine1\n";
    std::cout << "  " << program_name << " --threshold 5000 --router-name leaf2 --log-path /tmp/my_convergence.json\n";
    std::cout << "  " << program_name << " --log-path ./logs/convergence_cpp.json\n\n";
    std::cout << "选项:\n";
    std::cout << "  -t, --threshold MILLISECONDS  收敛判断阈值(毫秒，默认3000ms)\n";
    std::cout << "  -r, --router-name NAME        路由器名称标识，用于日志记录(默认自动生成)\n";
    std::cout << "  -l, --log-path PATH           日志文件路径(默认: /var/log/frr/async_route_convergence_cpp.json)\n";
    std::cout << "  -h, --help                    显示此帮助信息\n";
}

std::string get_current_user() {
    struct passwd* pw = getpwuid(getuid());
    return pw ? std::string(pw->pw_name) : "unknown";
}

std::string generate_router_name() {
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    return "router_" + get_current_user() + "_" + std::to_string(time_t);
}

int main(int argc, char* argv[]) {
    // 默认参数
    int64_t threshold = 3000;
    std::string router_name;
    std::string log_path;

    // 解析命令行参数
    static struct option long_options[] = {
        {"threshold", required_argument, 0, 't'},
        {"router-name", required_argument, 0, 'r'},
        {"log-path", required_argument, 0, 'l'},
        {"help", no_argument, 0, 'h'},
        {0, 0, 0, 0}
    };

    int option_index = 0;
    int c;
    while ((c = getopt_long(argc, argv, "t:r:l:h", long_options, &option_index)) != -1) {
        switch (c) {
            case 't':
                threshold = std::stoll(optarg);
                break;
            case 'r':
                router_name = optarg;
                break;
            case 'l':
                log_path = optarg;
                break;
            case 'h':
                print_usage(argv[0]);
                return 0;
            case '?':
                print_usage(argv[0]);
                return 1;
            default:
                break;
        }
    }

    // 参数验证
    if (threshold <= 0) {
        std::cerr << "❌ 错误: 收敛阈值必须大于0\n";
        return 1;
    }

    // 生成默认路由器名称
    if (router_name.empty()) {
        router_name = generate_router_name();
    }

    // 设置信号处理
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    // 打印启动信息
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    std::cout << "异步路由收敛监控工具启动 (C++多线程版) - " 
              << std::put_time(std::localtime(&time_t), "%Y-%m-%d %H:%M:%S") << "\n";
    std::cout << "参数: 收敛阈值=" << threshold << "ms\n";
    std::cout << "路由器名称: " << router_name << "\n";
    std::cout << "触发策略: 仅在IDLE状态时触发新会话，监控中作为路由事件\n";
    std::cout << "性能优化: C++多线程 + 原子操作 + 无锁数据结构\n";
    
    std::string actual_log_path = log_path.empty() ? "默认路径" : log_path;
    std::cout << "日志路径: " << actual_log_path << "\n";
    std::cout << "使用 Ctrl+C 停止监听\n\n";

    try {
        // 创建监控器
        global_monitor = std::make_unique<ConvergenceMonitor>(threshold, router_name, log_path);

        // 开始监控
        global_monitor->start_monitoring();

        // 等待关闭信号
        while (!shutdown_requested.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }

        // 停止监控
        global_monitor->stop_monitoring();
        global_monitor.reset();

        std::cout << "\n程序正常退出\n";
        
    } catch (const std::exception& e) {
        std::cerr << "❌ 程序运行出错: " << e.what() << "\n";
        return 1;
    }

    return 0;
}
