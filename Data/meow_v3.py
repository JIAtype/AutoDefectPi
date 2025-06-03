#!/usr/bin/python

# original script by brainflakes, improved by pageauc, peewee2 and Kesthal
# improved by meow2 to run in libcamera/raspberrypi 4
# www.raspberrypi.org/phpBB3/viewtopic.php?f=43&t=45235

# You need to install PIL to run this script
# type "sudo apt-get install python-imaging-tk" in an terminal window to do this

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
# Motion detection settings:
# Threshold          - how much a pixel has to change by to be marked as "changed"
# Sensitivity        - how many changed pixels before capturing an image, needs to be higher if noisy view
# ForceCapture       - whether to force an image to be captured every forceCaptureTime seconds, values True or False
# filepath           - location of folder to save photos
# filenamePrefix     - string that prefixes the file name for easier identification of files.
# diskSpaceToReserve - Delete oldest images to avoid filling disk. How much byte to keep free on disk.
# cameraSettings     - "" = no extra settings; "-hf" = Set horizontal flip of image; "-vf" = Set vertical flip; "-hf -vf" = both horizontal and vertical flip
########################################################################################################################################

threshold = 20 #31 previous
sensitivity = 5 #15.5 #10 default value
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
#testWidth = 100
#testHeight = 75

# this is the default setting, if the whole image should be scanned for changed pixel
testAreaCount = 1
#testBorders = [[[1, testWidth], [1, testHeight]]]  # [ [[start pixel on left side,end pixel on right side],[start pixel on top side,stop pixel on bottom side]] ]

# Instead of scanning entire frame:
testWidth = 200      # Increase detection resolution
testHeight = 150
#testBorders = [[[50, 150], [50, 100]]]  # Focus on center area

# Center detection box for 640x480 frame
center_x = 1296 // 2
center_y = 972 // 2
half_width = 200 // 2
half_height = 150 // 2

testBorders = [[[center_x - half_width + 1, center_x + half_width],
                [center_y - half_height + 1, center_y + half_height]]]



########################################################################################################################################
# testBorders are NOT zero-based, the first pixel is 1 and the last pixel is testWith or testHeight

# with "testBorders", you can define areas, where the script should scan for changed pixel
# for example, if your picture looks like this:
#
#     ....XXXX
#     ........
#     ........
#
# "." is a street or a house, "X" are trees which move arround like crazy when the wind is blowing
# because of the wind in the trees, there will be taken photos all the time. to prevent this, your setting might look like this:

# testAreaCount = 2
# testBorders = [ [[1,50],[1,75]], [[51,100],[26,75]] ] # area y=1 to 25 not scanned in x=51 to 100
#
# even more complex example
# testAreaCount = 4
# testBorders = [ [[1,39],[1,75]], [[40,67],[43,75]], [[68,85],[48,75]], [[86,100],[41,75]] ]

# in debug mode, a file debug.bmp is written to disk with marked changed pixel an with marked border of scan-area
# debug mode should only be turned on while testing the parameters above
########################################################################################################################################

debugMode = False # Set debug mode here (True to enable debug mode, False to disable)

# Save a full-size image to disk
def saveImage(image, quality, diskSpaceToReserve):
    keepDiskSpaceFree(diskSpaceToReserve)
    time_now = datetime.now()
    filename = os.path.join(filepath, f"{filenamePrefix}-%04d%02d%02d-%02d%02d%02d.jpg" % (time_now.day, time_now.month, time_now.year, time_now.hour, time_now.minute, time_now.second))
    
    # Convert BGR (OpenCV) to RGB (PIL)
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    im = Image.fromarray(image_rgb)
    #im = im.resize((saveWidth, saveHeight))  # Resize
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
    camera = cv2.VideoCapture(0) #default 0
    #fgbg = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=16)
    if not camera.isOpened():
        print("Error: Camera not accessible.")
        return

    # Set camera resolution for better quality
    # camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    # camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1296)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 972)

    camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))  # Ensure color output

    # Get first color frame
    ret, image1 = camera.read()
    if not ret:
        print("Error: Unable to capture initial image.")
        return

    lastCapture = time.time()
    cv2.namedWindow("Camera Feed", cv2.WINDOW_NORMAL)

    lastCapture = time.time()
    lastCaptureTime = 0  # <-- MOVE THIS OUTSIDE
    captureInterval = 0 # seconds between captures

    while True:
        ret, image2 = camera.read()
        if not ret:
            print("Error: Unable to capture frame.")
            break

        image2 = cv2.flip(image2,0)

        # Check if images are in the expected format
        if image1 is None or image2 is None:
            print("Warning: One of the images is None.")
            continue

        if len(image1.shape) != 3 or len(image2.shape) != 3:
            print("Warning: One of the images is not a color image.")
            print("Image1 shape:", image1.shape if image1 is not None else "None")
            print("Image2 shape:", image2.shape if image2 is not None else "None")
            continue

        # Motion detection logic
        changedPixels = 0
        takePicture = False

        # lastCaptureTime = 0  # Initialize last capture time
        # captureInterval = 5  # seconds between captures

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
                    # if changedPixels > sensitivity:
                    #     takePicture = True
                    #     break
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
    print("Starting motion detection...")
    motion()
    
######################################################################################################
#How to use the code?
#to run code: sudo python3 /home/intern/meow.py
#to kill cam: press Q or q on keyboard
#to find pic: Go to /home/pi/picam folder

'''
# Activate miniforge3 envs
conda install pip # Install Pip if needed
pipreqs . --force
.
.
python3 meow_v3.py # Run code
'''

