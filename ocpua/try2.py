#!/usr/bin/env python3
"""
修复的OPC UA客户端 - 包含完整的错误处理和连接诊断
"""

from opcua import Client
import time
import socket
import sys

def test_connection(host, port):
    """测试网络连接"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)  # 10秒超时
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        print(f"网络测试错误: {e}")
        return False

def main():
    # 你的树莓派IP地址
    RASPBERRY_PI_IP = "172.20.10.2"  # 修改为你的实际IP
    PORT = 3389
    SERVER_URL = f"opc.tcp://{RASPBERRY_PI_IP}:{PORT}/freeopcua/server/"
    
    print(f"正在连接到: {SERVER_URL}")
    
    # 步骤1: 测试网络连接
    print("步骤1: 测试网络连接...")
    if not test_connection(RASPBERRY_PI_IP, PORT):
        print(f"❌ 无法连接到 {RASPBERRY_PI_IP}:{PORT}")
        print("请检查:")
        print("1. 树莓派OPC UA服务器是否正在运行")
        print("2. 端口4840是否被防火墙阻止")
        print("3. 服务器是否绑定到正确的地址")
        
        # 尝试不同的端点URL
        alternative_urls = [
            f"opc.tcp://{RASPBERRY_PI_IP}:{PORT}/",
            f"opc.tcp://{RASPBERRY_PI_IP}:{PORT}/opcua/server",
            f"opc.tcp://{RASPBERRY_PI_IP}:{PORT}/UA/Server"
        ]
        
        print("\n尝试其他可能的端点...")
        for url in alternative_urls:
            print(f"测试: {url}")
            # 这里只是提示，实际测试需要OPC UA握手
        
        return
    else:
        print(f"✅ 端口 {PORT} 可以连接")
    
    # 步骤2: 创建OPC UA客户端
    print("步骤2: 创建OPC UA客户端...")
    client = Client(SERVER_URL)
    
    # 设置客户端参数
    client.session_timeout = 60000  # 60秒
    client.secure_channel_timeout = 60000  # 60秒
    
    try:
        print("步骤3: 连接到OPC UA服务器...")
        client.connect()
        print("✅ 已成功连接到OPC UA服务器")
        
        # 步骤4: 获取服务器信息
        print("步骤4: 获取服务器信息...")
        root = client.get_root_node()
        print(f"Root节点: {root}")
        
        objects = client.get_objects_node()
        print(f"Objects节点: {objects}")
        
        # 列出所有可用的对象
        print("可用的对象:")
        children = objects.get_children()
        for i, child in enumerate(children):
            print(f"  {i+1}. {child.get_browse_name()}: {child}")
        
        # 查找摄像头控制器对象
        camera_object = None
        try:
            # 尝试不同的可能名称
            possible_names = ["CameraController", "2:CameraController", "Camera", "2:Camera"]
            for name in possible_names:
                try:
                    camera_object = objects.get_child(name)
                    print(f"✅ 找到摄像头控制器: {camera_object} (名称: {name})")
                    break
                except:
                    continue
            
            if camera_object is None:
                print("❌ 未找到摄像头控制器对象")
                print("请检查服务器端的对象名称和命名空间")
                return
                
        except Exception as e:
            print(f"❌ 搜索摄像头控制器时出错: {e}")
            return
        
        # 步骤5: 探索摄像头控制器的内容
        print("步骤5: 探索摄像头控制器...")
        try:
            camera_children = camera_object.get_children()
            print("摄像头控制器包含:")
            for child in camera_children:
                browse_name = child.get_browse_name()
                node_class = child.get_node_class()
                print(f"  - {browse_name}: {child} (类型: {node_class})")
        except Exception as e:
            print(f"❌ 探索摄像头控制器失败: {e}")
            return
        
        # 步骤6: 尝试获取方法和变量
        print("步骤6: 获取方法和变量...")
        
        # 存储找到的节点
        methods = {}
        variables = {}
        
        for child in camera_children:
            browse_name = str(child.get_browse_name())
            node_class = child.get_node_class()
            
            try:
                if "Method" in str(node_class):
                    methods[browse_name] = child
                    print(f"  📋 方法: {browse_name}")
                elif "Variable" in str(node_class):
                    variables[browse_name] = child
                    value = child.get_value()
                    print(f"  📊 变量: {browse_name} = {value}")
            except Exception as e:
                print(f"  ⚠️ 读取 {browse_name} 时出错: {e}")
        
        # 步骤7: 测试功能（如果找到了相应的方法和变量）
        print("步骤7: 测试功能...")
        
        # 测试单张拍照
        capture_methods = [name for name in methods.keys() if "capture" in name.lower() or "image" in name.lower()]
        if capture_methods:
            method_name = capture_methods[0]
            capture_method = methods[method_name]
            print(f"\n测试拍照方法: {method_name}")
            try:
                result = camera_object.call_method(capture_method)
                print(f"✅ 拍照结果: {result}")
            except Exception as e:
                print(f"❌ 拍照失败: {e}")
        else:
            print("⚠️ 未找到拍照方法")
        
        # 测试运动检测
        motion_start_methods = [name for name in methods.keys() if "start" in name.lower() and "motion" in name.lower()]
        motion_stop_methods = [name for name in methods.keys() if "stop" in name.lower() and "motion" in name.lower()]
        
        if motion_start_methods and motion_stop_methods:
            start_method = methods[motion_start_methods[0]]
            stop_method = methods[motion_stop_methods[0]]
            
            print(f"\n测试运动检测...")
            try:
                # 启动运动检测
                result = camera_object.call_method(start_method)
                print(f"启动运动检测: {result}")
                
                # 等待几秒
                time.sleep(3)
                
                # 停止运动检测
                result = camera_object.call_method(stop_method)
                print(f"停止运动检测: {result}")
                
            except Exception as e:
                print(f"❌ 运动检测测试失败: {e}")
        else:
            print("⚠️ 未找到运动检测方法")
        
        # 测试变量读写
        writable_vars = []
        for name, var in variables.items():
            try:
                # 检查是否可写
                access_level = var.get_attribute(ua.AttributeIds.AccessLevel).Value.Value
                if access_level & 0x02:  # 可写位
                    writable_vars.append((name, var))
            except:
                pass
        
        if writable_vars:
            print(f"\n测试变量写入...")
            var_name, var_node = writable_vars[0]
            try:
                old_value = var_node.get_value()
                print(f"变量 {var_name} 当前值: {old_value}")
                
                # 根据数据类型设置新值
                if isinstance(old_value, (int, float)):
                    new_value = old_value + 1 if isinstance(old_value, int) else old_value + 0.1
                elif isinstance(old_value, bool):
                    new_value = not old_value
                else:
                    new_value = f"modified_{old_value}"
                
                var_node.set_value(new_value)
                print(f"设置新值: {new_value}")
                
                # 验证
                time.sleep(1)
                current_value = var_node.get_value()
                print(f"验证值: {current_value}")
                
                # 恢复原值
                var_node.set_value(old_value)
                print(f"恢复原值: {old_value}")
                
            except Exception as e:
                print(f"❌ 变量写入测试失败: {e}")
        
        print("\n✅ 测试完成！")
        
    except ConnectionRefusedError:
        print("❌ 连接被拒绝")
        print("可能的原因:")
        print("1. OPC UA服务器未启动")
        print("2. 服务器监听的地址不正确")
        print("3. 端口被其他程序占用")
        
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        
        # 根据错误类型给出建议
        error_msg = str(e).lower()
        if "timeout" in error_msg or "cancelled" in error_msg:
            print("\n超时错误可能的原因:")
            print("1. 服务器响应太慢")
            print("2. 网络延迟过高")
            print("3. 服务器端点URL不正确")
            print("4. 服务器安全设置问题")
        elif "bad" in error_msg and "url" in error_msg:
            print("\nURL错误可能的原因:")
            print("1. 端点URL格式不正确")
            print("2. 服务器使用不同的端点路径")
        
        print(f"\n建议在树莓派上检查:")
        print("1. 运行: netstat -tulpn | grep 4840")
        print("2. 检查服务器日志")
        print("3. 尝试本地连接测试")
        
    finally:
        try:
            client.disconnect()
            print("✅ 已断开连接")
        except:
            print("⚠️ 断开连接时出现警告（可以忽略）")

if __name__ == "__main__":
    # 导入ua模块用于属性访问
    from opcua import ua
    main()
