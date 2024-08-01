import json
import os
import socket
import time
import requests
import RPi.GPIO as GPIO

# GPIO setup
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Define LED GPIO pins (example)
LED_PINS = {
    'material1': 17,  # Replace with actual GPIO pin numbers
    'material2': 27,
    'material3': 22
}

# Define button GPIO pin
BUTTON_PIN = 4

# Setup LEDs
for pin in LED_PINS.values():
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)

# Setup button
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def get_machine_name():
    """Get the hostname of the machine."""
    return socket.gethostname()

def load_predefined_materials(machine_name):
    """Load predefined materials based on the machine name."""
    config_path = os.path.join('configurations', f'config_{machine_name}.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
            return config.get('predefined_materials', [])
    return []

def compare_materials(car_id, hostname):
    predefined_materials = load_predefined_materials(hostname)
    if not predefined_materials:
        print('No configuration file found for the given hostname.')
        return

    response = requests.get(f'http://localhost:5000/fetch_jit_components_api?PRODN={car_id}')
    if response.status_code != 200:
        print('Failed to fetch data from the existing API.')
        return

    data = response.json()
    matched_materials = {component.get('Material', '') for item in data.get('results', []) for component in item.get('BOM', []) if component.get('Material', '') in predefined_materials}

    if not matched_materials:
        print('No matching materials found.')
        return

    # Light up LEDs for each matched material
    for material, pin in LED_PINS.items():
        if material in matched_materials:
            GPIO.output(pin, GPIO.HIGH)
            print(f'LED for {material} is ON')
        else:
            GPIO.output(pin, GPIO.LOW)
            print(f'LED for {material} is OFF')

    # Wait for button press for each material
    for material in matched_materials:
        print(f'Please confirm for {material} by pressing the button.')
        while GPIO.input(BUTTON_PIN) == GPIO.HIGH:
            time.sleep(0.1)  # Wait for button press
        print(f'Button pressed for {material}.')
        # Turn off LED after confirmation
        GPIO.output(LED_PINS.get(material, -1), GPIO.LOW)

def main():
    print("Enter car ID:")
    car_id = input().strip()

    hostname = get_machine_name()
    print(f"Detected hostname: {hostname}")

    compare_materials(car_id, hostname)

if __name__ == '__main__':
    main()
