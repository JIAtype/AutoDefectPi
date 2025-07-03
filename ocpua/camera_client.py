#!/usr/bin/env python3
"""
OPC UA客户端，用于控制树莓派摄像头服务器
"""

from opcua import Client, ua
import time
import socket
import sys

# --- 配置参数 ---
RASPBERRY_PI_IP = "172.20.10.2"  # <<<--- 修改为你的树莓派的实际IP地址
PORT = 4840
SERVER_URL = f"opc.tcp://{RASPBERRY_PI_IP}:{PORT}/freeopcua/server/"
NAMESPACE_URI = "http://raspberrypi.camera.opcua" # 与服务器端一致

# 全局客户端变量
client = None

def test_network_connection(host, port, timeout=5):
    """测试基础TCP网络连接"""
    print(f"测试网络连接到 {host}:{port}...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        if result == 0:
            print(f"✅ 端口 {port} 在 {host} 上可达。")
            return True
        else:
            print(f"❌ 无法连接到 {host}:{port} (错误码: {result})。")
            return False
    except socket.gaierror:
        print(f"❌ 主机名解析错误: {host}")
        return False
    except socket.timeout:
        print(f"❌ 连接超时: {host}:{port}")
        return False
    except Exception as e:
        print(f"❌ 网络测试时发生未知错误: {e}")
        return False

def connect_to_server():
    """连接到OPC UA服务器"""
    global client
    print(f"正在连接到 OPC UA 服务器: {SERVER_URL}")
    client = Client(SERVER_URL)
    client.session_timeout = 60000  # 60秒
    # client.secure_channel_timeout = 10000 # 减少超时以便更快失败 (如果需要)
    try:
        client.connect()
        print("✅ 成功连接到 OPC UA 服务器。")
        return True
    except ConnectionRefusedError:
        print("❌ 连接被服务器拒绝。请检查服务器是否正在运行并且监听正确的地址和端口。")
        return False
    except Exception as e:
        print(f"❌ 连接到 OPC UA 服务器失败: {e}")
        if "BadTcpEndpointUrlInvalid" in str(e) or "BadConnectionRejected" in str(e):
            print("   提示: Endpoint URL 可能不正确或服务器未完全启动。")
        elif "timeout" in str(e).lower():
            print("   提示: 连接超时。检查网络连接和服务器响应。")
        return False

def get_camera_controller_node():
    """获取CameraController对象节点"""
    if not client:
        print("客户端未连接。")
        return None
    try:
        objects_node = client.get_objects_node()
        # 获取服务器端注册的命名空间的索引
        ns_idx = client.get_namespace_index(NAMESPACE_URI)
        controller_node_name = f"{ns_idx}:CameraController"
        camera_object = objects_node.get_child(controller_node_name)
        print(f"✅ 找到摄像头控制器对象: {camera_object} (QualifiedName: {controller_node_name})")
        return camera_object, ns_idx
    except ua.UaError as e:
        print(f"❌ 获取CameraController节点时发生OPC UA错误: {e}")
        if "BadNodeIdUnknown" in str(e):
             print(f"   提示: 节点名称 '{controller_node_name}' 在服务器上未找到。检查服务器端定义和命名空间。")
        objects_node = client.get_objects_node()
        print("   可用对象:")
        for child in objects_node.get_children():
            print(f"     - {child.get_browse_name()} (NodeId: {child.nodeid})")
        return None, -1
    except Exception as e:
        print(f"❌ 获取CameraController节点时发生未知错误: {e}")
        return None, -1


def call_camera_method(camera_object, ns_idx, method_name, *args):
    """调用CameraController对象上的方法"""
    if not camera_object:
        print("CameraController对象无效。")
        return None
    try:
        method_node_id_str = f"ns={ns_idx};s={method_name}" # 另一种构造 NodeId 的方式
        # 或者通过 get_child 获取方法节点
        method_node = camera_object.get_child(f"{ns_idx}:{method_name}")

        print(f"调用方法 '{method_name}' (Node: {method_node})...")
        
        # 将Python参数转换为OPC UA Variants (如果方法有输入参数)
        ua_args = []
        for arg in args:
            # 这里需要根据参数类型创建正确的Variant，本例中方法无输入参数
            # ua_args.append(ua.Variant(arg, ua.VariantType.Int64)) # 示例
            pass

        result_variants = camera_object.call_method(method_node, *ua_args)
        
        if result_variants:
            # 假设方法返回一个字符串结果
            result_str = result_variants[0] # .Value 如果是Variant对象
            print(f"✅ 方法 '{method_name}' 调用成功。结果: {result_str}")
            return result_str
        else:
            print(f"✅ 方法 '{method_name}' 调用成功，但无返回值或返回空。")
            return None # 或者 True 表示成功调用
            
    except ua.UaError as e:
        print(f"❌ 调用方法 '{method_name}' 失败: {e}")
        if "BadMethodInvalid" in str(e) or "BadNodeIdUnknown" in str(e):
            print(f"   提示: 方法节点 '{method_name}' 未找到或无效。")
        elif "BadUserAccessDenied" in str(e):
            print(f"   提示: 用户无权执行此方法。")
        return None
    except Exception as e:
        print(f"❌ 调用方法 '{method_name}' 时发生未知错误: {e}")
        return None


def get_variable_value(camera_object, ns_idx, variable_name):
    """获取变量的值"""
    if not camera_object: return None
    try:
        var_node = camera_object.get_child(f"{ns_idx}:{variable_name}")
        value = var_node.get_value()
        print(f"变量 '{variable_name}': {value}")
        return value
    except Exception as e:
        print(f"❌ 读取变量 '{variable_name}' 失败: {e}")
        return None

def set_variable_value(camera_object, ns_idx, variable_name, value):
    """设置变量的值"""
    if not camera_object: return False
    try:
        var_node = camera_object.get_child(f"{ns_idx}:{variable_name}")
        # data_type = var_node.get_data_type_as_variant_type() # 获取数据类型
        # ua_value = ua.Variant(value, data_type)
        # var_node.set_value(ua_value)
        var_node.set_value(value) # python-opcua通常能自动转换简单类型
        print(f"设置变量 '{variable_name}' 为: {value}")
        # 验证 (可选)
        time.sleep(0.2) # 给服务器一点时间处理
        new_value = var_node.get_value()
        if new_value == value or (isinstance(value, float) and abs(new_value - value) < 0.001): # 浮点数比较
             print(f"✅ 变量 '{variable_name}' 验证成功: {new_value}")
             return True
        else:
            print(f"⚠️ 变量 '{variable_name}' 设置后读取值为 {new_value}，与设置值 {value} 不符。")
            return False

    except Exception as e:
        print(f"❌ 写入变量 '{variable_name}' 失败: {e}")
        if "BadUserAccessDenied" in str(e) or "BadNotWritable" in str(e):
            print(f"   提示: 变量不可写或无写入权限。")
        return False

def display_menu_and_get_choice():
    print("\n--- 摄像头控制菜单 ---")
    print("1. 拍摄单张照片")
    print("2. 启动运动检测")
    print("3. 停止运动检测")
    print("4. 获取运动检测状态")
    print("5. 获取上一张图片路径")
    print("6. 查看/修改运动检测阈值 (Threshold)")
    print("7. 查看/修改运动检测灵敏度/面积 (Sensitivity/MinArea)")
    print("8. 查看/修改运动检测捕获间隔 (MotionCaptureInterval)")
    print("0. 退出")
    choice = input("请输入选项: ")
    return choice

def main():
    global client
    if not test_network_connection(RASPBERRY_PI_IP, PORT):
        print("无法连接到服务器的网络端口。请检查IP地址、端口和服务器运行状态。")
        return

    if not connect_to_server():
        return

    camera_ctrl_node, ns_idx = get_camera_controller_node()
    if not camera_ctrl_node:
        client.disconnect()
        return
    
    print(f"\n命名空间索引 {NAMESPACE_URI} -> {ns_idx}")
    print("摄像头控制器方法和变量探索:")
    try:
        for child_node in camera_ctrl_node.get_children():
            browse_name = child_node.get_browse_name()
            node_class = child_node.get_node_class()
            print(f"  - {browse_name.Name} (NS:{browse_name.NamespaceIndex}, Class:{node_class}, NodeId:{child_node.nodeid})")
    except Exception as e:
        print(f"探索节点时出错: {e}")


    running = True
    while running:
        choice = display_menu_and_get_choice()

        if choice == '1':
            call_camera_method(camera_ctrl_node, ns_idx, "CaptureImage")
        elif choice == '2':
            call_camera_method(camera_ctrl_node, ns_idx, "StartMotionDetection")
        elif choice == '3':
            call_camera_method(camera_ctrl_node, ns_idx, "StopMotionDetection")
        elif choice == '4':
            get_variable_value(camera_ctrl_node, ns_idx, "MotionDetectionStatus")
        elif choice == '5':
            get_variable_value(camera_ctrl_node, ns_idx, "LastImagePath")
        elif choice == '6':
            current_val = get_variable_value(camera_ctrl_node, ns_idx, "Threshold")
            if current_val is not None:
                new_val_str = input(f"当前 Threshold: {current_val}. 输入新值 (整数, 0-255, 留空不修改): ")
                if new_val_str:
                    try:
                        new_val = int(new_val_str)
                        set_variable_value(camera_ctrl_node, ns_idx, "Threshold", new_val)
                    except ValueError:
                        print("无效输入，请输入整数。")
        elif choice == '7':
            current_val = get_variable_value(camera_ctrl_node, ns_idx, "Sensitivity")
            if current_val is not None:
                new_val_str = input(f"当前 Sensitivity/MinArea: {current_val}. 输入新值 (整数, 建议>10, 留空不修改): ")
                if new_val_str:
                    try:
                        new_val = int(new_val_str)
                        set_variable_value(camera_ctrl_node, ns_idx, "Sensitivity", new_val)
                    except ValueError:
                        print("无效输入，请输入整数。")
        elif choice == '8':
            current_val = get_variable_value(camera_ctrl_node, ns_idx, "MotionCaptureInterval")
            if current_val is not None:
                new_val_str = input(f"当前 MotionCaptureInterval (秒): {current_val}. 输入新值 (整数, >=0, 留空不修改): ")
                if new_val_str:
                    try:
                        new_val = int(new_val_str)
                        if new_val >= 0:
                           set_variable_value(camera_ctrl_node, ns_idx, "MotionCaptureInterval", new_val)
                        else:
                           print("间隔不能为负数。")
                    except ValueError:
                        print("无效输入，请输入整数。")
        elif choice == '0':
            running = False
        else:
            print("无效选项，请重试。")
        
        time.sleep(0.5) # 短暂延时，避免连续快速操作

    if client:
        try:
            client.disconnect()
            print("✅ 已断开与服务器的连接。")
        except Exception as e:
            print(f"⚠️ 断开连接时发生错误: {e}")

if __name__ == "__main__":
    main()