#!/usr/bin/python3
import tkinter as tk
from tkinter import *
from tkinter import messagebox
from tkinter.font import Font
from tkinter import ttk
from tkinter import StringVar
from oled_091 import SSD1306
import time
from time import sleep
import serial
import RPi.GPIO as GPIO
from picamera2 import Picamera2
from PIL import Image, ImageDraw, ImageTk
import cv2
import face_recognition
import pickle
import redis
import numpy as np
import dbus

# Setup the GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(17, GPIO.OUT)

# These values are common whether using PiCamera or Webcam
frame_width = 640
frame_height = 480

# If using a raspberry pi camera on the CSI interface
# Start of picamera specific config. Comment out if using a webcam or other camera.
camera = Picamera2()
video_config = camera.create_video_configuration(main={"size": (frame_width, frame_height), "format": "RGB888"})
camera.configure(video_config)
#camera.set_controls({
#    "AeEnable": True,
#    "ExposureTime": 10000,
#    "AnalogueGain": 2.0,
#    "Brightness": 0.5
#   })
camera.start()

# End of pi camera specific setup.

# If using a webcam on a USB port uncomment this section
# camera = cv2.VideoCapture('/dev/video0')
# camera.set(cv2.CAP_PROP_FRAME_WIDTH, frame_width)
# camera.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_height)

#Initialize a few variables
#Number of training images to capture. More images = better training but longer to do.
training_images=10
#These are used for writing frames per second and images captured onto the frame
fps=0
fps_pos=(30,60)
img_count_pos=(30,30)
fps_font=cv2.FONT_HERSHEY_SIMPLEX
fps_height=0.5
fps_colour=(0,255,0)
fps_weight=1
# This are used for the location of the faces
top=0
bottom=0
right=0
left=0
face_sizes=np.array([0])
largest_face=0
#This is used to store all of the face encodings before writing to pickle file
faces_data=[]

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

class AddNewUserApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Add new employee")
        self.user_data={}
        self.knownCards={}
        self.knownNames={}
        self.knownPINS={}
        self.knownEncodings={}
             
        self.geometry('800x600+0+0')
        self.resizable(False, False)

        self.dataframe = Frame(self.master, padx=10, pady=10, width=750, height=500)
        self.dataframe.pack_propagate(False)
        self.dataframe.pack()

        self.infoframe = Frame(self.master, padx=10, pady=10, width=750, height=200, background="white")
        self.infoframe.pack_propagate(False)
        self.infoframe.pack(expand=False)

        self.HdgFont = Font(family="Quicksand", size=24, weight="bold")
        self.SubHdgFont = Font(family="Quicksand", size=18, weight="bold")

        self.employee_name = ""
        self.str_first_pin = ""
        self.str_second_pin = ""
        self.access_card_ID = ""

        self.heading_label = Label(self.dataframe, text="Welcome to A.N. Other Bank", font=self.HdgFont)
        self.subhead_label = Label(self.dataframe, text="New employee setup", font=self.SubHdgFont)
        self.heading_label.grid(row=0, column=0, columnspan=5)
        self.subhead_label.grid(row=1, column=0, columnspan=5)

        self.access_card_label = Label(self.dataframe, text="Access Card: ", font=self.SubHdgFont)
        self.access_card_ID_label = Label(self.dataframe, text="", font=self.SubHdgFont)

        self.name_label = Label(self.dataframe, text="Enter Name: ", font=self.SubHdgFont)
        self.name_entry = Entry(self.dataframe, textvariable=self.employee_name, width=35, borderwidth=5, font=self.SubHdgFont)

        self.pin_label = Label(self.dataframe, text="Enter 4 digit PIN: ", font=self.SubHdgFont)
        self.pin_entry = Entry(self.dataframe, textvariable=self.str_first_pin, show="*", width=35, borderwidth=5, font=self.SubHdgFont)

        self.second_pin_label = Label(self.dataframe, text="Re-enter PIN: ", font=self.SubHdgFont)
        self.second_pin_entry = Entry(self.dataframe, textvariable=self.str_second_pin, show="*", width=35, borderwidth=5, font=self.SubHdgFont)

        self.instruction_label = Label(self.infoframe, text="Click 'Add User' button to start.", fg="black", bg="white", wraplength=700, font=self.HdgFont)
        self.instruction_label.pack()

        self.access_card_label.grid(row=2, column=0, columnspan=1, padx=0, pady=0)
        self.access_card_ID_label.grid(row=2, column=1, columnspan=1, padx=0, pady=0)

        self.name_label.grid(row=3, column=0, columnspan=1, padx=0, pady=0)
        self.name_entry.grid(row=3, column=1, columnspan=3, padx=0, pady=0)

        self.pin_label.grid(row=4, column=0, columnspan=1, padx=0, pady=0)
        self.pin_entry.grid(row=4, column=1, columnspan=3, padx=0, pady=0)

        self.second_pin_label.grid(row=5, column=0, columnspan=1, padx=0, pady=0)
        self.second_pin_entry.grid(row=5, column=1, columnspan=3, padx=0, pady=0)

        # Define buttons
        self.button_card = Button(self.dataframe, text="Add user", padx=50, pady=20, command=self.start_add_user, bg="green", foreground="white", font=self.SubHdgFont)
        self.button_submit = Button(self.dataframe, state='disabled', text="Submit", padx=50, pady=20, command=self.submit_details, bg="green", foreground="white", font=self.SubHdgFont)
        self.button_save = Button(self.dataframe, state='disabled', text="Save", padx=50, pady=20, command=self.save_data, bg="green", foreground="white", font=self.SubHdgFont)
        self.button_exit = Button(self.dataframe, text="Exit", padx=50, pady=20, command=self.exit_app, bg="red", font=self.SubHdgFont)

        # Place buttons
        self.button_card.grid(row=8, column=0, columnspan=1)
        self.button_submit.grid(row=8, column=1, columnspan=1)
        self.button_save.grid(row=8, column=2, columnspan=1)
        self.button_exit.grid(row=8, column=3, columnspan=1)
        
    def start_add_user(self):
        self.instruction_label.config(text="Scan an access card on the reader")
        self.after(2000, self.read_card)  # Simulate card scan delay
        self.button_card.config(state='disabled')
            
    def read_rfid(self):
        display.PrintText("Place your TAG", FontSize=14)
        display.ShowImage()
        ser = serial.Serial("/dev/ttyS0")  # Open named port
        ser.baudrate = 9600                # Set baud rate to 9600
        rfid_data = ser.read(12)           # Read 12 characters from serial port to data
        if rfid_data != " ":
            GPIO.output(17, GPIO.HIGH)
            sleep(.1)
            GPIO.output(17, GPIO.LOW)
        ser.close()
        self.rfid_data = rfid_data.decode("utf-8")
        return self.rfid_data

    def read_card(self):
        #                                       self.load_data()
        self.access_card_ID = self.read_rfid()
        display.PrintText("ID : " + self.access_card_ID, cords=(4, 8), FontSize=11)
        display.DrawRect()
        display.ShowImage()
        # Delete the existing hash for this card if it exists
        card_key = f"card:{self.access_card_ID}"
        if redis_client.exists(card_key):
            redis_client.delete(card_key)
        
        self.access_card_ID_label.config(text=self.access_card_ID)
        self.instruction_label.config(text="New access card has been scanned. Now enter name for the card and a PIN twice. Click 'Submit' to confirm")
        self.button_submit.config(state='normal')              

    def submit_details(self):
        self.employee_name = self.name_entry.get()
        str_first_pin = self.pin_entry.get()
        str_second_pin = self.second_pin_entry.get()
        self.access_card_ID_label.config(text = "")
        self.name_entry.delete(0, END)
        self.pin_entry.delete(0, END)
        self.second_pin_entry.delete(0, END)

        if len(self.employee_name) == 0:
            messagebox.showerror("Invalid Input", "Name cannot be blank")
        elif len(str_first_pin) != 4 or not str_first_pin.isdigit():
            messagebox.showerror("Invalid Input", "Please enter a valid 4-digit number for the 1st PIN.")
        elif len(str_second_pin) != 4 or not str_second_pin.isdigit():
            messagebox.showerror("Invalid Input", "Please enter a valid 4-digit number for the 2nd PIN.")
        else:
            if str_first_pin != str_second_pin:
                messagebox.showerror("Invalid Input", "PIN entries do not match, try again")
            else:
                self.employee_pin = str_first_pin
                self.button_submit.config(state='disabled')
                self.recognise_face()

    def recognise_face(self):
        # Setup the initial window and instruction label
        self.instruction_label.config(text="Starting facial recognition. Look at the camera!")
        capture_window = Toplevel(self.master)
        capture_window.title("Recognising face...")
        capture_window.geometry(f"{frame_width + 1150}x{frame_height}+0+620")  # Increase width for columns

        image_label = Label(capture_window)
        image_label.grid(row=0, column=0)  # Display the image on the left side

        # Create a Treeview widget for displaying facial landmarks in two columns
        landmarks_tree = ttk.Treeview(capture_window, columns=("Feature", "Coordinates"), show="headings", height=20)
        landmarks_tree.heading("Feature", text="Feature")
        landmarks_tree.heading("Coordinates", text="Coordinates")
        landmarks_tree.column("Feature", width=100, anchor="w")
        landmarks_tree.column("Coordinates", width=1150, anchor="w")
        landmarks_tree.grid(row=0, column=1, padx=10, pady=10)
 
        frame_count = 0
        i=0
        fps=0
        while len(faces_data) < training_images:
            tStart=time.time()
            #camera.read if using USB webcam
            #(success, frame)=camera.read()
            #camera.capture_array() if using Picamera
            frame = camera.capture_array()
            # Convert the frame from BGR to RGB (face_recognition expects RGB)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            # detect the (x, y, w, h)-coordinates of the bounding boxes
            # corresponding to each face in the input image
            face_boxes = face_recognition.face_locations(frame, model="hog")
            encodings = face_recognition.face_encodings(frame, face_boxes)
            face_landmarks_list = face_recognition.face_landmarks(frame, face_locations=face_boxes)
            
            #Calculate the area of each face box, and choose only the largest for encoding
            #for (top, right, bottom, left) in face_boxes:
              #  width = right - left
             #   height = bottom - top
             #   area = width * height
             #   np.append(face_sizes, area)
              #  print("Found a face with area of ", area)
            
            #largest_face = np.max(face_sizes)
            #print("The largest face is in index ", largest_face)

            #If there are any faces in the captured frame then loop through them and add encodings into faces_data
            for (top, right, bottom, left), face_encoding in zip(face_boxes, encodings):           
                i=i+1
                faces_data.append(face_encoding)
                #Draw a rectangle onto the image where the face is.
                cv2.rectangle(frame, (left, top), (right, bottom), (0,255,0), 2)
                
            #Draw the face landmarks onto the image
            pil_image = Image.fromarray(frame)
            d = ImageDraw.Draw(pil_image)
            landmarks_tree.delete(*landmarks_tree.get_children())  # Clear previous landmarks

            #for face_landmarks in face_landmarks_list:
                # Let's trace out each facial feature in the image with a line!
                #for facial_feature in face_landmarks.keys():
                    #d.line(face_landmarks[facial_feature], fill=(255,0,0), width=3)
            
            for face_landmarks in face_landmarks_list:
                for feature, points in face_landmarks.items():
                    d.line(points, fill=(255, 0, 0), width=3)
                    landmarks_tree.insert("", "end", values=(feature, points))  # Insert key-value pairs in separate columns
            
            #Convert PIL array back to image.
            frame = np.array(pil_image)    
             #Display the frame to the screen.
            cv2.putText(frame, 'Training image '+str(len(faces_data))+'/'+str(int(training_images))+' captured',img_count_pos,fps_font,fps_height,fps_colour,fps_weight)
            cv2.putText(frame, str(int(fps))+'fps',fps_pos,fps_font,fps_height,fps_colour,fps_weight)
           
            # Convert frame to Image and display it
            img = Image.fromarray(frame)
            imgtk = ImageTk.PhotoImage(image=img)
            image_label.imgtk = imgtk
            image_label.configure(image=imgtk)
            frame_count += 1
            tEnd=time.time()
            loopTime=tEnd-tStart
            fps=.9*fps + .1*(1/loopTime)
            capture_window.update()
        capture_window.destroy()
        self.average_encoding = np.mean(faces_data, axis=0)
        #for encoding in faces_data:
        #self.knownCards.append(self.access_card_ID)
        #self.knownNames.append(self.employee_name)
        #self.knownPINS.append(self.employee_pin)
        #self.knownEncodings.append(average_encoding)
        self.instruction_label.config(text="Facial recognition complete. Press 'Save' to save this face")
        self.button_save.config(state='normal')
        
    def save_data(self):
        """
        This function saves the data (from the instance variables) to REDIS.
        """
        self.instruction_label.config(text="Writing face encoding to the database...")
        
        card_key=f"card:{self.access_card_ID}"

        # Store the data as a Redis hash
        redis_client.hset(card_key, mapping={
            'name': self.employee_name,
            'pin': self.employee_pin,
            'encoding': pickle.dumps(self.average_encoding)  # Serialize the encoding to store it
        })
        # Store the card number under the encoding key (to enable encoding-based retrieval)
        #redis_client.sadd(pickle.dumps(self.average_encoding), self.access_card_ID)

        self.button_save.config(state='disabled')
        self.button_card.config(state='normal')
        sleep(2)
        self.reset_buttons()
        
    def reset_buttons(self):
        """
        Resets the buttons to their initial state.
        Customize as needed to match the initial state of each button.
        """      
        self.employee_name = ""
        self.str_first_pin = ""
        self.str_second_pin = ""
        self.access_card_ID = ""
        faces_data.clear()
        
        self.instruction_label.config(text="Click 'Add User' button to start.", fg="black", bg="white", wraplength=700, font=self.HdgFont)
        self.instruction_label.pack()
 
        # Define buttons
        self.button_card.config(state='normal')
        self.button_submit.config(state='disabled')
        self.button_save.config(state='disabled')
        self.button_exit.config(state='normal')

        # Place buttons
        #self.button_card.grid(row=8, column=0, columnspan=1)
        #self.button_submit.grid(row=8, column=1, columnspan=1)
        #self.button_save.grid(row=8, column=2, columnspan=1)
        #self.button_exit.grid(row=8, column=3, columnspan=1)

    def exit_app(self):
        sleep(2)
        camera.close()
        self.destroy()
        display.NoDisplay()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    set_wallpaper("/home/pi/PiFace/Images/facial_recognition.jpg")
    redis_client = redis.StrictRedis(host='localhost', port=6379, decode_responses=False)
    display = SSD1306()
    app = AddNewUserApp()
    app.mainloop()
    set_wallpaper("/home/pi/PiFace/Images/CanYouBreakTheBank.jpg")
