#!/usr/bin/python3

"""
OPC UA 树莓派摄像头控制器
修改自原始运动检测脚本，添加OPC UA功能
"""

import io
import subprocess
import os
import time
from datetime import datetime
from PIL import Image
import numpy as np
import cv2
import signal
import sys
import threading
import logging

# OPC UA imports
from opcua import Server, ua
from opcua.common.callback import CallbackType

# 设置环境变量
os.environ["QT_QPA_PLATFORM"] = "xcb"

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CameraController:
    def __init__(self):
        # 摄像头设置
        self.camera = None
        self.is_running = False
        self.capture_thread = None
        
        # 原始设置
        self.threshold = 20
        self.sensitivity = 5
        self.forceCapture = True
        self.forceCaptureTime = 60 * 60
        self.filepath = "/home/pe/Downloads/Ann Machine/Data/databin"
        self.filenamePrefix = "capture"
        self.diskSpaceToReserve = 40 * 1024 * 1024
        
        # 图片设置
        self.saveWidth = 1296
        self.saveHeight = 972
        self.saveQuality = 100
        
        # 检测区域设置
        self.testAreaCount = 1
        center_x = 1296 // 2
        center_y = 972 // 2
        half_width = 200 // 2
        half_height = 150 // 2
        self.testBorders = [[[center_x - half_width + 1, center_x + half_width],
                            [center_y - half_height + 1, center_y + half_height]]]
        
        # 运动检测状态
        self.motion_detection_enabled = False
        self.last_capture = time.time()
        self.last_capture_time = 0
        self.capture_interval = 0
        
        # 确保目录存在
        self.ensure_directory_exists(self.filepath)
        
    def ensure_directory_exists(self, directory):
        if not os.path.exists(directory):
            logger.info(f"目录 {directory} 不存在，正在创建...")
            os.makedirs(directory)
    
    def init_camera(self):
        """初始化摄像头"""
        try:
            self.camera = cv2.VideoCapture(0)
            if not self.camera.isOpened():
                logger.error("错误：无法访问摄像头")
                return False
            
            # 设置摄像头参数
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.saveWidth)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.saveHeight)
            self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            
            logger.info("摄像头初始化成功")
            return True
        except Exception as e:
            logger.error(f"摄像头初始化失败: {e}")
            return False
    
    def capture_single_image(self):
        """捕捉单张图片"""
        if not self.camera or not self.camera.isOpened():
            if not self.init_camera():
                return False, "摄像头初始化失败"
        
        try:
            ret, frame = self.camera.read()
            if not ret:
                return False, "无法捕捉图片"
            
            frame = cv2.flip(frame, 0)  # 垂直翻转
            filename = self.save_image(frame)
            return True, f"图片已保存: {filename}"
        except Exception as e:
            logger.error(f"捕捉图片时出错: {e}")
            return False, str(e)
    
    def save_image(self, image):
        """保存图片到磁盘"""
        self.keep_disk_space_free(self.diskSpaceToReserve)
        time_now = datetime.now()
        filename = os.path.join(
            self.filepath, 
            f"{self.filenamePrefix}-%04d%02d%02d-%02d%02d%02d.jpg" % 
            (time_now.day, time_now.month, time_now.year, 
             time_now.hour, time_now.minute, time_now.second)
        )
        
        # 转换BGR到RGB
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        im = Image.fromarray(image_rgb)
        im.save(filename, quality=self.saveQuality)
        logger.info(f"已捕捉 {filename}")
        return filename
    
    def keep_disk_space_free(self, bytes_to_reserve):
        """保持磁盘空间充足"""
        if self.get_free_space() < bytes_to_reserve:
            for filename in sorted(os.listdir(self.filepath + "/")):
                if filename.startswith(self.filenamePrefix) and filename.endswith(".jpg"):
                    os.remove(self.filepath + "/" + filename)
                    logger.info(f"删除 {self.filepath}/{filename} 以避免磁盘空间不足")
                    if self.get_free_space() > bytes_to_reserve:
                        return
    
    def get_free_space(self):
        """获取可用磁盘空间"""
        st = os.statvfs(self.filepath + "/")
        return st.f_bavail * st.f_frsize
    
    def start_motion_detection(self):
        """启动运动检测"""
        if self.is_running:
            return False, "运动检测已在运行"
        
        if not self.init_camera():
            return False, "摄像头初始化失败"
        
        self.is_running = True
        self.motion_detection_enabled = True
        self.capture_thread = threading.Thread(target=self._motion_detection_loop)
        self.capture_thread.daemon = True
        self.capture_thread.start()
        
        logger.info("运动检测已启动")
        return True, "运动检测已启动"
    
    def stop_motion_detection(self):
        """停止运动检测"""
        self.is_running = False
        self.motion_detection_enabled = False
        
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=5)
        
        if self.camera:
            self.camera.release()
        
        logger.info("运动检测已停止")
        return True, "运动检测已停止"
    
    def _motion_detection_loop(self):
        """运动检测主循环"""
        try:
            # 获取第一帧
            ret, image1 = self.camera.read()
            if not ret:
                logger.error("无法捕捉初始图像")
                return
            
            image1 = cv2.flip(image1, 0)
            
            while self.is_running and self.motion_detection_enabled:
                ret, image2 = self.camera.read()
                if not ret:
                    logger.error("无法捕捉帧")
                    break
                
                image2 = cv2.flip(image2, 0)
                
                # 运动检测逻辑
                changed_pixels = 0
                take_picture = False
                
                for z in range(self.testAreaCount):
                    x_start = self.testBorders[z][0][0] - 1
                    x_end = self.testBorders[z][0][1]
                    y_start = self.testBorders[z][1][0] - 1
                    y_end = self.testBorders[z][1][1]
                    
                    for x in range(x_start, x_end):
                        for y in range(y_start, y_end):
                            pixdiff = abs(int(image1[y, x][1]) - int(image2[y, x][1]))
                            if pixdiff > self.threshold:
                                changed_pixels += 1
                            
                            if changed_pixels > self.sensitivity:
                                current_time = time.time()
                                if current_time - self.last_capture_time >= self.capture_interval:
                                    take_picture = True
                                    self.last_capture_time = current_time
                                break
                        if take_picture:
                            break
                    if take_picture:
                        break
                
                # 强制捕捉检查
                if self.forceCapture and (time.time() - self.last_capture > self.forceCaptureTime):
                    take_picture = True
                
                if take_picture:
                    self.last_capture = time.time()
                    self.save_image(image2)
                
                # 更新参考图像
                image1 = image2.copy()
                
                time.sleep(0.1)  # 小延迟避免CPU过载
                
        except Exception as e:
            logger.error(f"运动检测循环中出错: {e}")
        finally:
            if self.camera:
                self.camera.release()


class OPCUAServer:
    def __init__(self, camera_controller):
        self.camera_controller = camera_controller
        self.server = None
        
    def setup_server(self):
        """设置OPC UA服务器"""
        try:
            # 创建服务器
            self.server = Server()
            self.server.set_endpoint("opc.tcp://0.0.0.0:4840/freeopcua/server/")
            self.server.set_server_name("树莓派摄像头OPC UA服务器")
            
            # 设置安全策略
            self.server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
            
            # 创建命名空间
            uri = "http://raspberrypi.camera.opcua"
            idx = self.server.register_namespace(uri)
            
            # 创建对象节点
            camera_object = self.server.nodes.objects.add_object(idx, "CameraController")
            
            # 创建方法节点
            capture_method = camera_object.add_method(
                idx, "CaptureImage", self._capture_image_callback, [], [ua.VariantType.String]
            )
            
            start_motion_method = camera_object.add_method(
                idx, "StartMotionDetection", self._start_motion_callback, [], [ua.VariantType.String]
            )
            
            stop_motion_method = camera_object.add_method(
                idx, "StopMotionDetection", self._stop_motion_callback, [], [ua.VariantType.String]
            )
            
            # 创建状态变量
            self.motion_status_var = camera_object.add_variable(
                idx, "MotionDetectionStatus", False
            )
            self.motion_status_var.set_writable()
            
            self.last_image_var = camera_object.add_variable(
                idx, "LastImagePath", ""
            )
            
            # 创建设置变量
            self.threshold_var = camera_object.add_variable(
                idx, "Threshold", self.camera_controller.threshold
            )
            self.threshold_var.set_writable()
            
            self.sensitivity_var = camera_object.add_variable(
                idx, "Sensitivity", self.camera_controller.sensitivity
            )
            self.sensitivity_var.set_writable()
            
            logger.info("OPC UA服务器设置完成")
            return True
            
        except Exception as e:
            logger.error(f"设置OPC UA服务器失败: {e}")
            return False
    
    def _capture_image_callback(self, parent):
        """捕捉图片的回调函数"""
        success, message = self.camera_controller.capture_single_image()
        if success:
            self.last_image_var.set_value(message)
        return [ua.Variant(message, ua.VariantType.String)]
    
    def _start_motion_callback(self, parent):
        """启动运动检测的回调函数"""
        success, message = self.camera_controller.start_motion_detection()
        self.motion_status_var.set_value(success)
        return [ua.Variant(message, ua.VariantType.String)]
    
    def _stop_motion_callback(self, parent):
        """停止运动检测的回调函数"""
        success, message = self.camera_controller.stop_motion_detection()
        self.motion_status_var.set_value(False)
        return [ua.Variant(message, ua.VariantType.String)]
    
    def start_server(self):
        """启动服务器"""
        try:
            self.server.start()
            logger.info("OPC UA服务器已启动，端点: opc.tcp://0.0.0.0:4840/freeopcua/server/")
            return True
        except Exception as e:
            logger.error(f"启动OPC UA服务器失败: {e}")
            return False
    
    def stop_server(self):
        """停止服务器"""
        if self.server:
            self.server.stop()
            logger.info("OPC UA服务器已停止")


def signal_handler(sig, frame):
    """信号处理器"""
    logger.info("正在清理资源...")
    if 'opcua_server' in globals():
        opcua_server.stop_server()
    if 'camera_ctrl' in globals():
        camera_ctrl.stop_motion_detection()
    sys.exit(0)


if __name__ == "__main__":
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # 创建摄像头控制器
        camera_ctrl = CameraController()
        
        # 创建OPC UA服务器
        opcua_server = OPCUAServer(camera_ctrl)
        
        # 设置并启动服务器
        if opcua_server.setup_server():
            if opcua_server.start_server():
                logger.info("服务器运行中... 按 Ctrl+C 停止")
                
                try:
                    while True:
                        time.sleep(1)
                        # 更新状态变量
                        opcua_server.motion_status_var.set_value(camera_ctrl.motion_detection_enabled)
                        
                        # 同步设置变量
                        camera_ctrl.threshold = opcua_server.threshold_var.get_value()
                        camera_ctrl.sensitivity = opcua_server.sensitivity_var.get_value()
                        
                except KeyboardInterrupt:
                    logger.info("接收到中断信号")
            else:
                logger.error("无法启动OPC UA服务器")
        else:
            logger.error("无法设置OPC UA服务器")
            
    except Exception as e:
        logger.error(f"主程序出错: {e}")
    finally:
        # 清理资源
        if 'opcua_server' in locals():
            opcua_server.stop_server()
        if 'camera_ctrl' in locals():
            camera_ctrl.stop_motion_detection()
