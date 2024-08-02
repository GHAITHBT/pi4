import time
import requests
import RPi.GPIO as GPIO
import sys

# GPIO setup
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Define LED GPIO pins for predefined materials
LED_PINS = {
    '3PA0203600091': 18,  # LED for widget1
    '3PA1002300049': 23,  # LED for widget2
    '3PA1002300051': 24,  # LED for widget3
    '5PA80BCMB2102': 25,   # LED for widget4
    '5PA80BCM39102': 12   # LED for widget5
}

# Define button GPIO pins for confirmation
BUTTON_PINS = {
    '3PA0203600091': 5,   # Button for widget1
    '3PA1002300049': 6,   # Button for widget2
    '3PA1002300051': 13,  # Button for widget3
    '5PA80BCMB2102': 19 ,  # Button for widget4
    '5PA80BCM39102': 26   # Button for widget5
}

# GPIO pin for status LED
STATUS_LED_PIN = 16  # Choose an appropriate GPIO pin for status LED

# Setup LEDs
for pin in LED_PINS.values():
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)

# Setup buttons
for pin in BUTTON_PINS.values():
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Setup status LED
GPIO.setup(STATUS_LED_PIN, GPIO.OUT)
GPIO.output(STATUS_LED_PIN, GPIO.HIGH)  # Initially turn on status LED to indicate program running

def fetch_data(car_id):
    try:
        response = requests.get(f'http://10.110.22.161:5000/fetch_jit_components_api?PRODN={car_id}')
        response.raise_for_status()  # Raise an exception for non-200 status codes
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f'Error fetching data: {e}')
        # Flash LEDs three times to indicate error
        for _ in range(3):
            for pin in LED_PINS.values():
                GPIO.output(pin, GPIO.HIGH)
            time.sleep(0.5)
            for pin in LED_PINS.values():
                GPIO.output(pin, GPIO.LOW)
            time.sleep(0.5)
        return None

def verify_leds():
    print("Verifying LEDs...")
    for material, pin in LED_PINS.items():
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(0.2)  # Keep LEDs on for 0.5 seconds
        GPIO.output(pin, GPIO.LOW)
        time.sleep(0.2)  # Keep LEDs off for 0.2 seconds

def compare_materials(car_id):
    start_time = time.time()  # Start time when entering the function
    no_result_time = None     # Initialize time for handling no result condition

    try:
        while True:
            # Check if more than 15 seconds have passed since last result
            if no_result_time and time.time() - no_result_time > 15:
                # Flash LEDs twice to indicate no result after 15 seconds
                for _ in range(2):
                    for pin in LED_PINS.values():
                        GPIO.output(pin, GPIO.HIGH)
                    time.sleep(0.3)
                    for pin in LED_PINS.values():
                        GPIO.output(pin, GPIO.LOW)
                    time.sleep(0.3)
                no_result_time = None  # Reset no_result_time

            # Fetch data from the API
            data = fetch_data(car_id)
            if data is None:
                print("Failed to fetch data from the existing API. Please scan or enter the car ID again.")
                car_id = input("Scan or enter car ID: ").strip()
                start_time = time.time()  # Reset start time on new input
                no_result_time = time.time() if not no_result_time else no_result_time  # Set no_result_time if not set
                continue

            # Reset no_result_time when data is successfully fetched
            no_result_time = None

            # Predefined materials (keys of LED_PINS)
            predefined_materials = LED_PINS.keys()

            # Extract matched materials from the API response
            matched_materials = {component.get('Material', '') for item in data.get('results', []) for component in item.get('BOM', []) if component.get('Material', '') in predefined_materials}

            if not matched_materials:
                print('No matching materials found.')
                # Prompt user to scan another car ID
                print("\nScan or enter new car ID for production use, or press Enter to exit:")
                car_id = input().strip()
                if not car_id:
                    print("No new car ID provided. Exiting.")
                    break
                start_time = time.time()  # Reset start time on new input
                continue

            # Light up LEDs for each matched material
            for material, pin in LED_PINS.items():
                if material in matched_materials:
                    GPIO.output(pin, GPIO.HIGH)
                    print(f'LED for {material} is ON')
                else:
                    GPIO.output(pin, GPIO.LOW)
                    print(f'LED for {material} is OFF')

            # Dictionary to track confirmation status of each material
            confirmed_materials = {material: False for material in matched_materials}

            # Function to handle button press
            def button_pressed(material):
                GPIO.output(LED_PINS[material], GPIO.LOW)  # Turn off LED
                confirmed_materials[material] = True  # Mark material as confirmed

            # Set up button event detection
            for material in matched_materials:
                GPIO.add_event_detect(BUTTON_PINS[material], GPIO.FALLING, callback=lambda x, mat=material: button_pressed(mat), bouncetime=200)

            try:
                # Wait until all materials are confirmed
                while not all(confirmed_materials.values()):
                    time.sleep(0.1)
            except Exception as e:
                print(f"Error occurred: {e}")
                break
            finally:
                # Clean up event detection
                for material in matched_materials:
                    GPIO.remove_event_detect(BUTTON_PINS[material])

            # Ask if the user wants to scan or enter a new car ID for production use
            print("\nScan or enter new car ID for production use, or press Enter to exit:")
            car_id = input().strip()
            if not car_id:
                print("No new car ID provided. Exiting.")
                break
            start_time = time.time()  # Reset start time on new input
    finally:
        GPIO.output(STATUS_LED_PIN, GPIO.LOW)  # Turn off status LED
        GPIO.cleanup()  # Clean up GPIO pins when done

def main():
    try:
        verify_leds()  # Verify LEDs at program start
        print("Scan or enter car ID:")
        car_id = input().strip()  # Assuming input comes from scanner or other input device
        compare_materials(car_id)
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        GPIO.output(STATUS_LED_PIN, GPIO.LOW)  # Turn off status LED before cleanup
        GPIO.cleanup()  # Clean up GPIO pins when done

if __name__ == '__main__':
    main()
