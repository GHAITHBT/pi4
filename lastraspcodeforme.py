from flask import Flask, request, jsonify
import RPi.GPIO as GPIO
import socket
import requests
import time
import threading
import mysql.connector
from mysql.connector import pooling
import json
import subprocess
import socketio  # Add SocketIO client

app = Flask(__name__)

hostname = socket.gethostname()
sio = socketio.Client()  # Create SocketIO client instance

# Database configuration
db_config = {
    'host': '10.110.10.204',
    'user': 'root',
    'password': 'Passw0rd123',
    'database': 'PickByLight'
}

# Set up database connection pool
mysql_pool = pooling.MySQLConnectionPool(
    pool_name="mysql_pool",
    pool_size=5,
    **db_config
)

def get_db_connection():
    return mysql_pool.get_connection()

# Get the IP address of the Raspberry Pi
def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Initialize GPIO
def initialize_gpio(config):
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    led_pins = config.get('led_pins', {})
    button_pins = config.get('button_pins', {})
    status_led_pin = config.get('status_led_pin', 0)

    for pin in led_pins.values():
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)

    for pin in button_pins.values():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    GPIO.setup(status_led_pin, GPIO.OUT)
    GPIO.output(status_led_pin, GPIO.HIGH)

def fetch_configuration():
    ip_address = get_ip_address()
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT * FROM rasp_pi_configurations WHERE ip_address = %s', (ip_address,))
        config = cursor.fetchone()
        if config:
            # Convert JSON fields to Python objects
            config['led_pins'] = json.loads(config['led_pins'])
            config['button_pins'] = json.loads(config['button_pins'])
            config['predefined_materials'] = json.loads(config['predefined_materials'])
            return config
        return {}
    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        return {}
    finally:
        cursor.close()
        connection.close()

@app.route('/activate_led', methods=['POST'])
def activate_led():
    data = request.json
    material = data.get('material')
    if material in led_pins:
        GPIO.output(led_pins[material], GPIO.HIGH)
        return jsonify({'status': 'LED activated'}), 200
    return jsonify({'error': 'Invalid material'}), 400

@app.route('/deactivate_led', methods=['POST'])
def deactivate_led():
    data = request.json
    material = data.get('material')
    if material in led_pins:
        GPIO.output(led_pins[material], GPIO.LOW)
        return jsonify({'status': 'LED deactivated'}), 200
    return jsonify({'error': 'Invalid material'}), 400

def verify_leds():
    print("Verifying LEDs...")
    for material, pin in led_pins.items():
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(0.2)
        GPIO.output(pin, GPIO.LOW)
        time.sleep(0.2)

def button_callback(channel):
    material = [m for m, p in button_pins.items() if p == channel][0]
    GPIO.output(led_pins[material], GPIO.LOW)
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

# Blink the status LED twice when configuration updates
def blink_status_led():
    for _ in range(2):
        GPIO.output(status_led_pin, GPIO.HIGH)
        time.sleep(0.2)
        GPIO.output(status_led_pin, GPIO.LOW)
        time.sleep(0.2)

# SocketIO event handler for configuration updates
@sio.event
def configuration_update(data):
    print(f"Configuration update received: {data}")
    # Blink status LED twice
    blink_status_led()
    
    # Fetch and apply the new configuration
    new_config = fetch_configuration()
    if new_config:
        global led_pins, button_pins, status_led_pin
        led_pins = new_config.get('led_pins', {})
        button_pins = new_config.get('button_pins', {})
        status_led_pin = new_config.get('status_led_pin', 0)

        # Reinitialize the GPIO with the new config
        initialize_gpio(new_config)
        print("Configuration updated successfully.")
    else:
        print("Failed to fetch new configuration.")

# Connect to the Flask server via SocketIO
def connect_socketio():
    try:
        sio.connect('http://10.110.10.204:5001')
        print("Connected to Flask server via SocketIO.")
    except Exception as e:
        print(f"Failed to connect to Flask server: {e}")

def run_flask():
    app.run(host='0.0.0.0', port=5000)

def main():
    config = fetch_configuration()
    if not config:
        print("No configuration found for this Raspberry Pi.")
        return

    global led_pins, button_pins, status_led_pin
    led_pins = config.get('led_pins', {})
    button_pins = config.get('button_pins', {})
    status_led_pin = config.get('status_led_pin', 0)

    initialize_gpio(config)

    try:
        # Start Flask server in a separate thread
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        # Connect to the server for configuration updates
        connect_socketio()

        verify_leds()

        # Setup button event listeners
        for pin in button_pins.values():
            GPIO.add_event_detect(pin, GPIO.FALLING, callback=button_callback, bouncetime=200)

        while True:
            if check_network():
                GPIO.output(status_led_pin, GPIO.HIGH)
                time.sleep(1)
            else:
                GPIO.output(status_led_pin, GPIO.LOW)
                time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        GPIO.output(status_led_pin, GPIO.LOW)
        GPIO.cleanup()

if __name__ == '__main__':
    main()