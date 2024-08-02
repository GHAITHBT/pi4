from flask import Flask, request, jsonify
import RPi.GPIO as GPIO
import socket
import requests
import time
import threading

app = Flask(__name__)

# Get the hostname of the Raspberry Pi
hostname = socket.gethostname()

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

LED_PINS = {
    '3PA0203600091': 18,
    '3PA1002300049': 23,
    '3PA1002300051': 24,
    '5PA80BCMB2102': 25,
    '5PA80BCM39102': 12
}

BUTTON_PINS = {
    '3PA0203600091': 5,
    '3PA1002300049': 6,
    '3PA1002300051': 13,
    '5PA80BCMB2102': 19,
    '5PA80BCM39102': 26
}

STATUS_LED_PIN = 16

# Initialize GPIO
for pin in LED_PINS.values():
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)

for pin in BUTTON_PINS.values():
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

GPIO.setup(STATUS_LED_PIN, GPIO.OUT)
GPIO.output(STATUS_LED_PIN, GPIO.HIGH)

@app.route('/activate_led', methods=['POST'])
def activate_led():
    data = request.json
    material = data.get('material')
    if material in LED_PINS:
        GPIO.output(LED_PINS[material], GPIO.HIGH)
        return jsonify({'status': 'LED activated'}), 200
    return jsonify({'error': 'Invalid material'}), 400

@app.route('/deactivate_led', methods=['POST'])
def deactivate_led():
    data = request.json
    material = data.get('material')
    if material in LED_PINS:
        GPIO.output(LED_PINS[material], GPIO.LOW)
        return jsonify({'status': 'LED deactivated'}), 200
    return jsonify({'error': 'Invalid material'}), 400

def verify_leds():
    print("Verifying LEDs...")
    for material, pin in LED_PINS.items():
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(0.2)
        GPIO.output(pin, GPIO.LOW)
        time.sleep(0.2)

def button_callback(channel):
    material = [m for m, p in BUTTON_PINS.items() if p == channel][0]
    GPIO.output(LED_PINS[material], GPIO.LOW)
    # Change to the server's IP address
    try:
        response = requests.post(f'http://10.110.22.161:5001/confirm_material', json={'material': material, 'hostname': hostname})
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error sending confirmation: {e}")

def run_flask():
    app.run(host='0.0.0.0', port=5000)

def main():
    try:
        # Start Flask in a separate thread
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        verify_leds()
        for pin in BUTTON_PINS.values():
            GPIO.add_event_detect(pin, GPIO.FALLING, callback=button_callback, bouncetime=200)

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        GPIO.output(STATUS_LED_PIN, GPIO.LOW)
        GPIO.cleanup()

if __name__ == '__main__':
    main()
