#include "netlink_monitor.h"
#include <iostream>
#include <cstring>
#include <cerrno>
#include <net/if.h>
#include <arpa/inet.h>
#include <unordered_map>
#include <unordered_set>
#include <fcntl.h>
#include <thread>
#include <chrono>

// NetlinkSocket 实现
NetlinkSocket::NetlinkSocket(int protocol, uint32_t groups) : fd_(-1) {
    fd_ = socket(AF_NETLINK, SOCK_RAW | SOCK_CLOEXEC, protocol);
    if (fd_ < 0) {
        throw std::runtime_error("Failed to create netlink socket: " + std::string(strerror(errno)));
    }
    
    struct sockaddr_nl addr;
    memset(&addr, 0, sizeof(addr));
    addr.nl_family = AF_NETLINK;
    addr.nl_groups = groups;
    addr.nl_pid = 0; // 让内核分配PID
    
    if (bind(fd_, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) < 0) {
        close(fd_);
        fd_ = -1;
        throw std::runtime_error("Failed to bind netlink socket: " + std::string(strerror(errno)));
    }
}

NetlinkSocket::~NetlinkSocket() {
    if (fd_ >= 0) {
        close(fd_);
    }
}

NetlinkSocket::NetlinkSocket(NetlinkSocket&& other) noexcept : fd_(other.fd_) {
    other.fd_ = -1;
}

NetlinkSocket& NetlinkSocket::operator=(NetlinkSocket&& other) noexcept {
    if (this != &other) {
        if (fd_ >= 0) {
            close(fd_);
        }
        fd_ = other.fd_;
        other.fd_ = -1;
    }
    return *this;
}

ssize_t NetlinkSocket::recv_message(void* buffer, size_t buffer_size) {
    return recv(fd_, buffer, buffer_size, 0);
}

ssize_t NetlinkSocket::send_message(const void* message, size_t message_size) {
    return send(fd_, message, message_size, 0);
}

// NetlinkMonitor 实现
NetlinkMonitor::NetlinkMonitor() : route_socket_fd_(-1), qdisc_socket_fd_(-1) {
}

NetlinkMonitor::~NetlinkMonitor() {
    stop_monitoring();
}

void NetlinkMonitor::set_route_callback(RouteEventCallback callback) {
    route_callback_ = std::move(callback);
}

void NetlinkMonitor::set_qdisc_callback(QdiscEventCallback callback) {
    qdisc_callback_ = std::move(callback);
}

bool NetlinkMonitor::start_monitoring() {
    if (running_.load()) {
        return true;
    }
    
    try {
        // 创建路由监控套接字
        route_socket_fd_ = create_netlink_socket(NETLINK_ROUTE, RTMGRP_IPV4_ROUTE | RTMGRP_IPV6_ROUTE);
        if (route_socket_fd_ < 0) {
            std::cerr << "Failed to create route netlink socket\n";
            return false;
        }
        
        // 创建QDisc监控套接字
        qdisc_socket_fd_ = create_netlink_socket(NETLINK_ROUTE, RTMGRP_TC);
        if (qdisc_socket_fd_ < 0) {
            std::cerr << "Failed to create qdisc netlink socket\n";
            close(route_socket_fd_);
            route_socket_fd_ = -1;
            return false;
        }
        
        running_.store(true);
        
        // 启动监控线程
        route_monitor_thread_ = std::thread(&NetlinkMonitor::route_monitor_loop, this);
        qdisc_monitor_thread_ = std::thread(&NetlinkMonitor::qdisc_monitor_loop, this);
        
        return true;
        
    } catch (const std::exception& e) {
        std::cerr << "Failed to start netlink monitoring: " << e.what() << "\n";
        return false;
    }
}

void NetlinkMonitor::stop_monitoring() {
    if (!running_.load()) {
        return;
    }
    
    running_.store(false);
    
    // 关闭套接字以中断阻塞的recv调用
    if (route_socket_fd_ >= 0) {
        close(route_socket_fd_);
        route_socket_fd_ = -1;
    }
    
    if (qdisc_socket_fd_ >= 0) {
        close(qdisc_socket_fd_);
        qdisc_socket_fd_ = -1;
    }
    
    // 等待线程结束
    if (route_monitor_thread_.joinable()) {
        route_monitor_thread_.join();
    }
    
    if (qdisc_monitor_thread_.joinable()) {
        qdisc_monitor_thread_.join();
    }
}

int NetlinkMonitor::create_netlink_socket(int protocol, uint32_t groups) {
    int fd = socket(AF_NETLINK, SOCK_RAW | SOCK_CLOEXEC, protocol);
    if (fd < 0) {
        return -1;
    }
    
    struct sockaddr_nl addr;
    memset(&addr, 0, sizeof(addr));
    addr.nl_family = AF_NETLINK;
    addr.nl_groups = groups;
    addr.nl_pid = 0;
    
    if (bind(fd, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) < 0) {
        close(fd);
        return -1;
    }
    
    return fd;
}

void NetlinkMonitor::route_monitor_loop() {
    char buffer[NETLINK_BUFFER_SIZE];

    // 设置套接字为非阻塞模式
    int flags = fcntl(route_socket_fd_, F_GETFL, 0);
    fcntl(route_socket_fd_, F_SETFL, flags | O_NONBLOCK);

    while (running_.load()) {
        ssize_t len = recv(route_socket_fd_, buffer, sizeof(buffer), 0);
        if (len < 0) {
            if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) {
                // 非阻塞模式下没有数据，短暂休眠后继续
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                continue;
            }
            if (running_.load()) {
                std::cerr << "Route netlink recv error: " << strerror(errno) << "\n";
            }
            break;
        }

        if (len == 0) {
            break;
        }

        // 处理netlink消息
        struct nlmsghdr* nlh = reinterpret_cast<struct nlmsghdr*>(buffer);
        while (NLMSG_OK(nlh, len)) {
            handle_route_message(nlh);
            nlh = NLMSG_NEXT(nlh, len);
        }
    }
}

void NetlinkMonitor::qdisc_monitor_loop() {
    char buffer[NETLINK_BUFFER_SIZE];

    // 设置套接字为非阻塞模式
    int flags = fcntl(qdisc_socket_fd_, F_GETFL, 0);
    fcntl(qdisc_socket_fd_, F_SETFL, flags | O_NONBLOCK);

    while (running_.load()) {
        ssize_t len = recv(qdisc_socket_fd_, buffer, sizeof(buffer), 0);
        if (len < 0) {
            if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) {
                // 非阻塞模式下没有数据，短暂休眠后继续
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                continue;
            }
            if (running_.load()) {
                std::cerr << "QDisc netlink recv error: " << strerror(errno) << "\n";
            }
            break;
        }

        if (len == 0) {
            break;
        }

        // 处理netlink消息
        struct nlmsghdr* nlh = reinterpret_cast<struct nlmsghdr*>(buffer);
        while (NLMSG_OK(nlh, len)) {
            handle_qdisc_message(nlh);
            nlh = NLMSG_NEXT(nlh, len);
        }
    }
}

NetlinkMessageType NetlinkMonitor::get_message_type(const struct nlmsghdr* nlh) {
    switch (nlh->nlmsg_type) {
        case RTM_NEWROUTE:
            return NetlinkMessageType::ROUTE_ADD;
        case RTM_DELROUTE:
            return NetlinkMessageType::ROUTE_DEL;
        case RTM_NEWQDISC:
            return NetlinkMessageType::QDISC_ADD;
        case RTM_DELQDISC:
            return NetlinkMessageType::QDISC_DEL;
        case RTM_GETQDISC:
            return NetlinkMessageType::QDISC_CHANGE;
        default:
            return NetlinkMessageType::UNKNOWN;
    }
}

std::string NetlinkMonitor::message_type_to_string(NetlinkMessageType type) {
    switch (type) {
        case NetlinkMessageType::ROUTE_ADD:
            return "路由添加";
        case NetlinkMessageType::ROUTE_DEL:
            return "路由删除";
        case NetlinkMessageType::QDISC_ADD:
            return "QDISC_ADD";
        case NetlinkMessageType::QDISC_DEL:
            return "QDISC_DEL";
        case NetlinkMessageType::QDISC_CHANGE:
            return "QDISC_CHANGE";
        default:
            return "UNKNOWN";
    }
}

void NetlinkMonitor::handle_route_message(const struct nlmsghdr* nlh) {
    NetlinkMessageType msg_type = get_message_type(nlh);
    
    if (msg_type == NetlinkMessageType::ROUTE_ADD || 
        msg_type == NetlinkMessageType::ROUTE_DEL) {
        
        if (route_callback_) {
            route_callback_(nlh, message_type_to_string(msg_type));
        }
    }
}

void NetlinkMonitor::handle_qdisc_message(const struct nlmsghdr* nlh) {
    NetlinkMessageType msg_type = get_message_type(nlh);
    
    if (msg_type == NetlinkMessageType::QDISC_ADD || 
        msg_type == NetlinkMessageType::QDISC_DEL ||
        msg_type == NetlinkMessageType::QDISC_CHANGE) {
        
        if (qdisc_callback_) {
            qdisc_callback_(nlh, message_type_to_string(msg_type));
        }
    }
}

void NetlinkMonitor::handle_netlink_error(const struct nlmsghdr* nlh) {
    struct nlmsgerr* err = static_cast<struct nlmsgerr*>(NLMSG_DATA(nlh));
    std::cerr << "Netlink error: " << strerror(-err->error) << "\n";
}

// NetlinkMessageParser 实现
std::unordered_map<std::string, std::string> NetlinkMessageParser::parse_route_message(
    const struct rtmsg* rtm, const struct rtattr* rta, int len) {

    std::unordered_map<std::string, std::string> result;

    // 基本路由信息
    result["family"] = std::to_string(rtm->rtm_family);
    result["table"] = std::to_string(rtm->rtm_table);
    result["protocol"] = get_route_protocol_name(rtm->rtm_protocol);
    result["scope"] = get_route_scope_name(rtm->rtm_scope);
    result["type"] = get_route_type_name(rtm->rtm_type);

    // 解析路由属性
    parse_route_attributes(rta, len, result);

    return result;
}

std::unordered_map<std::string, std::string> NetlinkMessageParser::parse_qdisc_message(
    const struct tcmsg* tcm, const struct rtattr* rta, int len) {

    std::unordered_map<std::string, std::string> result;

    // 基本QDisc信息
    result["ifindex"] = std::to_string(tcm->tcm_ifindex);
    result["interface"] = get_interface_name(tcm->tcm_ifindex);
    result["handle"] = std::to_string(tcm->tcm_handle);
    result["parent"] = std::to_string(tcm->tcm_parent);
    result["family"] = std::to_string(tcm->tcm_family);

    // 解析QDisc属性
    parse_qdisc_attributes(rta, len, result);

    return result;
}

void NetlinkMessageParser::parse_route_attributes(const struct rtattr* rta, int len,
                                                 std::unordered_map<std::string, std::string>& result) {
    while (rta_ok(rta, len)) {
        switch (rta->rta_type) {
            case RTA_DST: {
                int family = std::stoi(result["family"]);
                result["dst"] = ip_to_string(rta_data(rta), family);
                break;
            }
            case RTA_GATEWAY: {
                int family = std::stoi(result["family"]);
                result["gateway"] = ip_to_string(rta_data(rta), family);
                break;
            }
            case RTA_OIF: {
                int ifindex = *static_cast<int*>(rta_data(rta));
                result["ifindex"] = std::to_string(ifindex);
                result["interface"] = get_interface_name(ifindex);
                break;
            }
            case RTA_PREFSRC: {
                int family = std::stoi(result["family"]);
                result["prefsrc"] = ip_to_string(rta_data(rta), family);
                break;
            }
            case RTA_PRIORITY: {
                int priority = *static_cast<int*>(rta_data(rta));
                result["priority"] = std::to_string(priority);
                break;
            }
            default:
                break;
        }
        rta = rta_next(rta, len);
    }

    // 设置默认值
    if (result.find("dst") == result.end()) {
        result["dst"] = "default";
    }
    if (result.find("gateway") == result.end()) {
        result["gateway"] = "N/A";
    }
    if (result.find("interface") == result.end()) {
        result["interface"] = "N/A";
    }
}

void NetlinkMessageParser::parse_qdisc_attributes(const struct rtattr* rta, int len,
                                                 std::unordered_map<std::string, std::string>& result) {
    while (rta_ok(rta, len)) {
        switch (rta->rta_type) {
            case TCA_KIND: {
                std::string kind(static_cast<char*>(rta_data(rta)));
                result["kind"] = kind;
                result["is_netem"] = (kind == "netem") ? "true" : "false";
                break;
            }
            case TCA_OPTIONS:
                // 这里可以进一步解析QDisc选项
                break;
            default:
                break;
        }
        rta = rta_next(rta, len);
    }

    // 设置默认值
    if (result.find("kind") == result.end()) {
        result["kind"] = "unknown";
        result["is_netem"] = "false";
    }
}

std::string NetlinkMessageParser::ip_to_string(const void* addr, int family) {
    char str[INET6_ADDRSTRLEN];

    if (family == AF_INET) {
        if (inet_ntop(AF_INET, addr, str, INET_ADDRSTRLEN)) {
            return std::string(str);
        }
    } else if (family == AF_INET6) {
        if (inet_ntop(AF_INET6, addr, str, INET6_ADDRSTRLEN)) {
            return std::string(str);
        }
    }

    return "N/A";
}

std::string NetlinkMessageParser::get_interface_name(int ifindex) {
    char ifname[IF_NAMESIZE];
    if (if_indextoname(ifindex, ifname)) {
        return std::string(ifname);
    }
    return "if" + std::to_string(ifindex);
}

std::string NetlinkMessageParser::get_route_table_name(int table) {
    switch (table) {
        case RT_TABLE_UNSPEC: return "unspec";
        case RT_TABLE_COMPAT: return "compat";
        case RT_TABLE_DEFAULT: return "default";
        case RT_TABLE_MAIN: return "main";
        case RT_TABLE_LOCAL: return "local";
        default: return std::to_string(table);
    }
}

std::string NetlinkMessageParser::get_route_protocol_name(int protocol) {
    switch (protocol) {
        case RTPROT_UNSPEC: return "unspec";
        case RTPROT_REDIRECT: return "redirect";
        case RTPROT_KERNEL: return "kernel";
        case RTPROT_BOOT: return "boot";
        case RTPROT_STATIC: return "static";
        default: return std::to_string(protocol);
    }
}

std::string NetlinkMessageParser::get_route_scope_name(int scope) {
    switch (scope) {
        case RT_SCOPE_UNIVERSE: return "universe";
        case RT_SCOPE_SITE: return "site";
        case RT_SCOPE_LINK: return "link";
        case RT_SCOPE_HOST: return "host";
        case RT_SCOPE_NOWHERE: return "nowhere";
        default: return std::to_string(scope);
    }
}

std::string NetlinkMessageParser::get_route_type_name(int type) {
    switch (type) {
        case RTN_UNSPEC: return "unspec";
        case RTN_UNICAST: return "unicast";
        case RTN_LOCAL: return "local";
        case RTN_BROADCAST: return "broadcast";
        case RTN_ANYCAST: return "anycast";
        case RTN_MULTICAST: return "multicast";
        case RTN_BLACKHOLE: return "blackhole";
        case RTN_UNREACHABLE: return "unreachable";
        case RTN_PROHIBIT: return "prohibit";
        default: return std::to_string(type);
    }
}

// RTA遍历辅助函数
const struct rtattr* NetlinkMessageParser::rta_next(const struct rtattr* rta, int& len) {
    int rta_len = RTA_ALIGN(rta->rta_len);
    len -= rta_len;
    return reinterpret_cast<const struct rtattr*>(
        reinterpret_cast<const char*>(rta) + rta_len);
}

bool NetlinkMessageParser::rta_ok(const struct rtattr* rta, int len) {
    return len >= static_cast<int>(sizeof(*rta)) &&
           rta->rta_len >= sizeof(*rta) &&
           rta->rta_len <= len;
}

void* NetlinkMessageParser::rta_data(const struct rtattr* rta) {
    return reinterpret_cast<void*>(
        reinterpret_cast<char*>(const_cast<struct rtattr*>(rta)) + RTA_LENGTH(0));
}

int NetlinkMessageParser::rta_len(const struct rtattr* rta) {
    return rta->rta_len - RTA_LENGTH(0);
}
