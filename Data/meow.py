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
from picamera2 import Picamera2  # New import for libcamera
import numpy as np
import cv2  # Import OpenCV for displaying the camera feed

# Initialize Picamera2 (libcamera)
picam2 = Picamera2()
picam2.configure(picam2.create_still_configuration())  # Configure the camera for still image capture


# Motion detection settings:
# Threshold          - how much a pixel has to change by to be marked as "changed"
# Sensitivity        - how many changed pixels before capturing an image, needs to be higher if noisy view
# ForceCapture       - whether to force an image to be captured every forceCaptureTime seconds, values True or False
# filepath           - location of folder to save photos
# filenamePrefix     - string that prefixes the file name for easier identification of files.
# diskSpaceToReserve - Delete oldest images to avoid filling disk. How much byte to keep free on disk.
# cameraSettings     - "" = no extra settings; "-hf" = Set horizontal flip of image; "-vf" = Set vertical flip; "-hf -vf" = both horizontal and vertical flip
threshold = 31
sensitivity = 15.5 #10 default value
forceCapture = True
forceCaptureTime = 60 * 60  # Once an hour
filepath = "/home/pi/picam"
filenamePrefix = "capture"
diskSpaceToReserve = 40 * 1024 * 1024  # Keep 40 mb free on disk
cameraSettings = ""

# Settings of the photos to save
saveWidth = 1296
saveHeight = 972
saveQuality = 100  # Set jpeg quality (0 to 100)

# Test-Image settings
testWidth = 100
testHeight = 75

# this is the default setting, if the whole image should be scanned for changed pixel
testAreaCount = 1
testBorders = [[[1, testWidth], [1, testHeight]]]  # [ [[start pixel on left side,end pixel on right side],[start pixel on top side,stop pixel on bottom side]] ]

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

# even more complex example
# testAreaCount = 4
# testBorders = [ [[1,39],[1,75]], [[40,67],[43,75]], [[68,85],[48,75]], [[86,100],[41,75]] ]

# in debug mode, a file debug.bmp is written to disk with marked changed pixel an with marked border of scan-area
# debug mode should only be turned on while testing the parameters above
debugMode = False # Set debug mode here (True to enable debug mode, False to disable)

# Motion detection: Capture a small test image (for motion detection)
def captureTestImage(settings, width, height):
    picam2.start()  # Start the camera
    image = picam2.capture_array()  # Capture the image into a NumPy array
    picam2.stop()  # Stop the camera

    # Convert NumPy array to PIL Image
    im = Image.fromarray(image)
    buffer = im.load()
    return im, buffer, image  # Return the NumPy array image for display

# Save a full-size image to disk
def saveImage(settings, width, height, quality, diskSpaceToReserve):
    keepDiskSpaceFree(diskSpaceToReserve)
    time_now = datetime.now()
    filename = filepath + "/" + filenamePrefix + "-%04d%02d%02d-%02d%02d%02d.jpg" % (time_now.year, time_now.month, time_now.day, time_now.hour, time_now.minute, time_now.second)
    
    picam2.start()  # Start the camera
    image = picam2.capture_array()  # Capture the image into a NumPy array
    picam2.stop()  # Stop the camera
    
    # Convert NumPy array to PIL Image and save it
    im = Image.fromarray(image)
    im = im.resize((saveWidth, saveHeight))  # Resize the image to desired dimensions
    im.save(filename, quality=quality, icc_profile=None)

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

# Define the path for storing captured images and debug files
filepath = "/home/pi/picam"

# Ensure the directory exists before saving files
def ensure_directory_exists(directory):
    if not os.path.exists(directory):
        print(f"Directory {directory} does not exist, creating it...")
        os.makedirs(directory)

# Ensure the directory is available
ensure_directory_exists(filepath)

def motion():
    # Get the first image
    image1, buffer1, _ = captureTestImage(cameraSettings, testWidth, testHeight)

    # Reset last capture time
    lastCapture = time.time()

    # Initialize OpenCV window to show the camera feed
    cv2.namedWindow("Camera Feed", cv2.WINDOW_NORMAL)
    

    while True:
        # Get the comparison image
        image2, buffer2, full_image2 = captureTestImage(cameraSettings, testWidth, testHeight)

        # Count changed pixels
        changedPixels = 0
        takePicture = False

        # Loop through the test areas
        for z in range(0, testAreaCount):
            for x in range(testBorders[z][0][0] - 1, testBorders[z][0][1]):
                for y in range(testBorders[z][1][0] - 1, testBorders[z][1][1]):
                    # Check for motion in the green channel
                    pixdiff = abs(buffer1[x, y][1] - buffer2[x, y][1])
                    if pixdiff > threshold:
                        changedPixels += 1
                    # If enough pixels changed, mark to take a picture
                    if changedPixels > sensitivity:
                        takePicture = True
                    if changedPixels > sensitivity:
                        break  # Break early if threshold is exceeded
                if changedPixels > sensitivity:
                    break  # Break the x loop
            if changedPixels > sensitivity:
                break  # Break the z loop

        # Check force capture (capture periodically even if no motion is detected)
        if forceCapture:
            if time.time() - lastCapture > forceCaptureTime:
                takePicture = True

        if takePicture:
            lastCapture = time.time()
            saveImage(cameraSettings, saveWidth, saveHeight, saveQuality, diskSpaceToReserve)

        # Swap comparison buffers for the next iteration
        image1 = image2
        buffer1 = buffer2

        # Show the camera feed in OpenCV window
        #cv2.imshow("Camera Feed", full_image2)
        
        # Show the camera feed in OpenCV window in BGR
        full_image2_bgr = cv2.cvtColor(full_image2, cv2.COLOR_RGB2BGR) #opencv uses BGR format!
        cv2.imshow("Camera Feed", full_image2_bgr)

        # Break the loop if 'q' is pressed
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        # Sleep to reduce CPU usage
        #time.sleep(0.1)

    # Release the OpenCV window and cleanup
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
conda activate raspi_ml # Activate miniforge3 envs
conda install pip # Install Pip if needed
pipreqs . --force
.
.
python3 meow.py # Run code
'''

