#!/usr/bin/python

# Modified camera capture script with OPC UA integration
# Original motion detection script improved with OPC UA remote control capability

import io
import subprocess
import os
import time
import asyncio
from datetime import datetime
from PIL import Image
import numpy as np
import cv2
from asyncua import Server, ua
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

os.environ["QT_QPA_PLATFORM"] = "xcb"  # Fix Wayland warning

########################################################################################################################################
# Camera and capture settings
########################################################################################################################################

threshold = 20
sensitivity = 5
forceCapture = True
forceCaptureTime = 60 * 60  # Once an hour
filepath = "/home/pe/Downloads/Ann Machine/Data/databin"
filenamePrefix = "capture"
diskSpaceToReserve = 40 * 1024 * 1024  # Keep 40 mb free on disk

# Settings of the photos to save
saveWidth = 1296
saveHeight = 972
saveQuality = 100

# Detection area settings
testAreaCount = 1
center_x = 1296 // 2
center_y = 972 // 2
half_width = 200 // 2
half_height = 150 // 2

testBorders = [[[center_x - half_width + 1, center_x + half_width],
                [center_y - half_height + 1, center_y + half_height]]]

debugMode = False

########################################################################################################################################
# OPC UA Server Configuration
########################################################################################################################################

OPC_UA_ENDPOINT = "opc.tcp://0.0.0.0:4840/camera/server/"
NAMESPACE_URI = "http://camera.opcua.server"

class CameraOPCUAServer:
    def __init__(self):
        self.server = None
        self.camera = None
        self.namespace_idx = None
        self.capture_trigger = None
        self.motion_detection_enabled = None
        self.camera_status = None
        self.last_capture_time = None
        self.capture_count = None
        self.motion_sensitivity = None
        self.capture_interval = None
        
        # Camera state
        self.is_capturing = False
        self.motion_enabled = True
        self.last_capture = time.time()
        self.image1 = None
        self.capture_counter = 0
        self.last_capture_timestamp = 0
        self.current_interval = 0  # seconds between captures
        
    async def init_server(self):
        """Initialize OPC UA server"""
        self.server = Server()
        await self.server.init()
        
        # Set server endpoint
        self.server.set_endpoint(OPC_UA_ENDPOINT)
        self.server.set_server_name("Camera Control Server")
        
        # Register namespace
        self.namespace_idx = await self.server.register_namespace(NAMESPACE_URI)
        
        # Create object for camera control
        camera_object = await self.server.nodes.objects.add_object(
            self.namespace_idx, "CameraController"
        )
        
        # Add control variables
        self.capture_trigger = await camera_object.add_variable(
            self.namespace_idx, "CaptureTrigger", False
        )
        await self.capture_trigger.set_writable()
        
        self.motion_detection_enabled = await camera_object.add_variable(
            self.namespace_idx, "MotionDetectionEnabled", True
        )
        await self.motion_detection_enabled.set_writable()
        
        self.camera_status = await camera_object.add_variable(
            self.namespace_idx, "CameraStatus", "Initializing"
        )
        
        self.last_capture_time = await camera_object.add_variable(
            self.namespace_idx, "LastCaptureTime", ""
        )
        
        self.capture_count = await camera_object.add_variable(
            self.namespace_idx, "CaptureCount", 0
        )
        
        self.motion_sensitivity = await camera_object.add_variable(
            self.namespace_idx, "MotionSensitivity", float(sensitivity)
        )
        await self.motion_sensitivity.set_writable()
        
        self.capture_interval = await camera_object.add_variable(
            self.namespace_idx, "CaptureInterval", 0.0
        )
        await self.capture_interval.set_writable()
        
        # Add methods
        capture_method = await camera_object.add_method(
            self.namespace_idx, "CapturePhoto", self.capture_photo_method
        )
        
        logger.info(f"OPC UA Server initialized at {OPC_UA_ENDPOINT}")
        
    async def capture_photo_method(self, parent):
        """OPC UA method to trigger photo capture"""
        if self.camera is not None and self.camera.isOpened():
            ret, frame = self.camera.read()
            if ret:
                frame = cv2.flip(frame, 0)
                await self.save_image_async(frame)
                return [ua.Variant(True, ua.VariantType.Boolean)]
        return [ua.Variant(False, ua.VariantType.Boolean)]
        
    def init_camera(self):
        """Initialize camera"""
        self.camera = cv2.VideoCapture(0)
        if not self.camera.isOpened():
            logger.error("Error: Camera not accessible.")
            return False
            
        # Set camera resolution
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1296)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 972)
        self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        
        # Get first frame
        ret, self.image1 = self.camera.read()
        if not ret:
            logger.error("Error: Unable to capture initial image.")
            return False
            
        self.image1 = cv2.flip(self.image1, 0)
        logger.info("Camera initialized successfully")
        return True
        
    async def save_image_async(self, image):
        """Save image asynchronously"""
        await asyncio.get_event_loop().run_in_executor(
            None, self.save_image, image, saveQuality, diskSpaceToReserve
        )
        
    def save_image(self, image, quality, diskSpaceToReserve):
        """Save a full-size image to disk"""
        self.keep_disk_space_free(diskSpaceToReserve)
        time_now = datetime.now()
        filename = os.path.join(
            filepath, 
            f"{filenamePrefix}-%04d%02d%02d-%02d%02d%02d.jpg" % (
                time_now.day, time_now.month, time_now.year, 
                time_now.hour, time_now.minute, time_now.second
            )
        )
        
        # Convert BGR (OpenCV) to RGB (PIL)
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        im = Image.fromarray(image_rgb)
        im.save(filename, quality=quality)
        
        self.capture_counter += 1
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        logger.info(f"Captured {filename}")
        return filename, timestamp
        
    def keep_disk_space_free(self, bytesToReserve):
        """Keep free space above given level"""
        if (self.get_free_space() < bytesToReserve):
            for filename in sorted(os.listdir(filepath + "/")):
                if filename.startswith(filenamePrefix) and filename.endswith(".jpg"):
                    os.remove(filepath + "/" + filename)
                    logger.info("Deleted %s/%s to avoid filling disk" % (filepath, filename))
                    if (self.get_free_space() > bytesToReserve):
                        return
                        
    def get_free_space(self):
        """Get available disk space"""
        st = os.statvfs(filepath + "/")
        du = st.f_bavail * st.f_frsize
        return du
        
    def ensure_directory_exists(self, directory):
        """Ensure the directory exists before saving files"""
        if not os.path.exists(directory):
            logger.info(f"Directory {directory} does not exist, creating it...")
            os.makedirs(directory)
            
    def detect_motion(self, image1, image2):
        """Detect motion between two frames"""
        if image1 is None or image2 is None:
            return False, 0
            
        if len(image1.shape) != 3 or len(image2.shape) != 3:
            return False, 0
            
        changedPixels = 0
        current_sensitivity = sensitivity  # Will be updated from OPC UA
        
        for z in range(testAreaCount):
            x_start = testBorders[z][0][0] - 1
            x_end = testBorders[z][0][1]
            y_start = testBorders[z][1][0] - 1
            y_end = testBorders[z][1][1]
            
            for x in range(x_start, x_end):
                for y in range(y_start, y_end):
                    # Access green channel (index 1) of BGR image
                    pixdiff = abs(int(image1[y, x][1]) - int(image2[y, x][1]))
                    if pixdiff > threshold:
                        changedPixels += 1
                    if changedPixels > current_sensitivity:
                        return True, changedPixels
                        
        return False, changedPixels
        
    async def camera_loop(self):
        """Main camera processing loop"""
        cv2.namedWindow("Camera Feed", cv2.WINDOW_NORMAL)
        
        while True:
            try:
                # Read OPC UA variables
                motion_enabled = await self.motion_detection_enabled.read_value()
                trigger_capture = await self.capture_trigger.read_value()
                current_sensitivity = await self.motion_sensitivity.read_value()
                interval = await self.capture_interval.read_value()
                
                # Update camera status
                await self.camera_status.write_value("Running")
                
                # Capture frame
                ret, image2 = self.camera.read()
                if not ret:
                    logger.error("Error: Unable to capture frame.")
                    await self.camera_status.write_value("Error - No Frame")
                    break
                    
                image2 = cv2.flip(image2, 0)
                takePicture = False
                changedPixels = 0
                
                # Check for manual trigger
                if trigger_capture:
                    takePicture = True
                    await self.capture_trigger.write_value(False)  # Reset trigger
                    logger.info("Manual capture triggered via OPC UA")
                
                # Motion detection (if enabled)
                elif motion_enabled:
                    motion_detected, changedPixels = self.detect_motion(self.image1, image2)
                    if motion_detected:
                        current_time = time.time()
                        if current_time - self.last_capture_timestamp >= interval:
                            takePicture = True
                            self.last_capture_timestamp = current_time
                            logger.info(f"Motion detected: {changedPixels} pixels changed")
                
                # Force capture (if enabled)
                if forceCapture and (time.time() - self.last_capture > forceCaptureTime):
                    takePicture = True
                    logger.info("Force capture triggered")
                
                # Take picture if needed
                if takePicture:
                    self.last_capture = time.time()
                    filename, timestamp = await asyncio.get_event_loop().run_in_executor(
                        None, self.save_image, image2, saveQuality, diskSpaceToReserve
                    )
                    
                    # Update OPC UA variables
                    await self.last_capture_time.write_value(timestamp)
                    await self.capture_count.write_value(self.capture_counter)
                
                # Update reference image
                self.image1 = image2.copy()
                
                # Draw detection areas
                for z in range(testAreaCount):
                    x_start = testBorders[z][0][0] - 1
                    x_end = testBorders[z][0][1]
                    y_start = testBorders[z][1][0] - 1
                    y_end = testBorders[z][1][1]
                    
                    # Draw rectangle
                    color = (0, 0, 255) if takePicture else (0, 255, 0)
                    cv2.rectangle(image2, (x_start, y_start), (x_end, y_end), color, 2)
                
                # Add info text
                info_text = f"Motion: {'ON' if motion_enabled else 'OFF'} | Captures: {self.capture_counter} | Changed: {changedPixels}"
                cv2.putText(image2, info_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                # Display frame
                cv2.imshow("Camera Feed", image2)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                    
                # Small delay to prevent overwhelming the CPU
                await asyncio.sleep(0.01)
                
            except Exception as e:
                logger.error(f"Error in camera loop: {e}")
                await self.camera_status.write_value(f"Error: {str(e)}")
                
        cv2.destroyAllWindows()
        
    async def start_server(self):
        """Start the OPC UA server and camera"""
        self.ensure_directory_exists(filepath)
        
        # Initialize camera
        if not self.init_camera():
            logger.error("Failed to initialize camera")
            return
            
        # Initialize OPC UA server
        await self.init_server()
        
        # Start server
        async with self.server:
            logger.info("OPC UA Camera Server started")
            await self.camera_status.write_value("Ready")
            
            # Start camera loop
            await self.camera_loop()
            
        # Cleanup
        if self.camera:
            self.camera.release()

async def main():
    """Main function"""
    logger.info("Starting OPC UA Camera Server...")
    
    camera_server = CameraOPCUAServer()
    try:
        await camera_server.start_server()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        logger.info("Server shutdown complete")


if __name__ == "__main__":
    print("Starting OPC UA Camera Control Server...")
    print(f"Server will be available at: {OPC_UA_ENDPOINT}")
    print("Press Ctrl+C to stop the server")
    
    asyncio.run(main())

########################################################################################################################################
# OPC UA Client Example Usage:
########################################################################################################################################

"""
使用示例 - OPC UA客户端控制代码:

from asyncua import Client
import asyncio

async def control_camera():
    client = Client("opc.tcp://localhost:4840/camera/server/")
    await client.connect()
    
    # 获取控制节点
    capture_trigger = await client.get_node("ns=2;s=CaptureTrigger")
    motion_enabled = await client.get_node("ns=2;s=MotionDetectionEnabled")
    sensitivity = await client.get_node("ns=2;s=MotionSensitivity")
    capture_count = await client.get_node("ns=2;s=CaptureCount")
    
    # 手动触发拍照
    await capture_trigger.write_value(True)
    print("拍照触发已发送")
    
    # 调整运动检测灵敏度
    await sensitivity.write_value(10.0)
    print("灵敏度已设置为10")
    
    # 禁用运动检测
    await motion_enabled.write_value(False)
    print("运动检测已禁用")
    
    # 读取拍照次数
    count = await capture_count.read_value()
    print(f"当前拍照次数: {count}")
    
    await client.disconnect()

# 运行客户端
asyncio.run(control_camera())
"""
