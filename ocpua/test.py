#!/usr/bin/python

# original script by brainflakes, improved by pageauc, peewee2 and Kesthal
# improved by meow2 to run in libcamera/raspberrypi 4
# Modified to work with robot communication signals

import io
import subprocess
import os
import time
from datetime import datetime
from PIL import Image
import numpy as np
import cv2
import socket
import threading
import serial
import queue

os.environ["QT_QPA_PLATFORM"] = "xcb"  # Fix Wayland warning

########################################################################################################################################
# Motion detection settings (same as original)
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
saveQuality = 100

# Detection area settings
testAreaCount = 1
testWidth = 200
testHeight = 150

center_x = 1296 // 2
center_y = 972 // 2
half_width = 200 // 2
half_height = 150 // 2

testBorders = [[[center_x - half_width + 1, center_x + half_width],
                [center_y - half_height + 1, center_y + half_height]]]

debugMode = False

########################################################################################################################################
# Robot Communication Settings - Choose ONE method
########################################################################################################################################

# Method 1: Socket Communication (TCP/IP)
COMMUNICATION_METHOD = "socket"  # Options: "socket", "serial", "udp"
ROBOT_IP = "192.168.1.100"  # Replace with robot's IP address
ROBOT_PORT = 8888           # Replace with robot's port

# Method 2: Serial Communication (USB/UART)
SERIAL_PORT = "/dev/ttyUSB0"  # Replace with actual serial port
SERIAL_BAUDRATE = 9600

# Method 3: UDP Communication
UDP_PORT = 9999

########################################################################################################################################
# Robot Communication Classes
########################################################################################################################################

class RobotCommunication:
    def __init__(self, method="socket"):
        self.method = method
        self.robot_signal = 0  # Default signal
        self.signal_queue = queue.Queue()
        self.running = False
        self.connection = None
        
    def start(self):
        """Start the communication thread"""
        self.running = True
        if self.method == "socket":
            self.thread = threading.Thread(target=self._socket_listener)
        elif self.method == "serial":
            self.thread = threading.Thread(target=self._serial_listener)
        elif self.method == "udp":
            self.thread = threading.Thread(target=self._udp_listener)
        else:
            print(f"Unknown communication method: {self.method}")
            return
            
        self.thread.daemon = True
        self.thread.start()
        print(f"Started {self.method} communication listener")
    
    def stop(self):
        """Stop the communication thread"""
        self.running = False
        if self.connection:
            try:
                self.connection.close()
            except:
                pass
    
    def get_robot_signal(self):
        """Get the latest robot signal"""
        # Get the most recent signal from queue
        while not self.signal_queue.empty():
            try:
                self.robot_signal = self.signal_queue.get_nowait()
            except queue.Empty:
                break
        return self.robot_signal
    
    def _socket_listener(self):
        """Listen for TCP socket connections from robot"""
        try:
            # Create server socket
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind(('0.0.0.0', ROBOT_PORT))
            server_socket.listen(1)
            server_socket.settimeout(1.0)  # Non-blocking with timeout
            
            print(f"Listening for robot connection on port {ROBOT_PORT}")
            
            while self.running:
                try:
                    # Accept connection
                    self.connection, addr = server_socket.accept()
                    print(f"Robot connected from {addr}")
                    
                    # Receive data
                    while self.running:
                        try:
                            data = self.connection.recv(1024)
                            if not data:
                                break
                            
                            # Parse signal (expect '0' or '1')
                            signal_str = data.decode('utf-8').strip()
                            if signal_str in ['0', '1']:
                                signal = int(signal_str)
                                self.signal_queue.put(signal)
                                print(f"Received robot signal: {signal}")
                            
                        except socket.timeout:
                            continue
                        except Exception as e:
                            print(f"Error receiving data: {e}")
                            break
                            
                    self.connection.close()
                    print("Robot disconnected")
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"Socket error: {e}")
                    
        except Exception as e:
            print(f"Failed to create socket server: {e}")
        finally:
            try:
                server_socket.close()
            except:
                pass
    
    def _serial_listener(self):
        """Listen for serial data from robot"""
        try:
            import serial
            ser = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE, timeout=1)
            self.connection = ser
            print(f"Opened serial port {SERIAL_PORT} at {SERIAL_BAUDRATE} baud")
            
            while self.running:
                try:
                    if ser.in_waiting > 0:
                        data = ser.readline().decode('utf-8').strip()
                        if data in ['0', '1']:
                            signal = int(data)
                            self.signal_queue.put(signal)
                            print(f"Received robot signal: {signal}")
                except Exception as e:
                    if self.running:
                        print(f"Serial error: {e}")
                    time.sleep(0.1)
                    
        except Exception as e:
            print(f"Failed to open serial port: {e}")
        finally:
            if self.connection:
                self.connection.close()
    
    def _udp_listener(self):
        """Listen for UDP packets from robot"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(('0.0.0.0', UDP_PORT))
            sock.settimeout(1.0)
            self.connection = sock
            print(f"Listening for UDP packets on port {UDP_PORT}")
            
            while self.running:
                try:
                    data, addr = sock.recvfrom(1024)
                    signal_str = data.decode('utf-8').strip()
                    if signal_str in ['0', '1']:
                        signal = int(signal_str)
                        self.signal_queue.put(signal)
                        print(f"Received robot signal: {signal} from {addr}")
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"UDP error: {e}")
                    
        except Exception as e:
            print(f"Failed to create UDP socket: {e}")
        finally:
            if self.connection:
                self.connection.close()

########################################################################################################################################
# Original functions (same as before)
########################################################################################################################################

def saveImage(image, quality, diskSpaceToReserve):
    keepDiskSpaceFree(diskSpaceToReserve)
    time_now = datetime.now()
    filename = os.path.join(filepath, f"{filenamePrefix}-%04d%02d%02d-%02d%02d%02d.jpg" % (time_now.day, time_now.month, time_now.year, time_now.hour, time_now.minute, time_now.second))
    
    # Convert BGR (OpenCV) to RGB (PIL)
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
    du = st.f_bavail * st.f_frsize
    return du

def ensure_directory_exists(directory):
    if not os.path.exists(directory):
        print(f"Directory {directory} does not exist, creating it...")
        os.makedirs(directory)

ensure_directory_exists(filepath)

########################################################################################################################################
# Modified Motion Detection Function
########################################################################################################################################

def motion():
    # Initialize robot communication
    robot_comm = RobotCommunication(method=COMMUNICATION_METHOD)
    robot_comm.start()
    
    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        print("Error: Camera not accessible.")
        robot_comm.stop()
        return

    # Set camera resolution
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1296)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 972)
    camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

    # Get first color frame
    ret, image1 = camera.read()
    if not ret:
        print("Error: Unable to capture initial image.")
        camera.release()
        robot_comm.stop()
        return

    lastCapture = time.time()
    cv2.namedWindow("Camera Feed", cv2.WINDOW_NORMAL)
    lastCaptureTime = 0
    captureInterval = 0

    print("Motion detection started. Waiting for robot signals...")
    print("Robot signal 0 = No capture, Robot signal 1 = Allow capture")

    while True:
        ret, image2 = camera.read()
        if not ret:
            print("Error: Unable to capture frame.")
            break

        image2 = cv2.flip(image2, 0)

        # Check image format
        if image1 is None or image2 is None:
            print("Warning: One of the images is None.")
            continue

        if len(image1.shape) != 3 or len(image2.shape) != 3:
            print("Warning: One of the images is not a color image.")
            continue

        # Get current robot signal
        robot_signal = robot_comm.get_robot_signal()
        
        # Motion detection logic (same as original)
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

        # MODIFIED: Only save image if motion detected AND robot signal is 1
        if takePicture and robot_signal == 1:
            lastCapture = time.time()
            saveImage(image2, saveQuality, diskSpaceToReserve)
            print("✓ Image saved (Motion detected + Robot signal = 1)")
        elif takePicture and robot_signal == 0:
            print("✗ Motion detected but robot signal = 0, image not saved")

        # Update reference image
        image1 = image2.copy()

        # Draw motion detection areas and robot signal status
        for z in range(testAreaCount):
            x_start = testBorders[z][0][0] - 1
            x_end = testBorders[z][0][1]
            y_start = testBorders[z][1][0] - 1
            y_end = testBorders[z][1][1]

            # Draw rectangle around the detection area
            color = (0, 255, 0)  # Green by default
            if takePicture and robot_signal == 1:
                color = (0, 0, 255)  # Red when capturing
            elif takePicture and robot_signal == 0:
                color = (0, 255, 255)  # Yellow when motion detected but not capturing
            
            cv2.rectangle(image2, (x_start, y_start), (x_end, y_end), color, 2)

        # Display robot signal status on screen
        signal_text = f"Robot Signal: {robot_signal}"
        signal_color = (0, 255, 0) if robot_signal == 1 else (0, 0, 255)
        cv2.putText(image2, signal_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, signal_color, 2)
        
        status_text = "CAPTURE ENABLED" if robot_signal == 1 else "CAPTURE DISABLED"
        cv2.putText(image2, status_text, (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, signal_color, 2)

        # Display color feed
        cv2.imshow("Camera Feed", image2)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Cleanup
    camera.release()
    cv2.destroyAllWindows()
    robot_comm.stop()
    print("Motion detection stopped")

# Run the motion detection loop
if __name__ == "__main__":
    print("Starting motion detection with robot communication...")
    print(f"Communication method: {COMMUNICATION_METHOD}")
    if COMMUNICATION_METHOD == "socket":
        print(f"Listening on port: {ROBOT_PORT}")
    elif COMMUNICATION_METHOD == "serial":
        print(f"Serial port: {SERIAL_PORT} at {SERIAL_BAUDRATE} baud")
    elif COMMUNICATION_METHOD == "udp":
        print(f"UDP port: {UDP_PORT}")
    
    motion()
