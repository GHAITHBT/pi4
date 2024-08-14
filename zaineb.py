import RPi.GPIO as GPIO
import time
import socket

# Setup
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Define the GPIO pins for LEDs and buttons
material_pins = {
    'material1': {'led': 17, 'button': 27},  # Example GPIO pins
    'material2': {'led': 22, 'button': 23},
    'material3': {'led': 24, 'button': 25},
    # Add more materials as needed
}

# Set up GPIO pins
for material, pins in material_pins.items():
    GPIO.setup(pins['led'], GPIO.OUT)
    GPIO.setup(pins['button'], GPIO.IN, pull_up_down=GPIO.PUD_UP)

def reset_leds():
    for pins in material_pins.values():
        GPIO.output(pins['led'], GPIO.LOW)

def wait_for_confirmation(material):
    led_pin = material_pins[material]['led']
    button_pin = material_pins[material]['button']

    GPIO.output(led_pin, GPIO.HIGH)
    while GPIO.input(button_pin) == GPIO.HIGH:
        time.sleep(0.1)  # Debouncing
    GPIO.output(led_pin, GPIO.LOW)
    print(f"Material {material} confirmed.")

def main():
    reset_leds()
    
    # Server setup
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('0.0.0.0', 5000))  # Listening on all interfaces
    server_socket.listen(5)
    
    print("Waiting for connection...")
    
    try:
        while True:
            client_socket, addr = server_socket.accept()
            print(f"Connection from {addr}")
            material_code = client_socket.recv(1024).decode('utf-8').strip()
            
            if material_code in material_pins:
                wait_for_confirmation(material_code)
            else:
                print(f"Unknown material code: {material_code}")
            
            client_socket.close()
    
    except KeyboardInterrupt:
        print("Program interrupted")
    
    finally:
        GPIO.cleanup()
        server_socket.close()

if __name__ == "__main__":
    main()
