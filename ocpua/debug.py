#!/usr/bin/python

# original script by brainflakes, improved by pageauc, peewee2 and Kesthal
# improved by meow2 to run in libcamera/raspberrypi 4
# www.raspberrypi.org/phpBB3/viewtopic.php?f=43&t=45235

import io
import subprocess
import os
import time
from datetime import datetime
from PIL import Image
import numpy as np
import cv2  # Import OpenCV for displaying the camera feed

os.environ["QT_QPA_PLATFORM"] = "xcb"  # Fix Wayland warning

########################################################################################################################################
# Motion detection settings
########################################################################################################################################

threshold = 20
sensitivity = 5
forceCapture = True
forceCaptureTime = 60 * 60  # Once an hour
filepath = "/home/pe/Downloads/Ann Machine/Data/databin"
filenamePrefix = "capture"
diskSpaceToReserve = 40 * 1024 * 1024  # Keep 40 mb free on disk
cameraSettings = ""

# Settings of the photos to save
saveWidth = 1296
saveHeight = 972
saveQuality = 100  # Set jpeg quality (0 to 100)

# Test-Image settings
testAreaCount = 1
testWidth = 200
testHeight = 150

# Center detection box for 640x480 frame
center_x = 1296 // 2
center_y = 972 // 2
half_width = 200 // 2
half_height = 150 // 2

testBorders = [[[center_x - half_width + 1, center_x + half_width],
                [center_y - half_height + 1, center_y + half_height]]]

debugMode = False

# 新增：查找可用摄像头的函数
def find_available_camera():
    """尝试找到可用的摄像头设备"""
    print("正在查找可用的摄像头设备...")
    
    # 检查/dev/video*设备
    import glob
    video_devices = glob.glob('/dev/video*')
    print(f"发现的视频设备: {video_devices}")
    
    # 尝试不同的摄像头索引
    for i in range(10):  # 尝试索引 0-9
        print(f"尝试摄像头索引 {i}...")
        cap = cv2.VideoCapture(i)
        
        if cap is not None and cap.isOpened():
            # 尝试读取一帧来确认摄像头真的可用
            ret, frame = cap.read()
            if ret and frame is not None:
                print(f"成功找到可用摄像头，索引: {i}")
                cap.release()
                return i
            else:
                print(f"摄像头索引 {i} 打开了但无法读取图像")
        
        cap.release()
    
    # 如果标准方法失败，尝试使用不同的后端
    backends = [
        cv2.CAP_V4L2,
        cv2.CAP_GSTREAMER,
        cv2.CAP_FFMPEG,
        cv2.CAP_ANY
    ]
    
    for backend in backends:
        for i in range(5):
            try:
                print(f"尝试后端 {backend} 和索引 {i}...")
                cap = cv2.VideoCapture(i, backend)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        print(f"成功找到可用摄像头，后端: {backend}, 索引: {i}")
                        cap.release()
                        return i, backend
                cap.release()
            except Exception as e:
                print(f"后端 {backend} 索引 {i} 失败: {e}")
                continue
    
    print("未找到可用的摄像头设备")
    return None

# Save a full-size image to disk
def saveImage(image, quality, diskSpaceToReserve):
    keepDiskSpaceFree(diskSpaceToReserve)
    time_now = datetime.now()
    filename = os.path.join(filepath, f"{filenamePrefix}-%04d%02d%02d-%02d%02d%02d.jpg" % (time_now.day, time_now.month, time_now.year, time_now.hour, time_now.minute, time_now.second))
    
    # Convert BGR (OpenCV) to RGB (PIL)
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    im = Image.fromarray(image_rgb)
    im.save(filename, quality=quality)
    print(f"Captured {filename}")

# Keep free space above given level
def keepDiskSpaceFree(bytesToReserve):
    if (getFreeSpace() < bytesToReserve):
        for filename in sorted(os.listdir(filepath + "/")):
            if filename.startswith(filenamePrefix) and filename.endswith(".jpg"):
                os.remove(filepath + "/" + filename)
                print("Deleted %s/%s to avoid filling disk" % (filepath, filename))
                if (getFreeSpace() > bytesToReserve):
                    return

# Get available disk space
def getFreeSpace():
    st = os.statvfs(filepath + "/")
    du = st.f_bavail * st.f_frsize
    return du

# Ensure the directory exists before saving files
def ensure_directory_exists(directory):
    if not os.path.exists(directory):
        print(f"Directory {directory} does not exist, creating it...")
        os.makedirs(directory)

# Ensure the directory is available
ensure_directory_exists(filepath)

def motion():
    # 使用新的摄像头查找函数
    camera_info = find_available_camera()
    
    if camera_info is None:
        print("错误: 无法找到可用的摄像头设备")
        return
    
    # 处理返回值（可能是索引或(索引, 后端)元组）
    if isinstance(camera_info, tuple):
        camera_index, backend = camera_info
        camera = cv2.VideoCapture(camera_index, backend)
    else:
        camera_index = camera_info
        camera = cv2.VideoCapture(camera_index)
    
    print(f"使用摄像头索引: {camera_index}")
    
    if not camera.isOpened():
        print("错误: 摄像头无法打开")
        return

    # 尝试设置较低的分辨率，然后逐步提高
    resolutions = [
        (640, 480),
        (1280, 720),
        (1296, 972)
    ]
    
    for width, height in resolutions:
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        
        # 测试是否能读取图像
        ret, test_frame = camera.read()
        if ret and test_frame is not None:
            actual_width = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"成功设置分辨率: {actual_width}x{actual_height}")
            break
        else:
            print(f"分辨率 {width}x{height} 设置失败，尝试下一个...")
    
    # 可选：设置编码格式，如果失败则跳过
    try:
        camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        print("MJPG编码设置成功")
    except:
        print("MJPG编码设置失败，使用默认编码")

    # Get first color frame
    ret, image1 = camera.read()
    if not ret:
        print("错误: 无法捕获初始图像")
        camera.release()
        return

    print("摄像头初始化成功，开始运动检测...")
    
    lastCapture = time.time()
    lastCaptureTime = 0
    captureInterval = 0
    
    cv2.namedWindow("Camera Feed", cv2.WINDOW_NORMAL)

    while True:
        ret, image2 = camera.read()
        if not ret:
            print("错误: 无法捕获帧")
            break

        image2 = cv2.flip(image2, 0)

        # Check if images are in the expected format
        if image1 is None or image2 is None:
            print("警告: 图像为空")
            continue

        if len(image1.shape) != 3 or len(image2.shape) != 3:
            print("警告: 图像不是彩色图像")
            print("Image1 shape:", image1.shape if image1 is not None else "None")
            print("Image2 shape:", image2.shape if image2 is not None else "None")
            continue

        # Motion detection logic
        changedPixels = 0
        takePicture = False

        for z in range(testAreaCount):
            x_start = testBorders[z][0][0] - 1
            x_end = testBorders[z][0][1]
            y_start = testBorders[z][1][0] - 1
            y_end = testBorders[z][1][1]
            
            # 确保坐标在图像范围内
            x_start = max(0, min(x_start, image1.shape[1] - 1))
            x_end = max(0, min(x_end, image1.shape[1]))
            y_start = max(0, min(y_start, image1.shape[0] - 1))
            y_end = max(0, min(y_end, image1.shape[0]))
            
            for x in range(x_start, x_end):
                for y in range(y_start, y_end):
                    # Access green channel (index 1) of BGR image
                    pixdiff = abs(int(image1[y, x][1]) - int(image2[y, x][1]))
                    if pixdiff > threshold:
                        changedPixels += 1
                    
                    if changedPixels > sensitivity:
                        currentTime = time.time()
                        if currentTime - lastCaptureTime >= captureInterval:
                            takePicture = True
                            lastCaptureTime = currentTime
                        break
                if takePicture:
                    break
            if takePicture:
                break

        if forceCapture and (time.time() - lastCapture > forceCaptureTime):
            takePicture = True

        if takePicture:
            lastCapture = time.time()
            saveImage(image2, saveQuality, diskSpaceToReserve)

        # Update reference image
        image1 = image2.copy()

        # Draw motion detection area(s)
        for z in range(testAreaCount):
            x_start = testBorders[z][0][0] - 1
            x_end = testBorders[z][0][1]
            y_start = testBorders[z][1][0] - 1
            y_end = testBorders[z][1][1]
            
            # 确保坐标在图像范围内
            x_start = max(0, min(x_start, image2.shape[1] - 1))
            x_end = max(0, min(x_end, image2.shape[1]))
            y_start = max(0, min(y_start, image2.shape[0] - 1))
            y_end = max(0, min(y_end, image2.shape[0]))

            # Draw rectangle around the detection area
            cv2.rectangle(image2, (x_start, y_start), (x_end, y_end), (0, 255, 0), 2)

            # If motion detected in this area, draw in red
            if takePicture:
                cv2.rectangle(image2, (x_start, y_start), (x_end, y_end), (0, 0, 255), 2)

        # Display color feed
        cv2.imshow("Camera Feed", image2)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    camera.release()
    cv2.destroyAllWindows()

# Run the motion detection loop
if __name__ == "__main__":
    print("开始运动检测...")
    motion()