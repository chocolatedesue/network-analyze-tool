#include "convergence_monitor.h"
#include <iostream>
#include <iomanip>
#include <sstream>
#include <algorithm>
#include <cmath>
#include <pwd.h>
#include <unistd.h>
#include <uuid/uuid.h>
#include <numeric>
#include <linux/netlink.h>
#include <linux/rtnetlink.h>
#include <linux/pkt_sched.h>

// C++17兼容性检查
#if __cplusplus >= 201703L
    #include <shared_mutex>
    #define HAS_SHARED_MUTEX 1
#else
    #define HAS_SHARED_MUTEX 0
#endif

// ConvergenceSession 实现
ConvergenceSession::ConvergenceSession(int id, int64_t netem_time, 
                                     const std::unordered_map<std::string, std::string>& netem_info_map)
    : session_id(id), netem_event_time(netem_time), netem_info(netem_info_map) {
}

void ConvergenceSession::add_route_event(int64_t timestamp, const std::string& event_type,
                                        const std::unordered_map<std::string, std::string>& route_info) {
    std::lock_guard<std::mutex> lock(mutex_);

    int64_t offset = timestamp - netem_event_time;
    route_events.emplace_back(timestamp, event_type, route_info, offset);
    last_route_event_time = timestamp;
}

bool ConvergenceSession::check_convergence(int64_t quiet_period_ms) {
    std::lock_guard<std::mutex> lock(mutex_);

    if (is_converged.load()) {
        return true;
    }

    auto current_time = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();

    int64_t quiet_time;
    if (!last_route_event_time.has_value()) {
        quiet_time = current_time - netem_event_time;
    } else {
        quiet_time = current_time - last_route_event_time.value();
    }

    convergence_check_count_.fetch_add(1);

    if (quiet_time >= quiet_period_ms) {
        is_converged.store(true);
        convergence_detected_time = current_time;

        if (last_route_event_time.has_value()) {
            convergence_time = last_route_event_time.value() - netem_event_time;
        } else {
            convergence_time = 0;
        }

        return true;
    }

    return false;
}

int ConvergenceSession::get_route_event_count() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return route_events.size();
}

int64_t ConvergenceSession::get_session_duration() const {
    std::lock_guard<std::mutex> lock(mutex_);

    if (convergence_detected_time.has_value()) {
        return convergence_detected_time.value() - netem_event_time;
    }

    auto current_time = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    return current_time - netem_event_time;
}

// ConvergenceMonitor 实现
ConvergenceMonitor::ConvergenceMonitor(int64_t convergence_threshold_ms,
                                     const std::string& router_name,
                                     const std::string& log_path)
    : router_name_(router_name),
      convergence_threshold_ms_(convergence_threshold_ms),
      monitoring_start_time_(get_current_timestamp_ms()) {
    
    // 生成监控器ID
    uuid_t uuid;
    uuid_generate(uuid);
    char uuid_str[37];
    uuid_unparse(uuid, uuid_str);
    monitor_id_ = std::string(uuid_str);
    
    // 创建日志记录器
    logger_ = std::make_unique<Logger>(log_path);
    log_file_path_ = logger_->get_log_file_path();
    
    // 创建netlink监控器
    netlink_monitor_ = std::make_unique<NetlinkMonitor>();
    
    // 设置回调函数
    netlink_monitor_->set_route_callback(
        [this](const void* data, const std::string& type) {
            this->on_route_event(data, type);
        });
    
    netlink_monitor_->set_qdisc_callback(
        [this](const void* data, const std::string& type) {
            this->on_qdisc_event(data, type);
        });
}

ConvergenceMonitor::~ConvergenceMonitor() {
    stop_monitoring();
}

void ConvergenceMonitor::start_monitoring() {
    if (running_.load()) {
        return;
    }
    
    running_.store(true);
    
    // 启动日志记录器
    logger_->start();
    
    // 记录监控开始日志
    std::string user = []() {
        struct passwd* pw = getpwuid(getuid());
        return pw ? std::string(pw->pw_name) : "unknown";
    }();
    
    auto start_log = Logger::create_monitoring_start_log(
        router_name_, user, convergence_threshold_ms_, 
        log_file_path_, monitor_id_);
    logger_->log_async(start_log);
    
    // 启动netlink监控
    if (!netlink_monitor_->start_monitoring()) {
        throw std::runtime_error("Failed to start netlink monitoring");
    }
    
    // 启动收敛检查线程
    convergence_checker_thread_ = std::thread(&ConvergenceMonitor::convergence_checker_loop, this);
    
    std::cout << "🎯 监控开始 - 路由器: " << router_name_ << "\n";
    std::cout << "   收敛阈值: " << convergence_threshold_ms_ << "ms\n";
    std::cout << "   等待触发事件...\n";
}

void ConvergenceMonitor::stop_monitoring() {
    if (!running_.load()) {
        return;
    }
    
    running_.store(false);
    
    // 停止netlink监控
    if (netlink_monitor_) {
        netlink_monitor_->stop_monitoring();
    }
    
    // 停止收敛检查线程
    if (convergence_checker_thread_.joinable()) {
        convergence_cv_.notify_all();
        convergence_checker_thread_.join();
    }
    
    // 打印统计信息
    print_statistics();
    
    // 停止日志记录器
    if (logger_) {
        logger_->stop();
    }
}

void ConvergenceMonitor::on_route_event(const void* route_data, const std::string& event_type) {
    int64_t timestamp = get_current_timestamp_ms();
    auto route_info = parse_route_info(route_data);
    handle_route_event(timestamp, event_type, route_info);
}

void ConvergenceMonitor::on_qdisc_event(const void* qdisc_data, const std::string& event_type) {
    auto qdisc_info = parse_qdisc_info(qdisc_data);
    handle_qdisc_event(qdisc_info, event_type);
}

void ConvergenceMonitor::cleanup_old_events() {
    int64_t current_time = get_current_timestamp_ms();
    int64_t cutoff_time = current_time - 300000; // 5分钟前
    
    std::lock_guard<std::mutex> lock(qdisc_events_mutex_);
    
    // 清理过期的qdisc事件
    while (!recent_qdisc_events_.empty() && 
           recent_qdisc_events_.front().timestamp < cutoff_time) {
        recent_qdisc_events_.pop();
    }
}

std::string ConvergenceMonitor::format_timestamp(int64_t timestamp_ms) const {
    auto time_point = std::chrono::system_clock::from_time_t(timestamp_ms / 1000);
    auto time_t = std::chrono::system_clock::to_time_t(time_point);
    auto ms = timestamp_ms % 1000;
    
    std::stringstream ss;
    ss << std::put_time(std::localtime(&time_t), "%Y-%m-%d %H:%M:%S");
    ss << "." << std::setfill('0') << std::setw(3) << ms;
    return ss.str();
}

std::string ConvergenceMonitor::get_interface_name(int ifindex) const {
    // 这里应该实现获取接口名称的逻辑
    // 可以通过读取 /sys/class/net/ 或使用 if_indextoname
    char ifname[IF_NAMESIZE];
    if (if_indextoname(ifindex, ifname)) {
        return std::string(ifname);
    }
    return "if" + std::to_string(ifindex);
}

void ConvergenceMonitor::convergence_checker_loop() {
    while (running_.load()) {
        std::unique_lock<std::mutex> lock(convergence_mutex_);

        // 等待1秒或直到被通知停止
        if (convergence_cv_.wait_for(lock, std::chrono::seconds(1),
                                   [this] { return !running_.load(); })) {
            break;
        }

        // 检查当前会话是否需要收敛检查
        ConvergenceSession* session = nullptr;
        {
            std::lock_guard<std::mutex> session_lock(session_mutex_);
            if (state_.load() == MonitorState::MONITORING &&
                current_session_ &&
                !current_session_->is_converged.load()) {
                session = current_session_.get();
            }
        }

        if (session) {
            // 检查收敛（不需要持有session_mutex_）
            if (session->check_convergence(convergence_threshold_ms_)) {
                // 获取写锁来完成会话
                std::lock_guard<std::mutex> write_lock(session_mutex_);
                if (state_.load() == MonitorState::MONITORING &&
                    current_session_.get() == session &&
                    current_session_->is_converged.load()) {

                    std::cout << "✅ 会话 #" << current_session_->session_id << " 收敛完成\n";
                    finish_current_session();
                }
            }
        }
    }
}

std::unordered_map<std::string, std::string> ConvergenceMonitor::parse_route_info(const void* route_data) const {
    const struct nlmsghdr* nlh = static_cast<const struct nlmsghdr*>(route_data);
    const struct rtmsg* rtm = static_cast<const struct rtmsg*>(NLMSG_DATA(nlh));

    // 计算属性数据的起始位置和长度
    int attrlen = nlh->nlmsg_len - NLMSG_LENGTH(sizeof(*rtm));
    const struct rtattr* rta = reinterpret_cast<const struct rtattr*>(
        reinterpret_cast<const char*>(rtm) + NLMSG_ALIGN(sizeof(*rtm)));

    // 使用NetlinkMessageParser解析消息
    return NetlinkMessageParser::parse_route_message(rtm, rta, attrlen);
}

std::unordered_map<std::string, std::string> ConvergenceMonitor::parse_qdisc_info(const void* qdisc_data) const {
    const struct nlmsghdr* nlh = static_cast<const struct nlmsghdr*>(qdisc_data);
    const struct tcmsg* tcm = static_cast<const struct tcmsg*>(NLMSG_DATA(nlh));

    // 计算属性数据的起始位置和长度
    int attrlen = nlh->nlmsg_len - NLMSG_LENGTH(sizeof(*tcm));
    const struct rtattr* rta = reinterpret_cast<const struct rtattr*>(
        reinterpret_cast<const char*>(tcm) + NLMSG_ALIGN(sizeof(*tcm)));

    // 使用NetlinkMessageParser解析消息
    return NetlinkMessageParser::parse_qdisc_message(tcm, rta, attrlen);
}

bool ConvergenceMonitor::is_netem_related_event(const std::unordered_map<std::string, std::string>& qdisc_info,
                                               const std::string& event_type) const {
    // 检查是否为netem类型
    auto it = qdisc_info.find("is_netem");
    if (it != qdisc_info.end() && it->second == "true") {
        return true;
    }

    // 对于删除事件，检查最近的事件
    if (event_type == "QDISC_DEL") {
        auto iface_it = qdisc_info.find("interface");
        if (iface_it != qdisc_info.end()) {
            std::string interface_name = iface_it->second;

            std::lock_guard<std::mutex> lock(qdisc_events_mutex_);

            // 创建临时队列来遍历
            std::queue<QdiscEvent> temp_queue = recent_qdisc_events_;
            while (!temp_queue.empty()) {
                const auto& event = temp_queue.front();
                auto event_iface_it = event.info.find("interface");
                if (event_iface_it != event.info.end() &&
                    event_iface_it->second == interface_name) {
                    auto event_netem_it = event.info.find("is_netem");
                    if (event_netem_it != event.info.end() &&
                        event_netem_it->second == "true") {
                        return true;
                    }
                }
                temp_queue.pop();
            }
        }
    }

    return false;
}

void ConvergenceMonitor::handle_trigger_event(int64_t timestamp, const std::string& event_type,
                                             const std::unordered_map<std::string, std::string>& trigger_info,
                                             const std::string& trigger_source) {
    std::lock_guard<std::mutex> lock(session_mutex_);

    // 如果当前有会话在进行且未收敛，不强制终止
    if (current_session_ && !current_session_->is_converged.load()) {
        std::cout << "⚠️  忽略新" << event_type << "事件，会话 #"
                  << current_session_->session_id << " 仍在进行中\n";
        return;
    }

    // 开始新会话
    int session_id = session_counter_.fetch_add(1) + 1;
    current_session_ = std::make_unique<ConvergenceSession>(session_id, timestamp, trigger_info);
    state_.store(MonitorState::MONITORING);

    // 更新统计
    if (trigger_source == "netem") {
        total_netem_triggers_.fetch_add(1);
    } else {
        total_route_triggers_.fetch_add(1);
    }

    // 记录会话开始日志
    std::string user = []() {
        struct passwd* pw = getpwuid(getuid());
        return pw ? std::string(pw->pw_name) : "unknown";
    }();

    auto session_start_log = Logger::create_session_start_log(
        router_name_, session_id, trigger_source, event_type, trigger_info, user);
    logger_->log_async(session_start_log);

    // 控制台输出
    if (trigger_source == "netem") {
        std::cout << "🚀 开始会话 #" << session_id << " (Netem触发: " << event_type << ")\n";
        auto iface_it = trigger_info.find("interface");
        if (iface_it != trigger_info.end()) {
            std::cout << "   接口: " << iface_it->second << "\n";
        }
    } else {
        std::cout << "🚀 开始会话 #" << session_id << " (路由触发: " << event_type << ")\n";
        auto dst_it = trigger_info.find("dst");
        if (dst_it != trigger_info.end()) {
            std::cout << "   目标: " << dst_it->second << "\n";
        }
    }
}

void ConvergenceMonitor::handle_qdisc_event(const std::unordered_map<std::string, std::string>& qdisc_info,
                                           const std::string& event_type) {
    int64_t current_time = get_current_timestamp_ms();

    // 缓存qdisc事件
    {
        std::lock_guard<std::mutex> lock(qdisc_events_mutex_);
        recent_qdisc_events_.emplace(current_time, event_type, qdisc_info);
        if (recent_qdisc_events_.size() > MAX_QDISC_EVENTS) {
            recent_qdisc_events_.pop();
        }
    }

    // 检查是否为netem相关事件
    if (is_netem_related_event(qdisc_info, event_type)) {
        // 记录netem事件日志
        std::string user = []() {
            struct passwd* pw = getpwuid(getuid());
            return pw ? std::string(pw->pw_name) : "unknown";
        }();

        auto netem_log = Logger::create_event_log("netem_detected", router_name_, user);
        netem_log["netem_event_type"] = event_type;
        netem_log["qdisc_info"] = ""; // 这里需要序列化qdisc_info
        logger_->log_async(netem_log);

        // 检查当前状态
        MonitorState current_state;
        bool is_monitoring;
        ConvergenceSession* session = nullptr;
        {
            std::lock_guard<std::mutex> lock(session_mutex_);
            current_state = state_.load();
            is_monitoring = (current_state == MonitorState::MONITORING &&
                           current_session_ &&
                           !current_session_->is_converged.load());
            if (is_monitoring) {
                session = current_session_.get();
            }
        }

        if (is_monitoring) {
            // 当前有活跃会话，将netem事件作为普通路由事件处理
            session->add_route_event(current_time, "Netem事件(" + event_type + ")", qdisc_info);

            int64_t total_events = total_route_events_.fetch_add(1) + 1;
            int64_t offset = current_time - session->netem_event_time;
            int session_event_count = session->get_route_event_count();

            // 记录路由事件日志
            auto route_log = Logger::create_route_event_log(
                router_name_, session->session_id, "Netem事件(" + event_type + ")",
                total_events, session_event_count, offset, qdisc_info, user);
            logger_->log_async(route_log);
        } else {
            // 没有活跃会话，作为触发事件处理
            handle_trigger_event(current_time, event_type, qdisc_info, "netem");
        }
    }
}

void ConvergenceMonitor::handle_route_event(int64_t timestamp, const std::string& event_type,
                                           const std::unordered_map<std::string, std::string>& route_info) {
    // 检查是否应该作为触发事件
    MonitorState current_state;
    {
        std::lock_guard<std::mutex> lock(session_mutex_);
        current_state = state_.load();
    }

    if ((event_type == "路由添加" || event_type == "路由删除") &&
        current_state == MonitorState::IDLE) {
        // 作为触发事件处理
        std::string trigger_type = (event_type == "路由添加") ? "route_add" : "route_del";

        std::unordered_map<std::string, std::string> trigger_info;
        trigger_info["type"] = trigger_type;

        auto dst_it = route_info.find("dst");
        trigger_info["dst"] = (dst_it != route_info.end()) ? dst_it->second : "N/A";

        auto iface_it = route_info.find("interface");
        trigger_info["interface"] = (iface_it != route_info.end()) ? iface_it->second : "N/A";

        auto gw_it = route_info.find("gateway");
        trigger_info["gateway"] = (gw_it != route_info.end()) ? gw_it->second : "N/A";

        handle_trigger_event(timestamp, event_type, trigger_info, "route");
        return;
    }

    // 普通路由事件处理
    ConvergenceSession* session = nullptr;
    {
        std::lock_guard<std::mutex> lock(session_mutex_);
        if (current_state != MonitorState::MONITORING || !current_session_) {
            return; // 不在监控状态，忽略路由事件
        }
        session = current_session_.get();
    }

    // 添加路由事件到会话中
    session->add_route_event(timestamp, event_type, route_info);

    // 更新统计信息
    int64_t total_events = total_route_events_.fetch_add(1) + 1;
    int64_t offset = timestamp - session->netem_event_time;
    int session_event_count = session->get_route_event_count();

    // 记录路由事件日志
    std::string user = []() {
        struct passwd* pw = getpwuid(getuid());
        return pw ? std::string(pw->pw_name) : "unknown";
    }();

    auto route_log = Logger::create_route_event_log(
        router_name_, session->session_id, event_type,
        total_events, session_event_count, offset, route_info, user);
    logger_->log_async(route_log);
}

void ConvergenceMonitor::finish_current_session() {
    if (!current_session_) {
        return;
    }

    auto session = std::move(current_session_);
    completed_sessions_.push_back(std::move(session));

    // 记录会话完成日志
    std::string user = []() {
        struct passwd* pw = getpwuid(getuid());
        return pw ? std::string(pw->pw_name) : "unknown";
    }();

    auto completed_session = completed_sessions_.back().get();
    auto session_log = Logger::create_session_completed_log(
        router_name_, completed_session->session_id,
        completed_session->convergence_time,
        completed_session->get_route_event_count(),
        completed_session->get_session_duration(),
        convergence_threshold_ms_,
        completed_session->netem_info,
        user);
    logger_->log_async(session_log);

    // 控制台输出
    if (completed_session->convergence_time.has_value()) {
        std::cout << "   收敛时间: " << completed_session->convergence_time.value()
                  << "ms, 路由事件: " << completed_session->get_route_event_count() << "\n";
    } else {
        std::cout << "   路由事件: " << completed_session->get_route_event_count() << "\n";
    }

    // 重置状态
    current_session_.reset();
    state_.store(MonitorState::IDLE);
}

void ConvergenceMonitor::force_finish_session(const std::string& reason) {
    std::lock_guard<std::mutex> lock(session_mutex_);
    if (current_session_) {
        current_session_->check_convergence(0); // 强制收敛
        std::cout << "📋 强制结束会话 #" << current_session_->session_id
                  << ": " << reason << "\n";
        finish_current_session();
    }
}

void ConvergenceMonitor::print_statistics() {
    // 强制结束当前会话
    {
        std::lock_guard<std::mutex> lock(session_mutex_);
        if (current_session_ && !current_session_->is_converged.load()) {
            force_finish_session("监听结束");
        }
    }

    int64_t current_time = get_current_timestamp_ms();
    int64_t total_time = current_time - monitoring_start_time_;

    // 读取统计计数器
    int64_t total_route_events = total_route_events_.load();
    int64_t total_netem_triggers = total_netem_triggers_.load();
    int64_t total_route_triggers = total_route_triggers_.load();

    // 计算统计数据
    std::vector<int64_t> convergence_times;
    std::vector<int> route_counts;
    std::vector<int64_t> session_durations;
    std::unordered_set<std::string> interface_set;

    for (const auto& session : completed_sessions_) {
        if (session->convergence_time.has_value()) {
            convergence_times.push_back(session->convergence_time.value());
        }
        route_counts.push_back(session->get_route_event_count());
        session_durations.push_back(session->get_session_duration());

        // 收集接口信息
        auto iface_it = session->netem_info.find("interface");
        if (iface_it != session->netem_info.end()) {
            interface_set.insert(iface_it->second);
        }

        for (const auto& route_event : session->route_events) {
            auto route_iface_it = route_event.info.find("interface");
            if (route_iface_it != route_event.info.end()) {
                interface_set.insert(route_iface_it->second);
            }
        }
    }

    // 收敛时间分布
    int fast_convergence = 0, medium_convergence = 0, slow_convergence = 0;
    for (int64_t t : convergence_times) {
        if (t < 100) fast_convergence++;
        else if (t < 1000) medium_convergence++;
        else slow_convergence++;
    }

    // 记录最终统计日志
    std::string user = []() {
        struct passwd* pw = getpwuid(getuid());
        return pw ? std::string(pw->pw_name) : "unknown";
    }();

    int64_t total_triggers = total_netem_triggers + total_route_triggers;
    auto final_log = Logger::create_monitoring_completed_log(
        router_name_, log_file_path_, user, total_time, convergence_threshold_ms_,
        total_triggers, total_netem_triggers, total_route_triggers,
        total_route_events, completed_sessions_.size(), monitor_id_);

    // 添加详细统计信息
    if (!convergence_times.empty()) {
        std::sort(convergence_times.begin(), convergence_times.end());
        final_log["fastest_convergence_ms"] = convergence_times.front();
        final_log["slowest_convergence_ms"] = convergence_times.back();

        double sum = std::accumulate(convergence_times.begin(), convergence_times.end(), 0.0);
        final_log["avg_convergence_time_ms"] = sum / convergence_times.size();
    }

    logger_->log_sync(final_log);

    // 控制台输出统计摘要
    std::cout << "\n📊 监控统计摘要\n";
    std::cout << "   路由器: " << router_name_ << "\n";
    std::cout << "   监听时长: " << (total_time / 1000.0) << "秒\n";
    std::cout << "   触发事件: " << total_triggers
              << ", 路由事件: " << total_route_events
              << ", 完成会话: " << completed_sessions_.size() << "\n";

    if (!convergence_times.empty()) {
        double avg = std::accumulate(convergence_times.begin(), convergence_times.end(), 0.0) / convergence_times.size();
        std::cout << "   收敛时间: 最快=" << convergence_times.front()
                  << "ms, 最慢=" << convergence_times.back()
                  << "ms, 平均=" << std::fixed << std::setprecision(1) << avg << "ms\n";
        std::cout << "   分布: 快速(<100ms)=" << fast_convergence
                  << ", 中等(100-1000ms)=" << medium_convergence
                  << ", 慢速(>1000ms)=" << slow_convergence << "\n";
    }

    std::cout << "   JSON日志已保存到: " << log_file_path_ << "\n";
    std::cout << "✅ 监控完成\n";
}
