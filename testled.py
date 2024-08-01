import RPi.GPIO as GPIO
import time

# Set up the GPIO pin
LED_PIN = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_PIN, GPIO.OUT)

try:
    # Turn on the LED
    GPIO.output(LED_PIN, GPIO.HIGH)
    print("LED is ON")
    
    # Keep the LED on for 5 seconds
    time.sleep(5)
    
    # Turn off the LED
    GPIO.output(LED_PIN, GPIO.LOW)
    print("LED is OFF")
    
finally:
    # Clean up the GPIO settings
    GPIO.cleanup()
