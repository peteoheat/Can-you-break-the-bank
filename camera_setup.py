"""
camera_setup.py

Opens the camera for the can-you-break-the-bank scripts, so tk_add_user.py and tk_open_vault.py set it up
the same way. open_camera(config) returns either a Raspberry Pi camera (Picamera2) or a USB
webcam, depending on [camera] type in the config file. Both provide capture_array() and
close(), and both return frames in BGR order (the Pi camera's "RGB888" frames are BGR in
memory), so the scripts' colour handling is the same for either camera.

Importing this module has no hardware side effects; calling open_camera() starts the camera.
"""

import cv2


class WebcamCamera:
    """Gives a USB webcam the small part of the Picamera2 interface the scripts use."""

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


def open_camera(config):
    """Open and start the camera chosen in the config and return it."""
    width = config["frame_width"]
    height = config["frame_height"]
    frame_rate = config["frame_rate"]

    if config["camera_type"] == "webcam":
        # A USB webcam. Your camera might be on something other than /dev/video0 - you can
        # check by running the command 'v4l2-ctl --list-devices' and setting webcam_device in the config
        return WebcamCamera(config["webcam_device"], width, height, frame_rate)

    # A raspberry pi camera on the CSI interface (imported here so a webcam setup doesn't need picamera2)
    from picamera2 import Picamera2
    camera = Picamera2()
    camera.preview_configuration.main.size = (width, height)
    camera.preview_configuration.main.format = "RGB888"
    camera.preview_configuration.controls.FrameRate = frame_rate
    camera.preview_configuration.align()
    camera.configure("preview")
    #camera.set_controls({
    #    "AeEnable": True,
    #    "ExposureTime": 10000,
    #    "AnalogueGain": 2.0,
    #    "Brightness": 0.5
    #   })
    camera.start()
    return camera
