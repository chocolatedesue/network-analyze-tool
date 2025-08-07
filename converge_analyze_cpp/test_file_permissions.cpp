#include "logger.h"
#include <iostream>
#include <sys/stat.h>
#include <unistd.h>

int main() {
    std::cout << "测试文件权限设置...\n";
    
    try {
        // 创建一个临时日志文件
        std::string test_log_path = "./test_permissions.json";
        
        // 删除可能存在的测试文件
        unlink(test_log_path.c_str());
        
        // 创建Logger实例
        Logger logger(test_log_path);
        
        // 启动logger（这会创建文件）
        logger.start();
        
        // 检查文件权限
        struct stat file_stat;
        if (stat(test_log_path.c_str(), &file_stat) == 0) {
            mode_t permissions = file_stat.st_mode & 0777;
            std::cout << "文件权限: " << std::oct << permissions << std::dec << "\n";
            
            if (permissions == 0666) {
                std::cout << "✅ 文件权限正确设置为 666 (公共可读写)\n";
            } else {
                std::cout << "❌ 文件权限不正确，期望 666，实际 " << std::oct << permissions << std::dec << "\n";
            }
            
            // 检查各种权限位
            std::cout << "权限详情:\n";
            std::cout << "  所有者: " << ((permissions & 0600) == 0600 ? "读写" : "其他") << "\n";
            std::cout << "  组: " << ((permissions & 0060) == 0060 ? "读写" : "其他") << "\n";
            std::cout << "  其他: " << ((permissions & 0006) == 0006 ? "读写" : "其他") << "\n";
        } else {
            std::cout << "❌ 无法获取文件状态\n";
        }
        
        // 停止logger
        logger.stop();
        
        // 清理测试文件
        unlink(test_log_path.c_str());
        
    } catch (const std::exception& e) {
        std::cerr << "❌ 测试失败: " << e.what() << "\n";
        return 1;
    }
    
    std::cout << "✅ 权限测试完成\n";
    return 0;
}
