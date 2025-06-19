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

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CameraController:
    def __init__(self):
        # 摄像头设置
        self.camera = None
        self.is_motion_detection_running = False 
        self.capture_thread = None

        # 运动检测参数
        self.threshold = 30
        self.sensitivity = 20 # 在新逻辑中代表最小轮廓面积
        self.forceCapture = True
        self.forceCaptureTime = 60 * 60
        self.filepath = "/home/pe/Downloads/Ann Machine/Data/databin" # <<<--- 修改为你自己的路径
        self.filenamePrefix = "capture"
        self.diskSpaceToReserve = 40 * 1024 * 1024

        # 图片设置
        self.saveWidth = 1296
        self.saveHeight = 972
        self.saveQuality = 90

        # 检测区域设置
        self.testAreaCount = 1
        center_x = self.saveWidth // 2
        center_y = self.saveHeight // 2
        half_width = 200 // 2
        half_height = 150 // 2
        self.testBorders = [[[center_x - half_width, center_x + half_width -1],
                            [center_y - half_height, center_y + half_height -1]]]

        # 运动检测状态
        self.last_motion_capture_time = 0
        self.capture_interval = 5
        self.last_force_capture_timestamp = time.time()

        self.ensure_directory_exists(self.filepath)

    def ensure_directory_exists(self, directory):
        if not os.path.exists(directory):
            logger.info(f"目录 {directory} 不存在，正在创建...")
            os.makedirs(directory, exist_ok=True)

    def _open_camera(self):
        if self.camera is not None and self.camera.isOpened():
            return True
        try:
            logger.info("尝试打开摄像头 cv2.VideoCapture(0)...")
            self.camera = cv2.VideoCapture(0)
            if not self.camera.isOpened():
                logger.warning("摄像头 0 打开失败，尝试摄像头 1...")
                self.camera = cv2.VideoCapture(1)
                if not self.camera.isOpened():
                    logger.error("错误：无法访问任何摄像头 (尝试了0和1)")
                    self.camera = None
                    return False

            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.saveWidth)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.saveHeight)
            
            ret, frame = self.camera.read()
            if ret:
                h, w = frame.shape[:2]
                logger.info(f"摄像头初始化成功。请求分辨率: {self.saveWidth}x{self.saveHeight}, 实际获取: {w}x{h}")
            else:
                logger.warning("摄像头打开但无法读取初始帧。")
            return True
        except Exception as e:
            logger.error(f"摄像头初始化过程中发生异常: {e}", exc_info=True)
            if self.camera: self.camera.release()
            self.camera = None
            return False

    def _release_camera(self):
        if self.camera is not None and self.camera.isOpened():
            logger.info("释放摄像头资源。")
            self.camera.release()
        self.camera = None

    def capture_single_image(self):
        if self.is_motion_detection_running:
            return False, "运动检测正在运行，请先停止运动检测以进行单张捕获。"
        if not self._open_camera():
            return False, "摄像头初始化失败 (capture_single_image)"
        try:
            ret, frame = self.camera.read()
            if not ret:
                self._release_camera()
                return False, "无法从摄像头捕捉图片"
            filename = self._save_image(frame)
            logger.info(f"单张图片已保存: {filename}")
            self._release_camera()
            return True, filename
        except Exception as e:
            logger.error(f"捕捉单张图片时出错: {e}", exc_info=True)
            self._release_camera()
            return False, f"捕捉图片错误: {str(e)}"

    def _save_image(self, image_bgr):
        self.keep_disk_space_free(self.diskSpaceToReserve)
        time_now = datetime.now()
        timestamp_str = time_now.strftime("%Y%m%d-%H%M%S")
        filename = os.path.join(self.filepath, f"{self.filenamePrefix}-{timestamp_str}.jpg")
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(image_rgb)
        pil_image.save(filename, quality=self.saveQuality)
        return filename

    def keep_disk_space_free(self, bytes_to_reserve):
        try:
            if self.get_free_space() < bytes_to_reserve:
                logger.warning("磁盘空间不足，尝试删除旧文件...")
                files = sorted(
                    [os.path.join(self.filepath, f) for f in os.listdir(self.filepath)
                     if f.startswith(self.filenamePrefix) and f.endswith(".jpg")]
                )
                for file_to_delete in files:
                    os.remove(file_to_delete)
                    logger.info(f"已删除 {file_to_delete} 以释放空间。")
                    if self.get_free_space() > bytes_to_reserve: return
        except Exception as e: logger.error(f"管理磁盘空间时出错: {e}")

    def get_free_space(self):
        try:
            st = os.statvfs(self.filepath)
            return st.f_bavail * st.f_frsize
        except Exception as e:
            logger.error(f"获取磁盘空间失败: {e}")
            return self.diskSpaceToReserve * 2

    def start_motion_detection(self):
        if self.is_motion_detection_running: return False, "运动检测已在运行"
        if not self._open_camera(): return False, "摄像头初始化失败 (start_motion_detection)"
        self.is_motion_detection_running = True
        self.capture_thread = threading.Thread(target=self._motion_detection_loop, daemon=True)
        self.capture_thread.start()
        logger.info("运动检测已启动")
        return True, "运动检测已启动"

    def stop_motion_detection(self):
        if not self.is_motion_detection_running: return True, "运动检测本未运行"
        logger.info("尝试停止运动检测...")
        self.is_motion_detection_running = False
        if self.capture_thread and self.capture_thread.is_alive():
            logger.info("等待运动检测线程结束...")
            self.capture_thread.join(timeout=10)
            if self.capture_thread.is_alive(): logger.warning("运动检测线程超时未结束!")
            else: logger.info("运动检测线程已成功停止。")
        else: logger.info("运动检测线程未运行或已结束。")
        self.capture_thread = None
        logger.info("运动检测已停止")
        return True, "运动检测已停止"

    def _motion_detection_loop(self):
        if self.camera is None or not self.camera.isOpened():
            logger.error("运动检测循环：摄像头未初始化或未打开！")
            self.is_motion_detection_running = False
            return
        logger.info("运动检测循环启动...")
        try:
            ret, frame1_bgr = self.camera.read()
            if not ret:
                logger.error("运动检测循环：无法捕捉初始帧")
                self.is_motion_detection_running = False
                return
            gray1 = cv2.cvtColor(frame1_bgr, cv2.COLOR_BGR2GRAY)
            gray1 = cv2.GaussianBlur(gray1, (21, 21), 0)
            self.last_force_capture_timestamp = time.time()

            while self.is_motion_detection_running:
                ret, frame2_bgr = self.camera.read()
                if not ret:
                    logger.warning("运动检测循环：无法捕捉后续帧。")
                    time.sleep(0.5)
                    continue
                gray2 = cv2.cvtColor(frame2_bgr, cv2.COLOR_BGR2GRAY)
                gray2 = cv2.GaussianBlur(gray2, (21, 21), 0)
                frame_delta = cv2.absdiff(gray1, gray2)
                thresh_img = cv2.threshold(frame_delta, self.threshold, 255, cv2.THRESH_BINARY)[1]
                thresh_img = cv2.dilate(thresh_img, None, iterations=2)
                contours, _ = cv2.findContours(thresh_img.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                motion_detected_in_roi = False
                if contours:
                    significant_contour_found = False
                    for contour in contours:
                        if cv2.contourArea(contour) < self.sensitivity: continue
                        significant_contour_found = True
                        break
                    if significant_contour_found:
                        current_time = time.time()
                        if current_time - self.last_motion_capture_time >= self.capture_interval:
                            motion_detected_in_roi = True
                            self.last_motion_capture_time = current_time
                            logger.info("运动检测到!")
                take_picture_now = motion_detected_in_roi
                if not take_picture_now and self.forceCapture and \
                   (time.time() - self.last_force_capture_timestamp > self.forceCaptureTime):
                    take_picture_now = True
                    logger.info("强制捕获触发。")
                    self.last_force_capture_timestamp = time.time()
                if take_picture_now:
                    logger.info("正在保存运动检测/强制捕获的图片...")
                    filename = self._save_image(frame2_bgr)
                    logger.info(f"图片已保存: {filename}")
                gray1 = gray2
                time.sleep(0.1)
        except cv2.error as e: logger.error(f"OpenCV 错误在运动检测循环中: {e}", exc_info=True)
        except Exception as e: logger.error(f"运动检测循环中发生未知错误: {e}", exc_info=True)
        finally:
            logger.info("运动检测循环结束。")
            self._release_camera()
            self.is_motion_detection_running = False
            logger.info("摄像头已在运动检测循环的finally块中释放。")


class OPCUAServer:
    def __init__(self, camera_controller):
        self.camera_controller = camera_controller
        self.server = None
        self.idx = 0

    def setup_server(self):
        try:
            self.server = Server()
            self.server.set_endpoint("opc.tcp://0.0.0.0:4840/freeopcua/server/")
            self.server.set_server_name("树莓派摄像头OPC UA服务器")
            self.server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
            uri = "http://raspberrypi.camera.opcua"
            self.idx = self.server.register_namespace(uri)
            objects_node = self.server.get_objects_node()
            camera_object = objects_node.add_object(self.idx, "CameraController")

            camera_object.add_method(self.idx, "CaptureImage", self._capture_image_callback, [], [ua.VariantType.String])
            camera_object.add_method(self.idx, "StartMotionDetection", self._start_motion_callback, [], [ua.VariantType.String])
            camera_object.add_method(self.idx, "StopMotionDetection", self._stop_motion_callback, [], [ua.VariantType.String])

            self.motion_status_var = camera_object.add_variable(self.idx, "MotionDetectionStatus", False)
            self.motion_status_var.set_writable(False)
            self.last_image_path_var = camera_object.add_variable(self.idx, "LastImagePath", "")
            self.last_image_path_var.set_writable(False)

            self.threshold_var = camera_object.add_variable(self.idx, "Threshold", self.camera_controller.threshold)
            self.threshold_var.set_writable(True)
            self.threshold_var.set_value_callback(self._threshold_value_written_callback) # MODIFIED

            self.sensitivity_var = camera_object.add_variable(self.idx, "Sensitivity", self.camera_controller.sensitivity)
            self.sensitivity_var.set_writable(True)
            self.sensitivity_var.set_value_callback(self._sensitivity_value_written_callback) # MODIFIED

            self.capture_interval_var = camera_object.add_variable(self.idx, "MotionCaptureInterval", self.camera_controller.capture_interval)
            self.capture_interval_var.set_writable(True)
            self.capture_interval_var.set_value_callback(self._capture_interval_value_written_callback) # MODIFIED

            logger.info("OPC UA服务器设置完成。Namespace Index: %s", self.idx)
            return True
        except Exception as e:
            logger.error(f"设置OPC UA服务器失败: {e}", exc_info=True)
            return False

    def _capture_image_callback(self, parent_nodeid, method_nodeid):
        logger.info("OPC UA: 调用 CaptureImage")
        success, message_or_path = self.camera_controller.capture_single_image()
        if success:
            self.last_image_path_var.set_value(message_or_path)
            return [ua.Variant(f"图片已保存: {message_or_path}", ua.VariantType.String)]
        return [ua.Variant(f"拍照失败: {message_or_path}", ua.VariantType.String)]

    def _start_motion_callback(self, parent_nodeid, method_nodeid):
        logger.info("OPC UA: 调用 StartMotionDetection")
        success, message = self.camera_controller.start_motion_detection()
        return [ua.Variant(message, ua.VariantType.String)]

    def _stop_motion_callback(self, parent_nodeid, method_nodeid):
        logger.info("OPC UA: 调用 StopMotionDetection")
        success, message = self.camera_controller.stop_motion_detection()
        return [ua.Variant(message, ua.VariantType.String)]

    def _threshold_value_written_callback(self, node, ua_var): # MODIFIED
        val = ua_var.Value
        logger.info(f"OPC UA: Threshold 变量被客户端写入，新值为: {val}")
        if isinstance(val, (int, float)): self.camera_controller.threshold = val
        else: logger.warning(f"Threshold 接收到非预期类型的值: {type(val)}")
        return ua.StatusCode(0)

    def _sensitivity_value_written_callback(self, node, ua_var): # MODIFIED
        val = ua_var.Value
        logger.info(f"OPC UA: Sensitivity 变量被客户端写入，新值为: {val}")
        if isinstance(val, (int, float)): self.camera_controller.sensitivity = val
        else: logger.warning(f"Sensitivity 接收到非预期类型的值: {type(val)}")
        return ua.StatusCode(0)

    def _capture_interval_value_written_callback(self, node, ua_var): # MODIFIED
        val = ua_var.Value
        logger.info(f"OPC UA: MotionCaptureInterval 变量被客户端写入，新值为: {val}")
        if isinstance(val, (int, float)) and val >=0 : self.camera_controller.capture_interval = val
        else: logger.warning(f"MotionCaptureInterval 接收到非预期类型或无效值: {val} (类型: {type(val)})")
        return ua.StatusCode(0)

    def start_server(self):
        try:
            self.server.start()
            logger.info(f"OPC UA服务器已启动，端点: {self.server.endpoint}")
            return True
        except Exception as e:
            logger.error(f"启动OPC UA服务器失败: {e}", exc_info=True)
            return False

    def stop_server(self):
        if self.server is not None:
            logger.info("正在停止OPC UA服务器...")
            try:
                # Check if bserver exists and is not None, as per the error trace
                if hasattr(self.server, 'bserver') and self.server.bserver is not None:
                    self.server.stop()
                    logger.info("OPC UA服务器已停止")
                else:
                    logger.warning("OPC UA服务器对象存在，但其内部bserver可能未初始化或已停止，无法再次调用stop。")
            except Exception as e:
                logger.error(f"停止服务器时发生错误: {e}", exc_info=True)
        else:
            logger.info("OPC UA服务器对象未初始化，无需停止。")


camera_ctrl_global = None
opcua_server_global = None

def signal_handler(sig, frame):
    logger.info("接收到中断信号 (Ctrl+C)，正在清理资源...")
    if opcua_server_global is not None:
        opcua_server_global.stop_server()
    if camera_ctrl_global is not None:
        logger.info("信号处理：停止运动检测...")
        camera_ctrl_global.stop_motion_detection()
    logger.info("清理完成，退出。")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    opcua_setup_successful = False # Flag to track if server setup was okay
    try:
        camera_ctrl = CameraController()
        camera_ctrl_global = camera_ctrl

        opcua_server = OPCUAServer(camera_ctrl)
        opcua_server_global = opcua_server

        if opcua_server.setup_server():
            opcua_setup_successful = True # Mark setup as successful
            if opcua_server.start_server():
                logger.info("服务器运行中... 按 Ctrl+C 停止。")
                try:
                    while True:
                        opcua_server.motion_status_var.set_value(camera_ctrl.is_motion_detection_running)
                        # Parameters are now updated via set_value_callbacks, no need for polling here
                        time.sleep(1)
                except KeyboardInterrupt: logger.info("主循环接收到KeyboardInterrupt.")
                except Exception as loop_e: logger.error(f"主服务器循环中发生意外错误: {loop_e}", exc_info=True)
            else: logger.error("无法启动OPC UA服务器。")
        else: logger.error("无法设置OPC UA服务器。")
    except Exception as e:
        logger.error(f"主程序启动时出错: {e}", exc_info=True)
    finally:
        logger.info("程序即将退出，执行最终清理...")
        if opcua_server_global is not None and opcua_setup_successful: # Only stop if setup was okay
             opcua_server_global.stop_server()
        elif opcua_server_global is not None:
             logger.info("OPC UA 服务器设置未成功，可能无需停止或无法安全停止。")

        if camera_ctrl_global is not None:
            camera_ctrl_global.stop_motion_detection()
        logger.info("最终清理完成。")
