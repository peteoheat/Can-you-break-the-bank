#!/usr/bin/python3
import sys
from app_config import load_config
# Settings come from ~/.config/can-you-break-the-bank/can-you-break-the-bank.cfg
config = load_config()
sys.path.append(config["includes_dir"])
import time
import csv
from collections import deque
from oled_091 import SSD1306
from time import sleep
from os import system
import serial
import RPi.GPIO as GPIO
import face_recognition
import pickle
import board
import neopixel_spi
import threading as Th
#from threading import Thread, Event
import cv2
import numpy as np
import tkinter as tk
from tkinter import *
from tkinter.font import Font
from tkinter import ttk
import subprocess
import dbus
import redis
from camera_setup import open_camera

frame_width=config["frame_width"]
frame_height=config["frame_height"]

# The Pi camera or USB webcam, as chosen by [camera] type in the config (see camera_setup.py)
camera=open_camera(config)

def set_wallpaper(image_path):
    # Create a session D-Bus interface to the plasmashell
    bus = dbus.SessionBus()
    plasma = bus.get_object("org.kde.plasmashell", "/PlasmaShell")
    interface = dbus.Interface(plasma, dbus_interface="org.kde.PlasmaShell")

    # Send the D-Bus command to change the wallpaper
    script = f"""
    var Desktops = desktops();
    for (i = 0; i < Desktops.length; i++) {{
        d = Desktops[i];
        d.wallpaperPlugin = "org.kde.image";
        d.currentConfigGroup = Array("Wallpaper", "org.kde.image", "General");
        d.writeConfig("Image", "file://{image_path}");
    }}
    """
    interface.evaluateScript(script)



# GPIO PINS
# Beacon is the GPIO pin for the electronic relay to control the 12V flashing beacon
Beacon = config["beacon_pin"]
# Buzzer is used to control the buzzer on the RFID HAT that beeps when a card is scanned
Buzzer = config["buzzer_pin"]

#Neopixel setup
pixels_num = config["neopixel_count"]
pixel_ord = neopixel_spi.GRB = 'GRB'
pixel_khz = config["neopixel_frequency"]
pixel_bits = 3
pixel_brightness = config["neopixel_brightness"]
pixel_red = (255, 0, 0)
pixel_green = (0, 255, 0)
pixel_blue = (0, 0, 255)
pixel_off = (0,0,0)

pixels = neopixel_spi.NeoPixel_SPI(
        board.SPI(),
        pixels_num,
        bpp=pixel_bits,
        brightness=pixel_brightness,
        auto_write=False,
        frequency=pixel_khz,
        pixel_order=pixel_ord,
        bit0=0b10000000)

#GPIO setup
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(Buzzer, GPIO.OUT)
GPIO.setup(Beacon, GPIO.OUT)
GPIO.output(Beacon, GPIO.HIGH)

draw_red = (0, 0, 255)
draw_green = (0, 255, 0)
draw_amber = (0, 125, 255)

display=SSD1306()



class AuthApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Vault Security")
        self.geometry('800x600+0+0')
        self.resizable(False, False)
        
        self.HdgFont = Font(family="Quicksand", size=24, weight="bold")
        self.SubHdgFont = Font(family="Quicksand", size=18, weight="bold")
        self.NormalFont = Font(family="Quicksand", size=10, weight="bold")
        
        self.dataframe = Frame(self.master, padx=10, pady=10, width=750, height=750)
        self.dataframe.grid_propagate(False)
        self.dataframe.grid(row=0, column=0, padx=10, pady=10)
        
        self.infoframe = Frame(self.dataframe, padx=10, pady=10, width=750, height=250, background="white")
        self.infoframe.grid_propagate(False)
        self.infoframe.grid(row=5, column=0, columnspan=5, padx=10, pady=10)
        
        self.heading_label = Label(self.dataframe, text="Welcome to A.N. Other Bank", font=self.HdgFont)
        self.subhead_label = Label(self.dataframe, text="Vault Security Control", font=self.SubHdgFont)
        self.heading_label.grid(row=0, column=0, columnspan=5)
        self.subhead_label.grid(row=1, column=0, columnspan=5)
        
        #Progress Bar Label
        self.progress_bar_label = Label(self.dataframe, text="Progress: ", font=self.SubHdgFont)
        self.progress_bar_label.grid(row=2, column=0, columnspan=2)
        
        # Progress Bar
        self.progress_bar = ttk.Progressbar(self.dataframe, length=300, maximum=3, mode='determinate')
        self.progress_bar.grid(row=2, column=1, ipady=5, columnspan=5)
        
        # Step labels
        self.step_label = Label(self.dataframe, text="", font=self.SubHdgFont)
        self.step_label.grid(row=3, column=0, columnspan=5)
        
        # Define buttons
        self.button_Factor1 = Button(self.dataframe, text="Factor 1", padx=20, pady=20, command=self.start_factor_1, bg="green", foreground="white", font=self.SubHdgFont)
        self.button_Factor2 = Button(self.dataframe, state='disabled', text="Factor 2", padx=20, pady=20, command=self.start_factor_2, bg="green", foreground="white", font=self.SubHdgFont)
        self.button_Factor3 = Button(self.dataframe, state='disabled', text="Factor 3", padx=20, pady=20, command=self.start_factor_3, bg="green", foreground="white", font=self.SubHdgFont)
        self.button_Open_Vault = Button(self.dataframe, state='disabled', text="Open Vault", padx=20, pady=20, command=self.Open_Vault, bg="red", font=self.SubHdgFont)

        # Place buttons
        self.button_Factor1.grid(row=4, column=0, columnspan=1)
        self.button_Factor2.grid(row=4, column=1, columnspan=1)
        self.button_Factor3.grid(row=4, column=2, columnspan=1)
        self.button_Open_Vault.grid(row=4, column=3, columnspan=1)

        self.instruction_label1 = Label(self.infoframe, text="Click 'Factor 1' button to start.", fg="black", bg="white", wraplength=700, font=self.HdgFont)
        self.instruction_label2 = Label(self.infoframe, text="You will be required to pass 3 factors of authentication to open the vault:", fg="black", bg="white", wraplength=700, font=self.SubHdgFont)
        self.instruction_label3 = Label(self.infoframe, text="Factor 1 = Something you HAVE (An access card)", fg="black", bg="white", wraplength=700, font=self.SubHdgFont)
        self.instruction_label4 = Label(self.infoframe, text="Factor 2 = Something you KNOW (A PIN)", fg="black", bg="white", wraplength=700, font=self.SubHdgFont)
        self.instruction_label5 = Label(self.infoframe, text="Factor 3 = Something you ARE (Facial recognition)", fg="black", bg="white", wraplength=700, font=self.SubHdgFont)

        self.instruction_label1.grid(row=0, column=0, columnspan=5)
        self.instruction_label2.grid(row=1, column=0, columnspan=5)
        self.instruction_label3.grid(row=2, column=0, columnspan=5)
        self.instruction_label4.grid(row=3, column=0, columnspan=5)
        self.instruction_label5.grid(row=4, column=0, columnspan=5)
        
        self.button_EXIT = Button(self.dataframe, state='normal', text="Exit", padx=20, pady=20, command=self.exit_app, bg="red", font=self.SubHdgFont)
        self.button_EXIT.grid(row=6, column=0, columnspan=5)
        
        self.attractmode_stop = Th.Event()
        self.attractmode = Th.Thread(target = self.attract_mode, args=(1, self.attractmode_stop))
        self.attractmode.start()
        
        # Initial settings
        self.factor = 0
        self.authentication_failed = False  # Track if any step fails
        
        #Initialize variables
        self.fps=0
        self.fps_pos=(30,60)
        self.fps_font=cv2.FONT_HERSHEY_SIMPLEX
        self.fps_height=1.5
        self.fps_colour=(0,0,255)
        self.fps_weight=3
        self.frame_width=1280
        self.frame_height=720
        self.frame_colour_format="RGB888"
        self.frame_rate=30
        self.small_frame_scale=config["small_frame_scale"]  # box_scale below needs 1/this to be a whole number
        
    def start_factor_1(self):
        """Start the first factor (access card scan)."""
        self.attractmode_stop.set()
        self.instruction_label1.config(text="Factor 1 - Something you HAVE")
        self.instruction_label2.config(text="Scan a valid access card on the reader")
        self.instruction_label3.config(text="")
        self.instruction_label4.config(text="")
        self.instruction_label5.config(text="")
        self.button_Factor1.config(state="disabled")
        self.after(2000, self.process_access_card)  # Simulate card scan delay

    def start_factor_2(self):
        """Start the second factor (PIN entry)."""
        self.instruction_label1.config(text="Factor 2 - Something you KNOW")
        self.instruction_label2.config(text="Enter the correct PIN")
        self.step_label.config(text="Factor 1: Something You HAVE - Passed")
        self.button_Factor2.config(state="disabled")
        self.after(2000, self.process_pin_entry)  # Simulate PIN entry delay

    def start_factor_3(self):
        """Start the third factor (facial recognition)."""
        self.instruction_label1.config(text="Factor 3 - Something you ARE")
        self.instruction_label2.config(text="Pass facial recognition")
        self.step_label.config(text="Factor 2: Something You KNOW - Passed")
        self.button_Factor3.config(state="disabled")
        self.after(2000, self.process_facial_recognition)  # Simulate recognition delay 
        
    def process_access_card(self):
        self.load_data()
        self.access_card_ID = self.read_rfid()
        self.card_owner = ""
        self.card_pin = ""
        if self.access_card_ID in self.knownCards:
            self.progress_bar['value'] = 1
            self.step_label.config(text="Factor 1: Something You HAVE - Passed")
            self.card_owner = self.knownNames[self.knownCards.index(self.access_card_ID)]
            self.card_pin = str(self.knownPINS[self.knownCards.index(self.access_card_ID)])
            self.button_Factor2.config(state="normal")
            self.instruction_label1.config(text="Click 'Factor 2' button to continue")
            self.instruction_label2.config(text="")

        else:
            self.step_label.config(text="Factor 1: Something You HAVE - Failed")
            self.instruction_label1.config(text="Authentication Failed at Factor 1 - Access Denied")
            self.instruction_label2.config(text="")
            self.after(2000, self.deny_access)  # Simulate card scan delay
            self.after(2000, self.reset_app)  # Simulate card scan delay

        
    def process_pin_entry(self):
        # Simulate PIN entry with a random outcome
        success = subprocess.call([sys.executable, config["pin_game"], self.card_pin])
        if success:
            self.step_label.config(text="Factor 2: Something You KNOW - Passed")
            self.progress_bar['value'] += 1  # Update progress bar
            self.button_Factor3.config(state="normal")  # Enable Face Recognition button for next factor
            self.instruction_label1.config(text="Click 'Factor 3' button to continue")
            self.instruction_label2.config(text="")
        else:
            self.step_label.config(text="Factor 2: Something You HAVE - Failed")
            self.instruction_label1.config(text="Authentication Failed at Factor 2 - Access Denied")
            self.instruction_label2.config(text="")
            self.after(2000, self.deny_access)  # Simulate card scan delay
            self.after(2000, self.reset_app)  # Simulate card scan delay

            
    def process_facial_recognition(self):
        # The timer (timer_seconds) only starts once a face has been detected (self.tStart stays None until then).
        # If nobody ever steps up, give up after face_wait_seconds so the game doesn't hang.
        self.tStart = None
        wait_start = time.time()
        face_wait_seconds = config["face_wait_seconds"]
        timer_seconds = config["timer_seconds"]
        # Only run detection/encoding on every Nth frame (the slow part); the frames in
        # between just redraw the most recent results
        recognise_every_n = config["recognise_every_n"]
        frame_number = 0
        # Factor 3 passes as soon as vote_required of the last vote_window recognition passes
        # matched the card holder's face. Each pass is a vote: a pass with no face, or a face
        # that is too far from the card holder's encoding, counts as a miss.
        # match_threshold is looser than the old 0.50 because the vote carries the security.
        match_threshold = config["match_threshold"]
        vote_window = config["vote_window"]
        vote_required = config["vote_required"]
        votes = deque(maxlen=vote_window)
        passed = False
        # Once the vote passes the result is locked in, but the live video carries on for
        # pass_hold_seconds with a banner so the students can see they have been recognised
        pass_hold_seconds = config["pass_hold_seconds"]
        pass_time = 0
        # The vote is 1:1 against the face enrolled for the scanned card; other faces in frame
        # never affect it (they are still boxed amber/red below)
        if self.access_card_ID in self.knownCards:
            claimed_index = self.knownCards.index(self.access_card_ID)
            claimed_encoding = self.knownEncodings[claimed_index]
            claimed_name = self.knownNames[claimed_index]
        else:
            claimed_encoding = None
            claimed_name = "Unauthorised"
        # Log every pass so match_threshold / vote_window / vote_required can be tuned from real data
        log_file = None
        try:
            log_file = open(config["face_log"], "a", newline="")
            log_writer = csv.writer(log_file)
        except OSError:
            log_writer = None
        # Faces from the last recognition pass, as (top, right, bottom, left, name, card, colour)
        # already scaled to the full size frame
        last_faces = []
        box_scale = int(1/self.small_frame_scale)
        # Create the display window once, rather than on every frame
        winname = "Facial Recognition in progress"
        cv2.namedWindow(winname)
        cv2.setWindowProperty(winname, cv2.WND_PROP_TOPMOST, 1)
        while (passed and time.time() - pass_time < pass_hold_seconds) or \
              (not passed and ((self.tStart is None and time.time() - wait_start < face_wait_seconds) or
                               (self.tStart is not None and time.time() - self.tStart < timer_seconds))):
            # Per-frame timer for the fps display (self.tStart is the timer_seconds limit once a face has been seen)
            frame_start = time.time()
            # Grab a frame from the camera
            self.frame = camera.capture_array()
            if frame_number % recognise_every_n == 0:
                # Reset the results on each recognition pass.
                # This ensures that if an authorised person leaves the frame and someone else enters, that access is denied.
                last_faces = []
                # Scale the frame down using small_frame_scale to aid recognition performance
                self.small_frame = cv2.resize(self.frame, (0, 0), fx=self.small_frame_scale, fy=self.small_frame_scale)
                # The camera's "RGB888" frames are BGR in memory; enrolment converts to RGB before
                # encoding, so do the same here (self.frame stays BGR for drawing and display)
                self.small_rgb_frame = cv2.cvtColor(self.small_frame, cv2.COLOR_BGR2RGB)
                # Detect the face boxes in the small_frame
                self.face_locations = face_recognition.face_locations(self.small_rgb_frame, model="hog")
                # compute the facial embeddings for each face bounding box
                self.face_encodings = face_recognition.face_encodings(self.small_rgb_frame, self.face_locations)
                # Distance from each face to the card holder; None means nobody to match against
                if claimed_encoding is not None and len(self.face_encodings) > 0:
                    self.face_distances = face_recognition.face_distance(self.face_encodings, claimed_encoding)
                    # The closest face is taken to be the card holder; the rest are bystanders and ignored
                    self.best_face_index = int(np.argmin(self.face_distances))
                    self.best_distance = float(self.face_distances[self.best_face_index])
                else:
                    self.best_face_index = -1
                    self.best_distance = None
                self.is_match = self.best_distance is not None and self.best_distance <= match_threshold
                # Start the 10s timer on the first pass that sees a face
                if self.tStart is None and len(self.face_locations) > 0:
                    self.tStart = time.time()
                # Votes only start once the timer has, and are locked once passed so a later bad frame can't undo the result
                if self.tStart is not None and not passed:
                    votes.append(self.is_match)
                    if sum(votes) >= vote_required:
                        passed = True
                        pass_time = time.time()
                for i, (top, right, bottom, left) in enumerate(self.face_locations):
                    self.frame_name = "Unauthorised"
                    self.frame_access_card = "No card"
                    self.drawcolour = draw_red
                    if i == self.best_face_index and self.is_match:
                        # Recognised and it is the person for this card
                        self.frame_name = claimed_name
                        self.frame_access_card = self.access_card_ID
                        self.drawcolour = draw_green
                    elif len(self.knownEncodings) > 0:
                        # Otherwise see whether this face is some other enrolled user
                        self.known_distances = face_recognition.face_distance(self.knownEncodings, self.face_encodings[i])
                        self.known_index = int(np.argmin(self.known_distances))
                        if self.known_distances[self.known_index] <= match_threshold and self.knownCards[self.known_index] != self.access_card_ID:
                            # Recognised, but for a different card
                            self.frame_name = self.knownNames[self.known_index]
                            self.frame_access_card = self.knownCards[self.known_index]
                            self.drawcolour = draw_amber
                    # Scale the box back up to the full size frame for displaying
                    last_faces.append((top * box_scale, right * box_scale, bottom * box_scale, left * box_scale,
                                       self.frame_name, self.frame_access_card, self.drawcolour))
                if log_writer is not None:
                    # Brightness of the card holder's face crop (mean and spread) to spot shade/sun problems
                    face_mean = face_std = ""
                    if self.best_face_index >= 0:
                        top, right, bottom, left = self.face_locations[self.best_face_index]
                        face_crop = cv2.cvtColor(self.small_frame[top:bottom, left:right], cv2.COLOR_BGR2GRAY)
                        if face_crop.size > 0:
                            face_mean = round(float(face_crop.mean()), 1)
                            face_std = round(float(face_crop.std()), 1)
                    log_writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), self.access_card_ID,
                                         len(self.face_locations),
                                         "" if self.best_distance is None else round(self.best_distance, 3),
                                         face_mean, face_std, int(self.is_match), sum(votes)])
            frame_number += 1

            for (top, right, bottom, left, name, card, colour) in last_faces:
                # draw the predicted face name on the image - color is in BGR
                cv2.rectangle(self.frame, (left, top), (right, bottom), colour, 2)
                y = top - 15 if top - 15 > 15 else top + 15
                x = bottom + 25 if bottom + 25 > 25 else bottom - 25
                #Put the name above the box
                cv2.putText(self.frame, name, (left, y), cv2.FONT_HERSHEY_SIMPLEX, .8, colour, 2)
                #Put their access card ID below the box
                cv2.putText(self.frame, card, (left, x), cv2.FONT_HERSHEY_SIMPLEX, .8, colour, 2)

            if passed:
                # Banner across the top of the frame while the pass is held on screen
                cv2.rectangle(self.frame, (0, 0), (frame_width, 60), draw_green, -1)
                cv2.putText(self.frame, "FACE RECOGNISED - PASSED", (20, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)

            # display the image to our screen
            #cv2.moveWindow(winname, 40,30)
            cv2.putText(self.frame, str(int(self.fps))+'fps',self.fps_pos,self.fps_font,self.fps_height,self.fps_colour,self.fps_weight)
            cv2.imshow(winname, self.frame)

            
                # Wait for 1 ms and check if 'q' is pressed to quit
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            self.tEnd=time.time()
            self.loopTime=self.tEnd-frame_start
            self.fps=.9*self.fps + .1*(1/self.loopTime)

        cv2.destroyAllWindows()
        if log_file is not None:
            log_file.close()

        if passed:
            self.step_label.config(text="Factor 3: Something You ARE - Passed")
            self.progress_bar['value'] += 1  # Update progress bar
            self.after(2000, self.grant_access)  # 2-second delay before showing success pop-up
        else:
            self.step_label.config(text="Factor 3: Something You ARE - Failed")
            self.instruction_label1.config(text="Authentication Failed at Factor 3 - Access Denied")
            self.after(2000, self.deny_access)  # Simulate card scan delay
            self.after(2000, self.reset_app)  # Simulate card scan delay   
            
    def load_data(self):
        
        self.knownCards=[]
        self.knownNames=[]
        self.knownPINS=[]
        self.knownEncodings=[]
        
        # Iterate over all keys matching the prefix
        for key in redis_client.scan_iter(f"card:*"):
            # Fetch the hash data for the card
            card_data = redis_client.hgetall(key)

            # Decode and deserialize the data
            card = key.decode('utf-8').split(":")[1]  # Extract card number from key
            name = card_data[b'name'].decode('utf-8')
            pin = card_data[b'pin'].decode('utf-8')
            encoding = pickle.loads(card_data[b'encoding'])

            # Append to user_data
            self.knownCards.append(card)
            self.knownNames.append(name)
            self.knownPINS.append(pin)
            self.knownEncodings.append(encoding) 
            
    def read_rfid(self):
        display.PrintText("Place your TAG", FontSize=14)
        display.ShowImage()
        ser = serial.Serial(config["serial_port"])  # Open named port
        ser.baudrate = 9600                # Set baud rate to 9600
        rfid_data = ser.read(12)           # Read 12 characters from serial port to data
        if rfid_data != " ":
            GPIO.output(Buzzer, GPIO.HIGH)
            sleep(.1)
            GPIO.output(Buzzer, GPIO.LOW)
        ser.close()
        self.rfid_data = rfid_data.decode("utf-8")
        display.PrintText("ID : " + self.rfid_data, cords=(4, 8), FontSize=11)
        display.DrawRect()
        display.ShowImage()
        return self.rfid_data
        
    def attract_mode(self, time_seconds, attractmode_stop):
        # Use the event this thread was started with, not self.attractmode_stop: reset_app replaces
        # the latter, which would stop the old thread ever seeing its own stop signal
        while not attractmode_stop.is_set():
            time_between_pixels = time_seconds / pixels_num
            for colour in (pixel_red, pixel_green, pixel_blue):
                for i in range(-1, (pixels_num - 1)):
                    if not attractmode_stop.is_set():
                        pixels[i + 1] = colour
                        pixels[i - 10] = pixel_off
                        pixels.show()
                        sleep(time_between_pixels)
        pixels.fill(pixel_off)
        pixels.show()
        
    # This function is called when access is granted. It plays a movie of the bank vault opening and updates the OLED display
    def grant_access(self):
        display.PrintText("Access granted!", FontSize=14)
        pixels.fill(pixel_green)
        pixels.show()
        self.button_Open_Vault.config(state="normal")  # Enable Face Recognition button for next factor
        self.instruction_label1.config(text="Click 'Open Vault' button to continue")
        self.instruction_label2.config(text="All security checks are complete!") 

        
    def Open_Vault(self):
        access_image = "ffplay -loglevel quiet -hide_banner -noborder -nostats -autoexit " + config["granted_video"]
        system(access_image)
        pixels.fill(pixel_off)
        pixels.show()
        display.NoDisplay()
        self.after(2000, self.reset_app)  # Simulate card scan delay

    # This function is called when access is denied. It plays a movie of an access denied message and updates the OLED display
    def deny_access(self):
        access_image = "ffplay -loglevel quiet -hide_banner -noborder -nostats -autoexit " + config["denied_video"]
        display.PrintText("Access denied!", FontSize=14)
        display.ShowImage()
        GPIO.output(Beacon, GPIO.LOW)
        pixels.fill(pixel_red)
        pixels.show()
        system(access_image)
        GPIO.output(Beacon, GPIO.HIGH)
        pixels.fill(pixel_off)
        pixels.show()
        display.NoDisplay()
        
    def reset_app(self):
        """Reset the app to its initial state."""
        # Reset all UI elements and variables
        self.factor = 0
        self.authentication_failed = False
        self.progress_bar['value'] = 0
        self.attractmode_stop.set()
        self.instruction_label1.config(text="Click 'Factor 1' button to start.")
        self.instruction_label2.config(text="You will be required to pass 3 factors of authentication to open the vault:")
        self.instruction_label3.config(text="Factor 1 = Something you HAVE (An access card)")
        self.instruction_label4.config(text="Factor 2 = Something you KNOW (A PIN)")
        self.instruction_label5.config(text="Factor 3 = Something you ARE (Facial recognition)")
        self.step_label.config(text="")
        self.button_Factor1.config(state="normal")
        self.button_Factor2.config(state="disabled")
        self.button_Factor3.config(state="disabled")
        self.button_Open_Vault.config(state="disabled")
        self.attractmode_stop = Th.Event()
        self.attractmode = Th.Thread(target = self.attract_mode, args=(1, self.attractmode_stop))
        self.attractmode.start()


    # This function displays a message on the RFID HAT OLED display before a card is scanned
    def info_print(self):
        # oled.Whiteoled()
        display.NoDisplay()
        display.DirImage(config["oled_logo"])
        display.DrawRect()
        display.ShowImage()
        sleep(1)
        display.PrintText("Place your TAG", FontSize=14)
        display.ShowImage()
     
    def exit_app(self):
        self.attractmode_stop.set()
        camera.close()
        self.destroy()
        cv2.destroyAllWindows()
        

        
# Run the application
if __name__ == "__main__":
    set_wallpaper(config["vault_wallpaper"])
    redis_client = redis.StrictRedis(host=config["local_host"], port=config["local_port"], decode_responses=False)
    app = AuthApp()
    app.mainloop()
    set_wallpaper(config["exit_wallpaper"])
