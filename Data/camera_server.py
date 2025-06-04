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
# from opcua.common.callback import CallbackType # CallbackType 未在此代码中使用

# 设置环境变量 (如果你的树莓派需要，通常用于无头运行时避免Qt错误)
# os.environ["QT_QPA_PLATFORM"] = "xcb" # 如果你通过SSH运行且没有X服务器，可能需要，否则可以注释掉

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CameraController:
    def __init__(self):
        # 摄像头设置
        self.camera = None
        self.is_motion_detection_running = False # 明确表示运动检测线程的状态
        self.capture_thread = None

        # 运动检测参数
        self.threshold = 30  # 像素差异阈值 (0-255)，越小越敏感
        self.sensitivity = 20 # 变化像素点数量阈值，越小越敏感
        self.forceCapture = True
        self.forceCaptureTime = 60 * 60  # 每小时强制捕获一次
        self.filepath = "/home/pe/Downloads/Ann Machine/Data/databin" # <<<--- 修改为你自己的路径
        self.filenamePrefix = "capture"
        self.diskSpaceToReserve = 40 * 1024 * 1024 # 40MB

        # 图片设置
        self.saveWidth = 1296
        self.saveHeight = 972
        self.saveQuality = 90 # JPG质量 (0-100)

        # 检测区域设置 (示例: 图像中心 200x150 区域)
        self.testAreaCount = 1
        center_x = self.saveWidth // 2
        center_y = self.saveHeight // 2
        half_width = 200 // 2
        half_height = 150 // 2
        self.testBorders = [[[center_x - half_width, center_x + half_width -1],  # 确保索引起始为0，且在范围内
                            [center_y - half_height, center_y + half_height -1]]]

        # 运动检测状态
        self.last_motion_capture_time = 0 # 用于运动检测的捕获间隔
        self.capture_interval = 5 # 运动检测到后，至少间隔5秒再拍下一张

        self.last_force_capture_timestamp = time.time() # 用于强制捕获计时

        self.ensure_directory_exists(self.filepath)

    def ensure_directory_exists(self, directory):
        if not os.path.exists(directory):
            logger.info(f"目录 {directory} 不存在，正在创建...")
            os.makedirs(directory, exist_ok=True)

    def _open_camera(self):
        """尝试打开并配置摄像头，返回True/False"""
        if self.camera is not None and self.camera.isOpened():
            logger.info("摄像头已打开。")
            return True
        try:
            logger.info("尝试打开摄像头 cv2.VideoCapture(0)...")
            self.camera = cv2.VideoCapture(0) # 尝试使用默认摄像头
            if not self.camera.isOpened():
                # 尝试备用索引，有时摄像头可能不是0
                logger.warning("摄像头 0 打开失败，尝试摄像头 1...")
                self.camera = cv2.VideoCapture(1)
                if not self.camera.isOpened():
                    logger.error("错误：无法访问任何摄像头 (尝试了0和1)")
                    self.camera = None
                    return False

            # 设置摄像头参数
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.saveWidth)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.saveHeight)
            # self.camera.set(cv2.CAP_PROP_FPS, 10) # 可以尝试设置FPS
            # self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG')) # 有些摄像头不支持，可能导致问题

            # 读取一帧检查实际分辨率
            ret, frame = self.camera.read()
            if ret:
                h, w = frame.shape[:2]
                logger.info(f"摄像头初始化成功。请求分辨率: {self.saveWidth}x{self.saveHeight}, 实际获取: {w}x{h}")
                # 如果需要，可以基于实际分辨率调整 testBorders
            else:
                logger.warning("摄像头打开但无法读取初始帧。")
                # 不立即返回False，让后续操作尝试

            return True
        except Exception as e:
            logger.error(f"摄像头初始化过程中发生异常: {e}", exc_info=True)
            if self.camera:
                self.camera.release()
            self.camera = None
            return False

    def _release_camera(self):
        """释放摄像头资源"""
        if self.camera is not None and self.camera.isOpened():
            logger.info("释放摄像头资源。")
            self.camera.release()
        self.camera = None

    def capture_single_image(self):
        """捕捉单张图片"""
        if self.is_motion_detection_running:
            return False, "运动检测正在运行，请先停止运动检测以进行单张捕获。"

        if not self._open_camera():
            return False, "摄像头初始化失败 (capture_single_image)"

        try:
            ret, frame = self.camera.read()
            if not ret:
                self._release_camera()
                return False, "无法从摄像头捕捉图片"

            # 图像处理，例如翻转 (如果需要)
            # frame = cv2.flip(frame, 0)  # 垂直翻转
            # frame = cv2.flip(frame, 1)  # 水平翻转
            # frame = cv2.flip(frame, -1) # 垂直和水平翻转

            filename = self._save_image(frame)
            logger.info(f"单张图片已保存: {filename}")
            self._release_camera() # 单次捕获后释放
            return True, filename # 返回文件名而不是带前缀的消息
        except Exception as e:
            logger.error(f"捕捉单张图片时出错: {e}", exc_info=True)
            self._release_camera()
            return False, f"捕捉图片错误: {str(e)}"

    def _save_image(self, image_bgr):
        """保存图片到磁盘"""
        self.keep_disk_space_free(self.diskSpaceToReserve)
        time_now = datetime.now()
        timestamp_str = time_now.strftime("%Y%m%d-%H%M%S")
        filename = os.path.join(
            self.filepath,
            f"{self.filenamePrefix}-{timestamp_str}.jpg"
        )

        # OpenCV的图像是BGR格式，PIL Image期望RGB
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(image_rgb)
        pil_image.save(filename, quality=self.saveQuality)
        # logger.info(f"图片已保存: {filename}") # capture_single_image 和 motion_detection_loop 会记录
        return filename

    def keep_disk_space_free(self, bytes_to_reserve):
        """保持磁盘空间充足"""
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
                    if self.get_free_space() > bytes_to_reserve:
                        return
        except Exception as e:
            logger.error(f"管理磁盘空间时出错: {e}")

    def get_free_space(self):
        """获取可用磁盘空间"""
        try:
            st = os.statvfs(self.filepath)
            return st.f_bavail * st.f_frsize
        except Exception as e:
            logger.error(f"获取磁盘空间失败: {e}")
            return self.diskSpaceToReserve * 2 # 出错时假设有足够空间，避免因此阻塞

    def start_motion_detection(self):
        if self.is_motion_detection_running:
            return False, "运动检测已在运行"

        # 确保摄像头能打开
        if not self._open_camera():
            return False, "摄像头初始化失败 (start_motion_detection)"

        self.is_motion_detection_running = True
        self.capture_thread = threading.Thread(target=self._motion_detection_loop, daemon=True)
        self.capture_thread.start()

        logger.info("运动检测已启动")
        return True, "运动检测已启动"

    def stop_motion_detection(self):
        if not self.is_motion_detection_running:
            return True, "运动检测本未运行" # 返回True表示操作目标达成

        logger.info("尝试停止运动检测...")
        self.is_motion_detection_running = False # 设置标志位，让循环自然退出

        if self.capture_thread and self.capture_thread.is_alive():
            logger.info("等待运动检测线程结束...")
            self.capture_thread.join(timeout=10) # 增加超时
            if self.capture_thread.is_alive():
                logger.warning("运动检测线程超时未结束! 摄像头可能未正确释放。")
                # 这种情况下，强制释放摄像头可能不是好主意，因为线程可能还在用它
            else:
                logger.info("运动检测线程已成功停止。")
        else:
            logger.info("运动检测线程未运行或已结束。")

        self.capture_thread = None
        # 摄像头应该在 _motion_detection_loop 的 finally 中释放
        # 此处不再主动释放，依赖循环的清理逻辑
        # self._release_camera() # 如果循环的finally没有正确执行，这里是后备

        logger.info("运动检测已停止")
        return True, "运动检测已停止"

    def _motion_detection_loop(self):
        """运动检测主循环"""
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

            # frame1_bgr = cv2.flip(frame1_bgr, 0) # 如果需要翻转
            gray1 = cv2.cvtColor(frame1_bgr, cv2.COLOR_BGR2GRAY)
            gray1 = cv2.GaussianBlur(gray1, (21, 21), 0) # 高斯模糊减少噪声

            self.last_force_capture_timestamp = time.time() # 重置强制捕获计时器

            while self.is_motion_detection_running:
                ret, frame2_bgr = self.camera.read()
                if not ret:
                    logger.warning("运动检测循环：无法捕捉后续帧，可能摄像头已断开。")
                    time.sleep(0.5) # 等待一下再尝试
                    continue

                # frame2_bgr = cv2.flip(frame2_bgr, 0) # 如果需要翻转
                gray2 = cv2.cvtColor(frame2_bgr, cv2.COLOR_BGR2GRAY)
                gray2 = cv2.GaussianBlur(gray2, (21, 21), 0)

                # 计算差异
                frame_delta = cv2.absdiff(gray1, gray2)
                thresh_img = cv2.threshold(frame_delta, self.threshold, 255, cv2.THRESH_BINARY)[1]

                # 膨胀处理，填充孔洞
                thresh_img = cv2.dilate(thresh_img, None, iterations=2)

                # 查找轮廓
                contours, _ = cv2.findContours(thresh_img.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                motion_detected_in_roi = False
                if contours:
                    # 检查是否有轮廓与定义的ROI重叠或在ROI内
                    # 简化的方法：如果任何轮廓足够大，则认为检测到运动
                    # 或者，更精确地检查轮廓是否在 self.testBorders 定义的区域内
                    significant_contour_found = False
                    for contour in contours:
                        if cv2.contourArea(contour) < self.sensitivity : # sensitivity 现在用作最小轮廓面积
                            continue
                        significant_contour_found = True
                        # (x, y, w, h) = cv2.boundingRect(contour)
                        # 检查 (x,y,w,h) 是否在 testBorders 内 (更复杂的逻辑)
                        break # 找到一个显著轮廓即可

                    if significant_contour_found:
                        current_time = time.time()
                        if current_time - self.last_motion_capture_time >= self.capture_interval:
                            motion_detected_in_roi = True
                            self.last_motion_capture_time = current_time
                            logger.info("运动检测到!")


                # 强制捕获检查
                take_picture_now = motion_detected_in_roi
                if not take_picture_now and self.forceCapture and \
                   (time.time() - self.last_force_capture_timestamp > self.forceCaptureTime):
                    take_picture_now = True
                    logger.info("强制捕获触发。")
                    self.last_force_capture_timestamp = time.time() # 重置计时器

                if take_picture_now:
                    logger.info("正在保存运动检测/强制捕获的图片...")
                    filename = self._save_image(frame2_bgr) # 保存原始彩色帧
                    logger.info(f"图片已保存: {filename}")


                gray1 = gray2 # 更新参考帧
                time.sleep(0.1) # 避免CPU过载，可以调整

        except cv2.error as e:
            logger.error(f"OpenCV 错误在运动检测循环中: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"运动检测循环中发生未知错误: {e}", exc_info=True)
        finally:
            logger.info("运动检测循环结束。")
            self._release_camera() # 确保摄像头在循环结束时释放
            self.is_motion_detection_running = False # 确保状态更新
            logger.info("摄像头已在运动检测循环的finally块中释放。")


class OPCUAServer:
    def __init__(self, camera_controller):
        self.camera_controller = camera_controller
        self.server = None
        self.idx = 0 # Namespace index

    def setup_server(self):
        try:
            self.server = Server()
            self.server.set_endpoint("opc.tcp://0.0.0.0:4840/freeopcua/server/")
            self.server.set_server_name("树莓派摄像头OPC UA服务器")
            self.server.set_security_policy([ua.SecurityPolicyType.NoSecurity]) # 无安全策略，方便测试

            uri = "http://raspberrypi.camera.opcua"
            self.idx = self.server.register_namespace(uri)

            objects_node = self.server.get_objects_node()
            camera_object = objects_node.add_object(self.idx, "CameraController")

            # --- 方法节点 ---
            capture_method_node = camera_object.add_method(
                self.idx, "CaptureImage", self._capture_image_callback, [], [ua.VariantType.String]
            )
            start_motion_method_node = camera_object.add_method(
                self.idx, "StartMotionDetection", self._start_motion_callback, [], [ua.VariantType.String]
            )
            stop_motion_method_node = camera_object.add_method(
                self.idx, "StopMotionDetection", self._stop_motion_callback, [], [ua.VariantType.String]
            )

            # --- 可读状态变量 ---
            self.motion_status_var = camera_object.add_variable(
                self.idx, "MotionDetectionStatus", False # 初始为False
            )
            self.motion_status_var.set_writable(False) # 通常状态变量是只读的

            self.last_image_path_var = camera_object.add_variable(
                self.idx, "LastImagePath", ""
            )
            self.last_image_path_var.set_writable(False)

            # --- 可写参数变量 ---
            self.threshold_var = camera_object.add_variable(
                self.idx, "Threshold", self.camera_controller.threshold # 初始值来自控制器
            )
            self.threshold_var.set_writable(True)
            self.threshold_var.add_data_change_callback(self._threshold_changed_callback)

            self.sensitivity_var = camera_object.add_variable(
                self.idx, "Sensitivity", self.camera_controller.sensitivity
            )
            self.sensitivity_var.set_writable(True)
            self.sensitivity_var.add_data_change_callback(self._sensitivity_changed_callback)

            self.capture_interval_var = camera_object.add_variable(
                self.idx, "MotionCaptureInterval", self.camera_controller.capture_interval
            )
            self.capture_interval_var.set_writable(True)
            self.capture_interval_var.add_data_change_callback(self._capture_interval_changed_callback)


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
        else:
            return [ua.Variant(f"拍照失败: {message_or_path}", ua.VariantType.String)]

    def _start_motion_callback(self, parent_nodeid, method_nodeid):
        logger.info("OPC UA: 调用 StartMotionDetection")
        success, message = self.camera_controller.start_motion_detection()
        # 状态变量的更新将在主循环中进行
        return [ua.Variant(message, ua.VariantType.String)]

    def _stop_motion_callback(self, parent_nodeid, method_nodeid):
        logger.info("OPC UA: 调用 StopMotionDetection")
        success, message = self.camera_controller.stop_motion_detection()
        # 状态变量的更新将在主循环中进行
        return [ua.Variant(message, ua.VariantType.String)]

    # --- 回调函数处理参数变化 ---
    @staticmethod
    def _threshold_changed_callback(node, val, data):
        logger.info(f"OPC UA: Threshold 变量被客户端修改为: {val}")
        # 注意: data.handle 是服务器对象，而不是 CameraController
        # 我们将在主循环中同步这些值到 CameraController
        # 或者，如果 OPCUAServer 实例可访问，可以直接修改：
        # opcua_server_instance.camera_controller.threshold = val
        # 但主循环同步更简单
        return ua.StatusCode(0) # Good

    @staticmethod
    def _sensitivity_changed_callback(node, val, data):
        logger.info(f"OPC UA: Sensitivity 变量被客户端修改为: {val}")
        return ua.StatusCode(0) # Good

    @staticmethod
    def _capture_interval_changed_callback(node, val, data):
        logger.info(f"OPC UA: MotionCaptureInterval 变量被客户端修改为: {val}")
        return ua.StatusCode(0) # Good

    def start_server(self):
        try:
            self.server.start()
            logger.info(f"OPC UA服务器已启动，端点: {self.server.endpoint}")
            return True
        except Exception as e:
            logger.error(f"启动OPC UA服务器失败: {e}", exc_info=True)
            return False

    def stop_server(self):
        if self.server:
            logger.info("正在停止OPC UA服务器...")
            self.server.stop()
            logger.info("OPC UA服务器已停止")

# 全局变量，用于信号处理
camera_ctrl_global = None
opcua_server_global = None

def signal_handler(sig, frame):
    logger.info("接收到中断信号 (Ctrl+C)，正在清理资源...")
    if opcua_server_global is not None:
        opcua_server_global.stop_server()
    if camera_ctrl_global is not None:
        # 确保运动检测先停止，它会释放摄像头
        logger.info("信号处理：停止运动检测...")
        camera_ctrl_global.stop_motion_detection()
        # 如果单次捕获后摄像头未释放，这里可以再尝试释放
        # logger.info("信号处理：确保摄像头释放...")
        # camera_ctrl_global._release_camera()
    logger.info("清理完成，退出。")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        camera_ctrl = CameraController()
        camera_ctrl_global = camera_ctrl # 赋值给全局变量

        opcua_server = OPCUAServer(camera_ctrl)
        opcua_server_global = opcua_server # 赋值给全局变量

        if opcua_server.setup_server():
            if opcua_server.start_server():
                logger.info("服务器运行中... 按 Ctrl+C 停止。")
                try:
                    while True:
                        # --- 主循环任务 ---
                        # 1. 更新OPC UA状态变量 (从控制器 -> OPC UA)
                        opcua_server.motion_status_var.set_value(camera_ctrl.is_motion_detection_running)
                        # (LastImagePath 由回调更新)

                        # 2. 同步OPC UA可写参数到控制器 (从OPC UA -> 控制器)
                        #    这些值可能由客户端通过OPC UA写入
                        new_threshold = opcua_server.threshold_var.get_value()
                        if camera_ctrl.threshold != new_threshold:
                            logger.info(f"主循环：同步 Threshold 从 {camera_ctrl.threshold} 到 {new_threshold}")
                            camera_ctrl.threshold = new_threshold

                        new_sensitivity = opcua_server.sensitivity_var.get_value()
                        if camera_ctrl.sensitivity != new_sensitivity:
                            logger.info(f"主循环：同步 Sensitivity 从 {camera_ctrl.sensitivity} 到 {new_sensitivity}")
                            camera_ctrl.sensitivity = new_sensitivity
                        
                        new_interval = opcua_server.capture_interval_var.get_value()
                        if camera_ctrl.capture_interval != new_interval:
                            logger.info(f"主循环：同步 MotionCaptureInterval 从 {camera_ctrl.capture_interval} 到 {new_interval}")
                            camera_ctrl.capture_interval = new_interval

                        time.sleep(1) # 主循环更新频率

                except KeyboardInterrupt:
                    logger.info("主循环接收到KeyboardInterrupt (这不应该发生，信号处理器会处理)。")
                except Exception as loop_e:
                    logger.error(f"主服务器循环中发生意外错误: {loop_e}", exc_info=True)
            else:
                logger.error("无法启动OPC UA服务器。")
        else:
            logger.error("无法设置OPC UA服务器。")

    except Exception as e:
        logger.error(f"主程序启动时出错: {e}", exc_info=True)
    finally:
        logger.info("程序即将退出，执行最终清理...")
        if 'opcua_server' in locals() and opcua_server is not None and opcua_server.server is not None : # 确保opcua_server已定义
            opcua_server.stop_server()
        if 'camera_ctrl' in locals() and camera_ctrl is not None : # 确保camera_ctrl已定义
            camera_ctrl.stop_motion_detection() # 这会处理摄像头释放
        logger.info("最终清理完成。")
