import json
import os
import socket
import time
import requests
import RPi.GPIO as GPIO
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, render_template_string

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this to a secure key

CONFIG_DIR = 'configurations/'  # Directory where configuration files are stored
IMAGES_FOLDER = 'static/images/'  # Path to the images folder

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

def get_db_connection():
    """MySQL database connection."""
    # Not needed in this version, so we'll just remove this function
    pass

def get_machine_name():
    """Get the hostname of the machine."""
    return socket.gethostname()

def load_predefined_materials(machine_name):
    """Load predefined materials based on the machine name."""
    config_path = os.path.join(CONFIG_DIR, f'config_{machine_name}.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
            return config.get('predefined_materials', [])
    return []

@app.route('/')
def index():
    # Check if the user is logged in
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Check if hostname is set
    hostname = request.cookies.get('hostname')
    if not hostname:
        return redirect(url_for('hostname_input'))

    # Render the main page
    return render_template('index.html')

@app.route('/hostname_input', methods=['GET', 'POST'])
def hostname_input():
    if request.method == 'POST':
        hostname = request.form['hostname'].strip()
        if hostname:
            # Set cookie and redirect to login page
            response = redirect(url_for('index'))
            response.set_cookie('hostname', hostname, max_age=60*60*24*30)  # Cookie lasts for 30 days
            return response
        else:
            return render_template('hostname_input.html', error='Hostname is required.')
    
    return render_template('hostname_input.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_id = request.form['user_id'].strip()
        if user_id:
            session['user_id'] = user_id
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='User ID is required.')
    
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/compare_materials', methods=['POST'])
def compare_materials():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    car_id = request.form['car_id'].strip()
    hostname = request.cookies.get('hostname')
    if not car_id:
        return jsonify({'error': 'Please enter a car ID.'}), 400

    predefined_materials = load_predefined_materials(hostname)
    if not predefined_materials:
        return jsonify({'error': 'No configuration file found for the given hostname.'}), 404

    response = requests.get(f'http://localhost:5000/fetch_jit_components_api?PRODN={car_id}')
    if response.status_code != 200:
        return jsonify({'error': 'Failed to fetch data from the existing API.'}), 500

    data = response.json()

    matched_materials = {component.get('Material', '') for item in data.get('results', []) for component in item.get('BOM', []) if component.get('Material', '') in predefined_materials}

    if not matched_materials:
        return jsonify({'error': 'No matching materials found.'}), 404

    # Light up LEDs for each matched material
    for material, pin in LED_PINS.items():
        if material in matched_materials:
            GPIO.output(pin, GPIO.HIGH)
        else:
            GPIO.output(pin, GPIO.LOW)

    # Wait for button press for each material
    for material in matched_materials:
        while GPIO.input(BUTTON_PIN) == GPIO.HIGH:
            time.sleep(0.1)  # Wait for button press
        # After button press, turn off LED
        GPIO.output(LED_PINS.get(material, -1), GPIO.LOW)

    return jsonify({'message': 'Materials compared and LEDs controlled accordingly.'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
