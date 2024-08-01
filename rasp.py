import time
import requests
import RPi.GPIO as GPIO

# GPIO setup
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Define LED GPIO pins for predefined materials
LED_PINS = {
    'widget1': 17,  # LED for widget1
    'widget2': 27,  # LED for widget2
    'widget3': 22   # LED for widget3
}

# Define button GPIO pin
BUTTON_PIN = 4

# Setup LEDs
for pin in LED_PINS.values():
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)

# Setup button
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def compare_materials(car_id):
    # Predefined materials (keys of LED_PINS)
    predefined_materials = LED_PINS.keys()

    # Fetch data from the API
    response = requests.get(f'http://localhost:5000/fetch_jit_components_api?PRODN={car_id}')
    if response.status_code != 200:
        print('Failed to fetch data from the existing API.')
        return

    data = response.json()

    # Extract matched materials from the API response
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
    compare_materials(car_id)
    GPIO.cleanup()  # Clean up GPIO pins when done

if __name__ == '__main__':
    main()
