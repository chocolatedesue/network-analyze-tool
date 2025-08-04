#pragma once

#include <functional>
#include <thread>
#include <atomic>
#include <memory>
#include <vector>
#include <unordered_map>
#include <string>
#include <sys/epoll.h>

// Linux netlink headers
#include <linux/netlink.h>
#include <linux/rtnetlink.h>
#include <linux/pkt_sched.h>
#include <sys/socket.h>
#include <unistd.h>

// 前向声明
class ConvergenceMonitor;

// Netlink消息类型
enum class NetlinkMessageType {
    ROUTE_ADD,
    ROUTE_DEL,
    QDISC_ADD,
    QDISC_DEL,
    QDISC_GET,
    QDISC_CHANGE,
    UNKNOWN
};

// Netlink事件回调函数类型
using RouteEventCallback = std::function<void(const void*, const std::string&)>;
using QdiscEventCallback = std::function<void(const void*, const std::string&)>;

// 统一的netlink事件回调函数类型
using NetlinkEventCallback = std::function<void(const void*, const std::string&, NetlinkMessageType)>;

// Netlink监控器类
class NetlinkMonitor {
private:
    // 统一的套接字文件描述符
    int netlink_socket_fd_;
    int epoll_fd_;

    // 用于优雅关闭的管道
    int shutdown_pipe_[2];

    // 线程管理
    std::atomic<bool> running_{false};
    std::thread monitor_thread_;

    // 事件回调
    RouteEventCallback route_callback_;
    QdiscEventCallback qdisc_callback_;
    NetlinkEventCallback unified_callback_;

    // 缓冲区大小
    static constexpr size_t NETLINK_BUFFER_SIZE = 8192;
    static constexpr int MAX_EPOLL_EVENTS = 10;

    // 内部方法
    int create_unified_netlink_socket();
    void unified_monitor_loop();
    
    void process_netlink_message(const struct nlmsghdr* nlh);
    
    NetlinkMessageType get_message_type(const struct nlmsghdr* nlh);
    std::string message_type_to_string(NetlinkMessageType type);
    
    // 路由消息处理
    void handle_route_message(const struct nlmsghdr* nlh);
    
    // QDisc消息处理  
    void handle_qdisc_message(const struct nlmsghdr* nlh);
    
    // 错误处理
    void handle_netlink_error(const struct nlmsghdr* nlh);

public:
    NetlinkMonitor();
    ~NetlinkMonitor();
    
    // 禁用拷贝和移动
    NetlinkMonitor(const NetlinkMonitor&) = delete;
    NetlinkMonitor& operator=(const NetlinkMonitor&) = delete;
    NetlinkMonitor(NetlinkMonitor&&) = delete;
    NetlinkMonitor& operator=(NetlinkMonitor&&) = delete;
    
    // 设置事件回调
    void set_route_callback(RouteEventCallback callback);
    void set_qdisc_callback(QdiscEventCallback callback);
    void set_unified_callback(NetlinkEventCallback callback);
    
    // 启动和停止监控
    bool start_monitoring();
    void stop_monitoring();
    void request_shutdown(); // 请求优雅关闭

    // 检查是否正在运行
    bool is_running() const { return running_.load(); }
};

// Netlink消息解析辅助类
class NetlinkMessageParser {
public:
    // 解析路由消息
    static std::unordered_map<std::string, std::string> parse_route_message(const struct rtmsg* rtm, 
                                                                           const struct rtattr* rta, 
                                                                           int len);
    
    // 解析QDisc消息
    static std::unordered_map<std::string, std::string> parse_qdisc_message(const struct tcmsg* tcm, 
                                                                           const struct rtattr* rta, 
                                                                           int len);
    
    // 解析路由属性
    static void parse_route_attributes(const struct rtattr* rta, int len, 
                                     std::unordered_map<std::string, std::string>& result);
    
    // 解析QDisc属性
    static void parse_qdisc_attributes(const struct rtattr* rta, int len, 
                                     std::unordered_map<std::string, std::string>& result);
    
    // 辅助函数
    static std::string ip_to_string(const void* addr, int family);
    static std::string get_interface_name(int ifindex);
    static std::string get_route_table_name(int table);
    static std::string get_route_protocol_name(int protocol);
    static std::string get_route_scope_name(int scope);
    static std::string get_route_type_name(int type);
    
private:
    // RTA遍历宏的C++版本
    static const struct rtattr* rta_next(const struct rtattr* rta, int& len);
    static bool rta_ok(const struct rtattr* rta, int len);
    static void* rta_data(const struct rtattr* rta);
    static int rta_len(const struct rtattr* rta);
};

// Netlink套接字RAII包装器
class NetlinkSocket {
private:
    int fd_;
    
public:
    NetlinkSocket(int protocol, uint32_t groups);
    ~NetlinkSocket();
    
    // 禁用拷贝，允许移动
    NetlinkSocket(const NetlinkSocket&) = delete;
    NetlinkSocket& operator=(const NetlinkSocket&) = delete;
    NetlinkSocket(NetlinkSocket&& other) noexcept;
    NetlinkSocket& operator=(NetlinkSocket&& other) noexcept;
    
    int get_fd() const { return fd_; }
    bool is_valid() const { return fd_ >= 0; }
    
    // 接收消息
    ssize_t recv_message(void* buffer, size_t buffer_size);
    
    // 发送消息
    ssize_t send_message(const void* message, size_t message_size);
};
