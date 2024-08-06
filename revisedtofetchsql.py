import RPi.GPIO as GPIO
import socket
import requests
import time
import threading
import mysql.connector

# Get the hostname of the Raspberry Pi
hostname = socket.gethostname()

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

STATUS_LED_PIN = 16

# Fetch configuration from MySQL
def fetch_configuration(machine_name):
    try:
        connection = mysql.connector.connect(
            host='localhost',
            user='root',
            password='Passw0rd123',
            database='PickByLight'
        )
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT * FROM raspberry_pi_configurations WHERE machine_name = %s', (machine_name,))
        config = cursor.fetchone()
        if config:
            return config
        else:
            print(f"No configuration found for machine_name: {machine_name}")
            return None
    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        return None
    finally:
        cursor.close()
        connection.close()

# Load configuration
config = fetch_configuration(hostname)
if config:
    LED_PINS = config['led_pins']
    BUTTON_PINS = config['button_pins']
else:
    LED_PINS = {}
    BUTTON_PINS = {}

GPIO.setup(STATUS_LED_PIN, GPIO.OUT)
GPIO.output(STATUS_LED_PIN, GPIO.HIGH)

# Initialize GPIO
for pin in LED_PINS.values():
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)

for pin in BUTTON_PINS.values():
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def activate_led(material):
    if material in LED_PINS:
        GPIO.output(LED_PINS[material], GPIO.HIGH)
        return {'status': 'LED activated'}
    return {'error': 'Invalid material'}

def deactivate_led(material):
    if material in LED_PINS:
        GPIO.output(LED_PINS[material], GPIO.LOW)
        return {'status': 'LED deactivated'}
    return {'error': 'Invalid material'}

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
    try:
        response = requests.post(f'http://10.110.10.204:5001/confirmation_material', json={'material': material, 'hostname': hostname})
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error sending confirmation: {e}")

def check_network():
    try:
        result = subprocess.run(['ping', '-c', '1', '10.110.10.204'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.returncode == 0
    except Exception:
        return False

def run_flask():
    from flask import Flask, request, jsonify
    app = Flask(__name__)

    @app.route('/activate_led', methods=['POST'])
    def activate_led_route():
        data = request.json
        material = data.get('material')
        return jsonify(activate_led(material))

    @app.route('/deactivate_led', methods=['POST'])
    def deactivate_led_route():
        data = request.json
        material = data.get('material')
        return jsonify(deactivate_led(material))

    app.run(host='0.0.0.0', port=5000)

def main():
    try:
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        verify_leds()
        for pin in BUTTON_PINS.values():
            GPIO.add_event_detect(pin, GPIO.FALLING, callback=button_callback, bouncetime=200)

        while True:
            if check_network():
                GPIO.output(STATUS_LED_PIN, GPIO.HIGH)
                time.sleep(1)
            else:
                GPIO.output(STATUS_LED_PIN, GPIO.LOW)
                time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        GPIO.output(STATUS_LED_PIN, GPIO.LOW)
        GPIO.cleanup()

if __name__ == '__main__':
    main()
