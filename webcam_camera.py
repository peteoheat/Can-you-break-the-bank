"""
webcam_camera.py

Lets a USB webcam stand in for the Raspberry Pi camera (Picamera2). It provides the
small part of the Picamera2 interface the scripts use: capture_array() and close().

Frames come back in BGR order, which is the same byte order as the Pi camera's
"RGB888" frames, so the scripts' colour handling is the same for both cameras.
"""

import cv2


class WebcamCamera:
    def __init__(self, device, width, height, frame_rate):
        # A device number (e.g. "0") or a path (e.g. "/dev/video0"); check with 'v4l2-ctl --list-devices'
        self.capture = cv2.VideoCapture(int(device) if device.isdigit() else device)
        if not self.capture.isOpened():
            raise RuntimeError(f"Could not open the webcam at {device}")
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.capture.set(cv2.CAP_PROP_FPS, frame_rate)

    def capture_array(self):
        success, frame = self.capture.read()
        if not success:
            raise RuntimeError("Could not read a frame from the webcam")
        return frame

    def close(self):
        self.capture.release()
