#pragma once

#include <string>
#include <fstream>
#include <memory>
#include <queue>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <atomic>
#include <unordered_map>

// C++17兼容性检查
#if __cplusplus >= 201703L
    #include <optional>
    #define HAS_OPTIONAL 1
#else
    #define HAS_OPTIONAL 0
    // 简单的optional替代实现
    template<typename T>
    class optional {
    private:
        bool has_value_;
        T value_;
    public:
        optional() : has_value_(false) {}
        optional(const T& val) : has_value_(true), value_(val) {}

        bool has_value() const { return has_value_; }
        const T& value() const { return value_; }
        T& value() { return value_; }

        explicit operator bool() const { return has_value_; }
    };
#endif

// 简化的JSON值类型实现，避免variant依赖
class JsonValue {
public:
    enum Type { STRING, INT64, DOUBLE, BOOL };

private:
    Type type_;
    std::string str_val_;
    int64_t int_val_;
    double double_val_;
    bool bool_val_;

public:
    // 默认构造函数，创建空字符串类型
    JsonValue() : type_(STRING), str_val_(), int_val_(0), double_val_(0.0), bool_val_(false) {}
    JsonValue(const std::string& s) : type_(STRING), str_val_(s), int_val_(0), double_val_(0.0), bool_val_(false) {}
    JsonValue(const char* s) : type_(STRING), str_val_(s), int_val_(0), double_val_(0.0), bool_val_(false) {}
    JsonValue(int64_t i) : type_(INT64), int_val_(i), double_val_(0.0), bool_val_(false) {}
    JsonValue(int i) : type_(INT64), int_val_(i), double_val_(0.0), bool_val_(false) {}
    JsonValue(double d) : type_(DOUBLE), str_val_(), int_val_(0), double_val_(d), bool_val_(false) {}
    JsonValue(bool b) : type_(BOOL), str_val_(), int_val_(0), double_val_(0.0), bool_val_(b) {}

    Type get_type() const { return type_; }
    const std::string& as_string() const { return str_val_; }
    int64_t as_int64() const { return int_val_; }
    double as_double() const { return double_val_; }
    bool as_bool() const { return bool_val_; }
};

using JsonObject = std::unordered_map<std::string, JsonValue>;

// 日志条目结构
struct LogEntry {
    JsonObject data;
    std::chrono::system_clock::time_point timestamp;
    
    LogEntry(const JsonObject& d) 
        : data(d), timestamp(std::chrono::system_clock::now()) {}
};

// 异步日志记录器类
class Logger {
private:
    std::string log_file_path_;
    std::ofstream log_file_;
    
    // 异步日志队列
    std::queue<LogEntry> log_queue_;
    mutable std::mutex queue_mutex_;
    std::condition_variable queue_cv_;
    
    // 日志处理线程
    std::thread log_thread_;
    std::atomic<bool> running_{false};
    
    // 队列大小限制
    static constexpr size_t MAX_QUEUE_SIZE = 1000;
    
    // 内部方法
    void log_processor_loop();
    std::string json_to_string(const JsonObject& json) const;
    std::string json_value_to_string(const JsonValue& value) const;
    std::string escape_json_string(const std::string& str) const;

public:
    Logger(const std::string& log_path = "");
    ~Logger();
    
    // 禁用拷贝和移动
    Logger(const Logger&) = delete;
    Logger& operator=(const Logger&) = delete;
    Logger(Logger&&) = delete;
    Logger& operator=(Logger&&) = delete;
    
    void start();
    void stop();
    
    // 异步记录结构化日志
    void log_async(const JsonObject& data);
    
    // 同步记录日志（用于程序退出时的最终统计）
    void log_sync(const JsonObject& data);
    
    // 获取日志文件路径
    const std::string& get_log_file_path() const { return log_file_path_; }
    
    // 辅助方法：创建常用的JSON对象
    static JsonObject create_event_log(const std::string& event_type, 
                                      const std::string& router_name,
                                      const std::string& user);
    
    static JsonObject create_session_start_log(const std::string& router_name,
                                              int session_id,
                                              const std::string& trigger_source,
                                              const std::string& trigger_event_type,
                                              const std::unordered_map<std::string, std::string>& trigger_info,
                                              const std::string& user);
    
    static JsonObject create_route_event_log(const std::string& router_name,
                                            int session_id,
                                            const std::string& route_event_type,
                                            int64_t route_event_number,
                                            int session_event_number,
                                            int64_t offset_from_trigger_ms,
                                            const std::unordered_map<std::string, std::string>& route_info,
                                            const std::string& user);
    
#if HAS_OPTIONAL
    static JsonObject create_session_completed_log(const std::string& router_name,
                                                  int session_id,
                                                  const std::optional<int64_t>& convergence_time_ms,
                                                  int route_events_count,
                                                  int64_t session_duration_ms,
                                                  int64_t convergence_threshold_ms,
                                                  const std::unordered_map<std::string, std::string>& netem_info,
                                                  const std::string& user);
#else
    static JsonObject create_session_completed_log(const std::string& router_name,
                                                  int session_id,
                                                  const optional<int64_t>& convergence_time_ms,
                                                  int route_events_count,
                                                  int64_t session_duration_ms,
                                                  int64_t convergence_threshold_ms,
                                                  const std::unordered_map<std::string, std::string>& netem_info,
                                                  const std::string& user);
#endif
    
    static JsonObject create_monitoring_start_log(const std::string& router_name,
                                                 const std::string& user,
                                                 int64_t convergence_threshold_ms,
                                                 const std::string& log_file_path,
                                                 const std::string& monitor_id);
    
    static JsonObject create_monitoring_completed_log(const std::string& router_name,
                                                     const std::string& log_file_path,
                                                     const std::string& user,
                                                     int64_t total_listen_duration_ms,
                                                     int64_t convergence_threshold_ms,
                                                     int64_t total_trigger_events,
                                                     int64_t netem_events_count,
                                                     int64_t route_events_in_trigger,
                                                     int64_t total_route_events,
                                                     int completed_sessions_count,
                                                     const std::string& monitor_id);

private:
    // 设置默认日志路径
    std::string setup_default_log_path() const;

    // 解析日志路径（检测是文件还是目录）
    std::string resolve_log_path(const std::string& input_path) const;

    // 确保日志目录存在
    bool ensure_log_directory(const std::string& path) const;

    // 测试文件是否可以创建
    bool test_file_creation(const std::string& path) const;

    // 确保日志文件具有正确的权限（666）
    void ensure_log_file_permissions(const std::string& path) const;
};
