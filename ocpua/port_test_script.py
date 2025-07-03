#!/usr/bin/env python3
"""
简单的端口连接测试脚本
"""

import socket
import time

def test_port(host, port, timeout=10):
    """测试端口连接"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        print(f"正在测试连接到 {host}:{port}...")
        start_time = time.time()
        
        result = sock.connect_ex((host, port))
        
        end_time = time.time()
        response_time = (end_time - start_time) * 1000  # 转换为毫秒
        
        sock.close()
        
        if result == 0:
            print(f"✅ 端口 {port} 开放 (响应时间: {response_time:.2f}ms)")
            return True
        else:
            print(f"❌ 端口 {port} 关闭或无响应 (错误代码: {result})")
            return False
            
    except socket.timeout:
        print(f"❌ 连接超时 (>{timeout}秒)")
        return False
    except Exception as e:
        print(f"❌ 连接错误: {e}")
        return False

def main():

    # host = "172.20.10.2"
    port = 4840

    host = "172.20.10.2"
    # port = 3389
    
    print("=== OPC UA端口连接测试 ===")
    print(f"目标: {host}:{port}")
    print("-" * 30)
    
    # 测试多次
    success_count = 0
    total_tests = 5
    
    for i in range(total_tests):
        print(f"\n测试 {i+1}/{total_tests}:")
        if test_port(host, port):
            success_count += 1
        time.sleep(1)
    
    print("\n" + "=" * 30)
    print(f"测试结果: {success_count}/{total_tests} 成功")
    
    if success_count == total_tests:
        print("✅ 端口连接稳定，可以尝试OPC UA连接")
    elif success_count > 0:
        print("⚠️ 端口连接不稳定，可能有间歇性问题")
    else:
        print("❌ 端口完全无法连接")
        print("\n排查建议:")
        print("1. 确认树莓派上OPC UA服务器正在运行")
        print("2. 检查防火墙设置")
        print("3. 检查服务器绑定地址 (应该是 0.0.0.0:4840)")

if __name__ == "__main__":
    main()
