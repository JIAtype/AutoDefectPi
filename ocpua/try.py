from opcua import Client
import time

# 连接到服务器
client = Client("opc.tcp://172.20.10.2:3389/freeopcua/server/")  # 替换为你的树莓派IP

try:
    client.connect()
    print("已连接到OPC UA服务器")
    
    # 获取摄像头控制对象
    root = client.get_root_node()
    camera_object = root.get_child(["0:Objects", "2:CameraController"])
    
    # 获取方法
    capture_method = camera_object.get_child("2:CaptureImage")
    start_motion_method = camera_object.get_child("2:StartMotionDetection")
    stop_motion_method = camera_object.get_child("2:StopMotionDetection")
    
    # 获取状态变量
    motion_status = camera_object.get_child("2:MotionDetectionStatus")
    last_image = camera_object.get_child("2:LastImagePath")
    
    # 捕捉单张图片
    print("捕捉图片...")
    result = camera_object.call_method(capture_method)
    print(f"结果: {result}")
    
    # 启动运动检测
    print("启动运动检测...")
    result = camera_object.call_method(start_motion_method)
    print(f"结果: {result}")
    
    # 检查状态
    time.sleep(2)
    status = motion_status.get_value()
    print(f"运动检测状态: {status}")
    
    # 等待一段时间
    time.sleep(10)
    
    # 停止运动检测
    print("停止运动检测...")
    result = camera_object.call_method(stop_motion_method)
    print(f"结果: {result}")
    
finally:
    client.disconnect()
    print("已断开连接")