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
threshold = 50  # Change threshold value
sensitivity = 20  # Default value is 10
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
testWidth = 10000 #100
testHeight = 7500 #75

# Define the borders for scanning changed pixels
testAreaCount = 1
testBorders = [[[1, testWidth], [1, testHeight]]]  # Scan the entire image area

# Debug mode (set to True for debugging purposes)
debugMode = False

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

# Ensure the directory is available
def ensure_directory_exists(directory):
    if not os.path.exists(directory):
        print(f"Directory {directory} does not exist, creating it...")
        os.makedirs(directory)

# Capture a small test image (for motion detection)
def captureTestImage(settings, width, height):
    picam2.start()  # Start the camera
    image = picam2.capture_array()  # Capture the image into a NumPy array
    picam2.stop()  # Stop the camera

    # Convert NumPy array to PIL Image
    im = Image.fromarray(image)
    
    # Get actual dimensions of the captured image
    global testWidth, testHeight
    testWidth, testHeight = im.size  # Update the test dimensions based on the image size
    
    # Set the borders to cover the entire image
    testBorders[0] = [[1, testWidth], [1, testHeight]]
    
    buffer = im.load()
    print(f"Captured image size: {im.size}")  # Print the actual image size
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

# Function to draw centered borders on the image
def drawBorders(image, testBorders):
    # Get the dimensions of the captured image (using NumPy shape)
    image_height, image_width = image.shape[:2]  # shape gives (height, width, channels)
    
    # Define border size (you can adjust this size as needed)
    border_width = 1000
    border_height = 750
    
    # Calculate the top-left corner to center the border
    x1 = (image_width - border_width) // 2
    y1 = (image_height - border_height) // 2
    x2 = x1 + border_width
    y2 = y1 + border_height
    
    # Draw a rectangle around the test area (green color, thickness of 2 pixels)
    cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)  # Green color, thickness 2
    return image

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

        # Draw the borders around the test area
        image_with_borders = drawBorders(full_image2, testBorders)

        # Convert the image to BGR (OpenCV uses BGR, but Picamera2 captures in RGB)
        full_image2_bgr = cv2.cvtColor(image_with_borders, cv2.COLOR_RGB2BGR)

        # Show the camera feed with the borders drawn in OpenCV window
        cv2.imshow("Camera Feed", full_image2_bgr)

        # Break the loop if 'q' is pressed
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Release the OpenCV window and cleanup
    cv2.destroyAllWindows()

# Run the motion detection loop
if __name__ == "__main__":
    print("Starting motion detection...")
    motion()
    
    


