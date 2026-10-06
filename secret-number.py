import random
import tkinter as tk
from tkinter import messagebox
from tkinter.font import Font
import sys
from app_config import load_config

# Settings come from ~/.config/can-you-break-the-bank/can-you-break-the-bank.cfg
config = load_config()
num_digits = config["pin_length"]
num_guesses = config["max_guesses"]
time_limit_seconds = config["time_limit_seconds"]


# variables
green = '#27e512'
yellow = '#e8ef0e'
gray = '#4c4c4c'
font = 'Verdana, 38'
numbers = []

class NumberWordleGame:
    def __init__(self, root, num_digits, secret_number):
        self.root = root
        self.root.title("Factor 2")

        self.HdgFont = Font(family="Quicksand", size=24, weight="bold")
        self.SubHdgFont = Font(family="Quicksand", size=18, weight="bold")
        self.NormalFont = Font(family="Quicksand", size=10, weight="bold")

        self.num_digits = num_digits
        self.secret_number = secret_number
        
        self.attempts = 0
        self.guesses = []
        
        # Timer variables
        self.remaining_ms = time_limit_seconds * 1000  # time limit in milliseconds
        self.timer_running = True
        
        # Timer display at the top
        self.timer_label = tk.Label(root, text="Time Remaining:", font=self.HdgFont, fg="red")
        self.timer_label.pack()
        self.timer_label = tk.Label(root, text=f"{time_limit_seconds // 60:02d}:{time_limit_seconds % 60:02d}.000", font=self.HdgFont, fg="red")
        self.timer_label.pack(pady=10)

        self.label = tk.Label(root, text=f"Enter {self.num_digits} digit access code:", font=self.HdgFont)
        self.label.pack(pady=10)

        self.entry = tk.Entry(root, font=self.SubHdgFont)
        self.entry.pack(pady=10)
        
        self.submit_button = tk.Button(root, text="Submit", padx=20, pady=20, command=self.check_guess, font=self.SubHdgFont, bg="green", foreground="white")
        self.submit_button.pack(pady=10)

        self.guess_frame = tk.Frame(root)
        self.guess_frame.pack()

        self.guess_label = tk.Label(self.guess_frame, text="Grey = Digit incorrect", font=self.SubHdgFont, bg="grey")
        self.guess_label.pack()
        self.guess_label = tk.Label(self.guess_frame, text="Amber = Digit correct, wrong position", font=self.SubHdgFont, bg="orange")
        self.guess_label.pack()
        self.guess_label = tk.Label(self.guess_frame, text="Green = Digit and position correct", font=self.SubHdgFont, bg="green") 
        self.guess_label.pack()
        self.guess_label = tk.Label(self.guess_frame, text="Feedback:", font=self.SubHdgFont)
        self.guess_label.pack()
        self.guess_remaining_label = tk.Label(self.guess_frame, text=f"Attempts: {self.attempts}/{num_guesses}", font=self.SubHdgFont)
        self.guess_remaining_label.pack(pady=10)

        
        # Start the countdown timer
        self.update_timer()

    def update_timer(self):
        """Update the countdown timer display"""
        if not self.timer_running:
            return
            
        if self.remaining_ms <= 0:
            # Time's up - exit with error
            self.timer_label.config(text="00:00.000")
            messagebox.showerror("Time's Up!", "You ran out of time!")
            self.root.destroy()
            sys.exit(0)
        
        # Calculate minutes, seconds, and milliseconds
        minutes = self.remaining_ms // 60000
        seconds = (self.remaining_ms % 60000) // 1000
        milliseconds = self.remaining_ms % 1000
        
        # Update display
        time_str = f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
        self.timer_label.config(text=time_str)
        
        # Decrease by 10ms for smooth animation
        self.remaining_ms -= 10
        
        # Schedule next update in 10ms
        self.root.after(10, self.update_timer)

    def generate_random_number(self, num_digits):
        return ''.join(random.sample('0123456789', num_digits))

    def compare_numbers(self, guess):
        feedback = []

        for i in range(self.num_digits):
            if guess[i] == self.secret_number[i]:
                feedback.append(('green', guess[i]))
            elif guess[i] in self.secret_number:
                feedback.append(('orange', guess[i]))
            else:
                feedback.append(('gray', guess[i]))

        return feedback

    def check_guess(self):
        user_guess = self.entry.get()

        if len(user_guess) != self.num_digits or not user_guess.isdigit():
            messagebox.showinfo("Invalid Input", f"Please enter a valid {self.num_digits}-digit number.")
            return

        feedback = self.compare_numbers(user_guess)
        self.guesses.append((user_guess, feedback))
        self.update_guess_display()

        if user_guess == self.secret_number:
            self.timer_running = False  # Stop the timer
            messagebox.showinfo("Success", f"You have entered the correct number {user_guess}!\nIt took you {self.attempts + 1} attempts.")
            self.root.destroy()
            sys.exit(1)
        else:
            self.attempts += 1
            self.entry.delete(0, tk.END)
        if self.attempts == num_guesses:
            self.timer_running = False  # Stop the timer
            messagebox.showinfo("Failed!", f"You have reached the maximum of {num_guesses} attempts.")
            self.root.destroy()
            sys.exit(0)

    def update_guess_display(self):
        # Earlier guesses are already on screen from previous calls, so only add the newest row
        guess, feedback = self.guesses[-1]
        guess_feedback_frame = tk.Frame(self.guess_frame)
        guess_feedback_frame.pack()

        for color, digit in feedback:
            label = tk.Label(guess_feedback_frame, text=digit, width=3, height=1, font=self.SubHdgFont, relief='solid', bg=color)
            label.pack(side=tk.LEFT, padx=2)

                
if __name__ == "__main__":
    secret_number = sys.argv[1]
    root = tk.Tk()
    game = NumberWordleGame(root, num_digits, secret_number)
    root.mainloop()
