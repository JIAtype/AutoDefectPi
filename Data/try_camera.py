import io
import subprocess
import os
import time
from datetime import datetime
from PIL import Image
import numpy as np
import cv2

# 设置摄像头参数及文件保存路径等
threshold = 20
sensitivity = 5
forceCapture = True
forceCaptureTime = 60 * 60
filepath = "/home/pe/Downloads/Ann Machine/Data/databin"
filenamePrefix = "capture"
diskSpaceToReserve = 40 * 1024 * 1024

saveWidth = 1296
saveHeight = 972
saveQuality = 100  

testAreaCount = 1
testWidth = 200      
testHeight = 150

center_x = 1296 // 2
center_y = 972 // 2
half_width = 200 // 2
half_height = 150 // 2

testBorders = [[[center_x - half_width + 1, center_x + half_width], 
                 [center_y - half_height + 1, center_y + half_height]]]

def saveImage(image, quality, diskSpaceToReserve):
    keepDiskSpaceFree(diskSpaceToReserve)
    time_now = datetime.now()
    filename = os.path.join(filepath, f"{filenamePrefix}-%04d%02d%02d-%02d%02d%02d.jpg" % 
                             (time_now.day, time_now.month, time_now.year, 
                              time_now.hour, time_now.minute, time_now.second))

    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    im = Image.fromarray(image_rgb)
    im.save(filename, quality=quality)
    print(f"Captured {filename}")

def keepDiskSpaceFree(bytesToReserve):
    if (getFreeSpace() < bytesToReserve):
        for filename in sorted(os.listdir(filepath + "/")):
            if filename.startswith(filenamePrefix) and filename.endswith(".jpg"):
                os.remove(filepath + "/" + filename)
                print("Deleted %s/%s to avoid filling disk" % (filepath, filename))
                if (getFreeSpace() > bytesToReserve):
                    return

def getFreeSpace():
    st = os.statvfs(filepath + "/")
    return st.f_bavail * st.f_frsize

def ensure_directory_exists(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

ensure_directory_exists(filepath)

def motion():
    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        print("Error: Camera not accessible.")
        return

    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1296)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 972)
    camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

    try:
        ret, image1 = camera.read()
        if not ret:
            print("Error: Unable to capture initial image.")
            return

        lastCapture = time.time()
        cv2.namedWindow("Camera Feed", cv2.WINDOW_NORMAL)

        while True:
            ret, image2 = camera.read()
            if not ret:
                print("Error: Unable to capture frame.")
                break

            image2 = cv2.flip(image2,0)

            changedPixels = 0
            takePicture = False

            for z in range(testAreaCount):
                x_start = testBorders[z][0][0] - 1
                x_end = testBorders[z][0][1]
                y_start = testBorders[z][1][0] - 1
                y_end = testBorders[z][1][1]

                for x in range(x_start, x_end):
                    for y in range(y_start, y_end):
                        pixdiff = abs(int(image1[y, x][1]) - int(image2[y, x][1]))
                        if pixdiff > threshold:
                            changedPixels += 1
                        if changedPixels > sensitivity:
                            currentTime = time.time()
                            if currentTime - lastCapture >= forceCaptureTime:
                                takePicture = True
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

            image1 = image2.copy()
            cv2.imshow("Camera Feed", image2)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        camera.release()
        cv2.destroyAllWindows()

# Run the motion detection loop
if __name__ == "__main__":
    print("Starting motion detection...")
    motion()
