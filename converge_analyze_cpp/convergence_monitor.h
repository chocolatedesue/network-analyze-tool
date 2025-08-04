#pragma once

#include <string>
#include <vector>
#include <memory>
#include <atomic>
#include <mutex>
#include <thread>
#include <queue>
#include <condition_variable>
#include <chrono>
#include <unordered_map>
#include <unordered_set>
#include <functional>
#include <net/if.h>

// C++17兼容性检查
#if __cplusplus >= 201703L
    #include <shared_mutex>
    #include <optional>
    #define HAS_SHARED_MUTEX 1
    #define HAS_OPTIONAL 1
#else
    #define HAS_SHARED_MUTEX 0
    #define HAS_OPTIONAL 0
    // 为C++14/C++11提供fallback
    namespace std {
        template<typename T>
        class optional {
        private:
            bool has_value_;
            alignas(T) char storage_[sizeof(T)];
        public:
            optional() : has_value_(false) {}
            optional(const T& value) : has_value_(true) {
                new(storage_) T(value);
            }
            ~optional() {
                if (has_value_) {
                    reinterpret_cast<T*>(storage_)->~T();
                }
            }
            bool has_value() const { return has_value_; }
            const T& value() const { return *reinterpret_cast<const T*>(storage_); }
            T& value() { return *reinterpret_cast<T*>(storage_); }
            void reset() {
                if (has_value_) {
                    reinterpret_cast<T*>(storage_)->~T();
                    has_value_ = false;
                }
            }
            optional& operator=(const T& val) {
                reset();
                new(storage_) T(val);
                has_value_ = true;
                return *this;
            }
        };
    }
#endif

#include "logger.h"
#include "netlink_monitor.h"

// 前向声明
class NetlinkMonitor;
class Logger;

// 路由事件结构
struct RouteEvent {
    int64_t timestamp;
    std::string type;
    std::unordered_map<std::string, std::string> info;
    int64_t offset_from_netem;
    
    RouteEvent(int64_t ts, const std::string& t, 
               const std::unordered_map<std::string, std::string>& i, 
               int64_t offset)
        : timestamp(ts), type(t), info(i), offset_from_netem(offset) {}
};

// QDisc事件结构
struct QdiscEvent {
    int64_t timestamp;
    std::string type;
    std::unordered_map<std::string, std::string> info;
    
    QdiscEvent(int64_t ts, const std::string& t, 
               const std::unordered_map<std::string, std::string>& i)
        : timestamp(ts), type(t), info(i) {}
};

// 收敛会话类
class ConvergenceSession {
private:
    mutable std::mutex mutex_;
    std::atomic<int> convergence_check_count_{0};

public:
    int session_id;
    int64_t netem_event_time;
    std::unordered_map<std::string, std::string> netem_info;
    std::vector<RouteEvent> route_events;
    std::optional<int64_t> last_route_event_time;
    std::optional<int64_t> convergence_time;
    std::atomic<bool> is_converged{false};
    std::optional<int64_t> convergence_detected_time;

    ConvergenceSession(int id, int64_t netem_time, 
                      const std::unordered_map<std::string, std::string>& netem_info);

    void add_route_event(int64_t timestamp, const std::string& event_type, 
                        const std::unordered_map<std::string, std::string>& route_info);
    
    bool check_convergence(int64_t quiet_period_ms);
    
    int get_route_event_count() const;
    
    int64_t get_session_duration() const;
};

// 监控状态枚举
enum class MonitorState {
    IDLE,
    MONITORING
};

// 主监控器类
class ConvergenceMonitor {
private:
    // 基本配置
    std::unique_ptr<Logger> logger_;
    std::string log_file_path_;
    std::string router_name_;
    std::string monitor_id_;
    int64_t convergence_threshold_ms_;
    
    // 状态管理
    std::atomic<MonitorState> state_{MonitorState::IDLE};
    std::mutex session_mutex_;
    std::unique_ptr<ConvergenceSession> current_session_;
    std::vector<std::unique_ptr<ConvergenceSession>> completed_sessions_;
    std::atomic<int> session_counter_{0};
    
    // 统计计数器 (原子操作)
    std::atomic<int64_t> total_route_events_{0};
    std::atomic<int64_t> total_netem_triggers_{0};
    std::atomic<int64_t> total_route_triggers_{0};
    int64_t monitoring_start_time_;
    
    // 事件缓存
    mutable std::mutex qdisc_events_mutex_;
    std::queue<QdiscEvent> recent_qdisc_events_;
    static constexpr size_t MAX_QDISC_EVENTS = 20;
    
    // 线程管理
    std::atomic<bool> running_{false};
    std::vector<std::thread> worker_threads_;
    std::unique_ptr<NetlinkMonitor> netlink_monitor_;
    
    // 收敛检查线程
    std::thread convergence_checker_thread_;
    std::condition_variable convergence_cv_;
    std::mutex convergence_mutex_;

    // 内部方法
    void cleanup_old_events();
    std::string format_timestamp(int64_t timestamp_ms) const;
    std::string get_interface_name(int ifindex) const;
    std::unordered_map<std::string, std::string> parse_route_info(const void* route_data) const;
    std::unordered_map<std::string, std::string> parse_qdisc_info(const void* qdisc_data) const;
    bool is_netem_related_event(const std::unordered_map<std::string, std::string>& qdisc_info, 
                               const std::string& event_type) const;
    
    void handle_trigger_event(int64_t timestamp, const std::string& event_type, 
                             const std::unordered_map<std::string, std::string>& trigger_info, 
                             const std::string& trigger_source);
    
    void handle_qdisc_event(const std::unordered_map<std::string, std::string>& qdisc_info, 
                           const std::string& event_type);
    
    void handle_route_event(int64_t timestamp, const std::string& event_type, 
                           const std::unordered_map<std::string, std::string>& route_info);
    
    void convergence_checker_loop();
    void finish_current_session();
    void force_finish_session(const std::string& reason);
    void print_statistics();
    
    // 获取当前时间戳（毫秒）
    static int64_t get_current_timestamp_ms() {
        return std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
    }

public:
    ConvergenceMonitor(int64_t convergence_threshold_ms, 
                      const std::string& router_name, 
                      const std::string& log_path = "");
    
    ~ConvergenceMonitor();
    
    // 禁用拷贝和移动
    ConvergenceMonitor(const ConvergenceMonitor&) = delete;
    ConvergenceMonitor& operator=(const ConvergenceMonitor&) = delete;
    ConvergenceMonitor(ConvergenceMonitor&&) = delete;
    ConvergenceMonitor& operator=(ConvergenceMonitor&&) = delete;
    
    void start_monitoring();
    void stop_monitoring();
    
    // 事件处理回调 (由NetlinkMonitor调用)
    void on_route_event(const void* route_data, const std::string& event_type);
    void on_qdisc_event(const void* qdisc_data, const std::string& event_type);
};
