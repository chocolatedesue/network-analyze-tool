#include "logger.h"
#include <iostream>
#include <iomanip>
#include <sstream>
#include <pwd.h>
#include <unistd.h>
#include <sys/stat.h>
#include <libgen.h>
#include <cstring>

// C++17兼容性检查
#if __cplusplus >= 201703L
    #include <filesystem>
    #define HAS_FILESYSTEM 1
#else
    #define HAS_FILESYSTEM 0
#endif

Logger::Logger(const std::string& log_path) {
    if (log_path.empty()) {
        log_file_path_ = setup_default_log_path();
    } else {
        log_file_path_ = log_path;
        if (!ensure_log_directory(log_path)) {
            // 如果无法创建目录，回退到当前目录
            // 提取文件名
            const char* filename = strrchr(log_path.c_str(), '/');
            if (filename) {
                log_file_path_ = "./" + std::string(filename + 1);
            } else {
                log_file_path_ = "./" + log_path;
            }
        }
    }
}

Logger::~Logger() {
    stop();
}

void Logger::start() {
    if (running_.load()) {
        return;
    }
    
    running_.store(true);
    
    // 尝试打开日志文件
    log_file_.open(log_file_path_, std::ios::out | std::ios::app);
    if (!log_file_.is_open()) {
        std::cerr << "无法打开日志文件 " << log_file_path_ << "，仅使用控制台输出\n";
    } else {
        std::cout << "JSON结构化日志文件已配置: " << log_file_path_ << "\n";
    }
    
    // 启动日志处理线程
    log_thread_ = std::thread(&Logger::log_processor_loop, this);
}

void Logger::stop() {
    if (!running_.load()) {
        return;
    }
    
    running_.store(false);
    
    // 通知日志处理线程
    queue_cv_.notify_all();
    
    // 等待线程结束
    if (log_thread_.joinable()) {
        log_thread_.join();
    }
    
    // 关闭文件
    if (log_file_.is_open()) {
        log_file_.close();
    }
}

void Logger::log_async(const JsonObject& data) {
    std::unique_lock<std::mutex> lock(queue_mutex_);
    
    // 如果队列满了，丢弃最旧的条目
    if (log_queue_.size() >= MAX_QUEUE_SIZE) {
        log_queue_.pop();
        std::cout << "⚠️  日志队列满，丢弃一条日志\n";
    }
    
    log_queue_.emplace(data);
    lock.unlock();
    
    queue_cv_.notify_one();
}

void Logger::log_sync(const JsonObject& data) {
    std::string json_str = json_to_string(data);
    
    if (log_file_.is_open()) {
        log_file_ << json_str << "\n";
        log_file_.flush();
    } else {
        std::cout << json_str << "\n";
    }
}

void Logger::log_processor_loop() {
    while (running_.load() || !log_queue_.empty()) {
        std::unique_lock<std::mutex> lock(queue_mutex_);
        
        // 等待有日志条目或停止信号
        queue_cv_.wait(lock, [this] { 
            return !log_queue_.empty() || !running_.load(); 
        });
        
        // 处理所有待处理的日志条目
        while (!log_queue_.empty()) {
            LogEntry entry = std::move(log_queue_.front());
            log_queue_.pop();
            lock.unlock();
            
            // 生成JSON字符串并写入
            std::string json_str = json_to_string(entry.data);
            
            if (log_file_.is_open()) {
                log_file_ << json_str << "\n";
                log_file_.flush();
            } else {
                std::cout << json_str << "\n";
            }
            
            lock.lock();
        }
    }
}

std::string Logger::json_to_string(const JsonObject& json) const {
    std::ostringstream oss;
    oss << "{";

    bool first = true;
    for (const auto& pair : json) {
        if (!first) {
            oss << ",";
        }
        first = false;

        oss << "\"" << escape_json_string(pair.first) << "\":";
        oss << json_value_to_string(pair.second);
    }

    oss << "}";
    return oss.str();
}

std::string Logger::json_value_to_string(const JsonValue& value) const {
    switch (value.get_type()) {
        case JsonValue::STRING:
            return "\"" + escape_json_string(value.as_string()) + "\"";
        case JsonValue::INT64:
            return std::to_string(value.as_int64());
        case JsonValue::DOUBLE: {
            std::ostringstream oss;
            oss << std::fixed << std::setprecision(3) << value.as_double();
            return oss.str();
        }
        case JsonValue::BOOL:
            return value.as_bool() ? "true" : "false";
        default:
            return "null";
    }
}

std::string Logger::escape_json_string(const std::string& str) const {
    std::string escaped;
    escaped.reserve(str.length() + 10); // 预留一些空间给转义字符
    
    for (char c : str) {
        switch (c) {
            case '"':  escaped += "\\\""; break;
            case '\\': escaped += "\\\\"; break;
            case '\b': escaped += "\\b"; break;
            case '\f': escaped += "\\f"; break;
            case '\n': escaped += "\\n"; break;
            case '\r': escaped += "\\r"; break;
            case '\t': escaped += "\\t"; break;
            default:
                if (c < 0x20) {
                    // 控制字符
                    std::ostringstream oss;
                    oss << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(c);
                    escaped += oss.str();
                } else {
                    escaped += c;
                }
                break;
        }
    }
    
    return escaped;
}

std::string Logger::setup_default_log_path() const {
    std::string log_dir = "/var/log/frr";

    // 检查目录是否存在，如果不存在尝试创建
    struct stat st;
    if (stat(log_dir.c_str(), &st) != 0) {
        // 目录不存在，尝试创建
        if (mkdir(log_dir.c_str(), 0755) != 0) {
            log_dir = ".";
            std::cout << "无法创建 /var/log/frr 目录，使用当前目录: " << log_dir << "\n";
        }
    }

    return log_dir + "/async_route_convergence_cpp.json";
}

bool Logger::ensure_log_directory(const std::string& path) const {
    // 提取目录路径
    size_t last_slash = path.find_last_of('/');
    if (last_slash == std::string::npos) {
        return true; // 当前目录
    }

    std::string dir_path = path.substr(0, last_slash);
    if (dir_path.empty()) {
        return true;
    }

    // 检查目录是否存在
    struct stat st;
    if (stat(dir_path.c_str(), &st) == 0) {
        return S_ISDIR(st.st_mode);
    }

    // 尝试创建目录（递归）
    return ensure_log_directory(dir_path) && mkdir(dir_path.c_str(), 0755) == 0;
}

// 静态辅助方法实现
JsonObject Logger::create_event_log(const std::string& event_type,
                                   const std::string& router_name,
                                   const std::string& user) {
    JsonObject log;
    log["event_type"] = event_type;
    log["router_name"] = router_name;
    log["user"] = user;

    // 添加时间戳
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    std::ostringstream oss;
    oss << std::put_time(std::gmtime(&time_t), "%Y-%m-%dT%H:%M:%S");
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()) % 1000;
    oss << "." << std::setfill('0') << std::setw(3) << ms.count() << "Z";
    log["timestamp"] = oss.str();

    return log;
}

JsonObject Logger::create_session_start_log(const std::string& router_name,
                                           int session_id,
                                           const std::string& trigger_source,
                                           const std::string& trigger_event_type,
                                           const std::unordered_map<std::string, std::string>& trigger_info,
                                           const std::string& user) {
    auto log = create_event_log("session_started", router_name, user);
    log["session_id"] = static_cast<int64_t>(session_id);
    log["trigger_source"] = trigger_source;
    log["trigger_event_type"] = trigger_event_type;

    // 序列化trigger_info (简化版本)
    std::ostringstream trigger_oss;
    trigger_oss << "{";
    bool first = true;
    for (const auto& pair : trigger_info) {
        if (!first) trigger_oss << ",";
        first = false;
        trigger_oss << "\"" << pair.first << "\":\"" << pair.second << "\"";
    }
    trigger_oss << "}";
    log["trigger_info"] = trigger_oss.str();

    return log;
}

JsonObject Logger::create_route_event_log(const std::string& router_name,
                                         int session_id,
                                         const std::string& route_event_type,
                                         int64_t route_event_number,
                                         int session_event_number,
                                         int64_t offset_from_trigger_ms,
                                         const std::unordered_map<std::string, std::string>& route_info,
                                         const std::string& user) {
    auto log = create_event_log("route_event", router_name, user);
    log["session_id"] = static_cast<int64_t>(session_id);
    log["route_event_type"] = route_event_type;
    log["route_event_number"] = route_event_number;
    log["session_event_number"] = static_cast<int64_t>(session_event_number);
    log["offset_from_trigger_ms"] = offset_from_trigger_ms;

    // 序列化route_info
    std::ostringstream route_oss;
    route_oss << "{";
    bool first = true;
    for (const auto& pair : route_info) {
        if (!first) route_oss << ",";
        first = false;
        route_oss << "\"" << pair.first << "\":\"" << pair.second << "\"";
    }
    route_oss << "}";
    log["route_info"] = route_oss.str();

    return log;
}

JsonObject Logger::create_session_completed_log(const std::string& router_name,
                                               int session_id,
                                               const std::optional<int64_t>& convergence_time_ms,
                                               int route_events_count,
                                               int64_t session_duration_ms,
                                               int64_t convergence_threshold_ms,
                                               const std::unordered_map<std::string, std::string>& netem_info,
                                               const std::string& user) {
    auto log = create_event_log("session_completed", router_name, user);
    log["session_id"] = static_cast<int64_t>(session_id);

    if (convergence_time_ms.has_value()) {
        log["convergence_time_ms"] = convergence_time_ms.value();
    }

    log["route_events_count"] = static_cast<int64_t>(route_events_count);
    log["session_duration_ms"] = session_duration_ms;
    log["convergence_threshold_ms"] = convergence_threshold_ms;

    // 序列化netem_info
    std::ostringstream netem_oss;
    netem_oss << "{";
    bool first = true;
    for (const auto& pair : netem_info) {
        if (!first) netem_oss << ",";
        first = false;
        netem_oss << "\"" << pair.first << "\":\"" << pair.second << "\"";
    }
    netem_oss << "}";
    log["netem_info"] = netem_oss.str();

    return log;
}

JsonObject Logger::create_monitoring_start_log(const std::string& router_name,
                                              const std::string& user,
                                              int64_t convergence_threshold_ms,
                                              const std::string& log_file_path,
                                              const std::string& monitor_id) {
    auto log = create_event_log("monitoring_started", router_name, user);
    log["convergence_threshold_ms"] = convergence_threshold_ms;
    log["log_file_path"] = log_file_path;
    log["monitor_id"] = monitor_id;

    // 添加UTC时间
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    std::ostringstream oss;
    oss << std::put_time(std::gmtime(&time_t), "%Y-%m-%dT%H:%M:%S");
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()) % 1000;
    oss << "." << std::setfill('0') << std::setw(3) << ms.count() << "Z";
    log["utc_time"] = oss.str();
    log["listen_start_time"] = oss.str();

    return log;
}

JsonObject Logger::create_monitoring_completed_log(const std::string& router_name,
                                                  const std::string& log_file_path,
                                                  const std::string& user,
                                                  int64_t total_listen_duration_ms,
                                                  int64_t convergence_threshold_ms,
                                                  int64_t total_trigger_events,
                                                  int64_t netem_events_count,
                                                  int64_t route_events_in_trigger,
                                                  int64_t total_route_events,
                                                  int completed_sessions_count,
                                                  const std::string& monitor_id) {
    auto log = create_event_log("monitoring_completed", router_name, user);
    log["log_file_path"] = log_file_path;
    log["total_listen_duration_ms"] = total_listen_duration_ms;
    log["total_listen_duration_seconds"] = static_cast<double>(total_listen_duration_ms) / 1000.0;
    log["convergence_threshold_ms"] = convergence_threshold_ms;
    log["total_trigger_events"] = total_trigger_events;
    log["netem_events_count"] = netem_events_count;
    log["route_events_in_trigger"] = route_events_in_trigger;
    log["total_route_events"] = total_route_events;
    log["completed_sessions_count"] = static_cast<int64_t>(completed_sessions_count);
    log["monitor_id"] = monitor_id;

    // 添加时间信息
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    std::ostringstream oss;
    oss << std::put_time(std::gmtime(&time_t), "%Y-%m-%dT%H:%M:%S");
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()) % 1000;
    oss << "." << std::setfill('0') << std::setw(3) << ms.count() << "Z";
    log["utc_time"] = oss.str();
    log["listen_end_time"] = oss.str();
    log["extraction_timestamp"] = oss.str();
    log["extracted_by"] = "async_event_monitor_cpp_v1.0_" + monitor_id;

    return log;
}
