import json
import os
import socket
import time
import requests
import RPi.GPIO as GPIO
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, render_template_string
from mysql.connector import pooling

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this to a secure key

CONFIG_DIR = 'configurations/'  # Directory where configuration files are stored
IMAGES_FOLDER = 'static/images/'  # Path to the images folder

# MySQL connection pool
mysql_pool = pooling.MySQLConnectionPool(
    pool_name="mysql_pool",
    pool_size=10,
    host='localhost',
    user='root',
    password='Passw0rd123',
    database='PickByLight'
)

def get_db_connection():
    """MySQL database connection."""
    return mysql_pool.get_connection()

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

# GPIO setup
MATERIALS_COUNT = 10
LED_PINS = [18, 23, 24, 25, 12, 16, 20, 21, 26, 19]
BUTTON_PINS = [17, 27, 22, 5, 6, 13, 19, 26, 12, 16]
GPIO.setmode(GPIO.BCM)
for pin in LED_PINS:
    GPIO.setup(pin, GPIO.OUT)
for pin in BUTTON_PINS:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Define material to GPIO pin mapping
material_to_gpio = {
    "material1": LED_PINS[0],
    "material2": LED_PINS[1],
    "material3": LED_PINS[2],
    "material4": LED_PINS[3],
    "material5": LED_PINS[4],
    "material6": LED_PINS[5],
    "material7": LED_PINS[6],
    "material8": LED_PINS[7],
    "material9": LED_PINS[8],
    "material10": LED_PINS[9]
}

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    hostname = request.cookies.get('hostname')
    if not hostname:
        return redirect(url_for('hostname_input'))
    
    return render_template('index.html')

@app.route('/hostname_input', methods=['GET', 'POST'])
def hostname_input():
    if request.method == 'POST':
        hostname = request.form['hostname'].strip()
        if hostname:
            response = redirect(url_for('index'))
            response.set_cookie('hostname', hostname, max_age=60*60*24*30)
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

    start_time = time.time()

    response = requests.get(f'http://localhost:5000/fetch_jit_components_api?PRODN={car_id}')
    if response.status_code != 200:
        return jsonify({'error': 'Failed to fetch data from the existing API.'}), 500

    data = response.json()
    execution_time = time.time() - start_time

    matched_materials = [component.get('Material', '') for item in data.get('results', []) for component in item.get('BOM', []) if component.get('Material', '') in predefined_materials]

    if not matched_materials:
        return jsonify({'error': 'No matching materials found.'}), 404

    materials_with_pictures = {material: f"{IMAGES_FOLDER}{material}.png" for material in matched_materials}

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute('''
            INSERT INTO scans (car_id, user_id, machine_name, scan_time, execution_time)
            VALUES (%s, %s, %s, NOW(), %s)
        ''', (car_id, session['user_id'], hostname, execution_time))
        connection.commit()
    except mysql.connector.Error as err:
        return jsonify({'error': f'Database error: {err}'}), 500
    finally:
        cursor.close()
        connection.close()

    # Light up the LEDs for matched materials
    for material in matched_materials:
        if material in material_to_gpio:
            GPIO.output(material_to_gpio[material], GPIO.HIGH)

    return render_template_string('''
    <table class="materials-table">
        {% for material, picture in materials_with_pictures.items() %}
            {% if material in material_to_gpio %}
            {% if loop.index % 2 == 1 %}
            <tr>
            {% endif %}
            <td class="material-item">
                <img src="{{ url_for('static', filename='images/' + material + '.png') }}" alt="Picture of {{ material }}" class="material-image">
                <p>{{ material }}</p>
                <button onclick="turn_off_led('{{ material }}')">Confirm</button>
            </td>
            {% if loop.index % 2 == 0 or loop.last %}
            </tr>
            {% endif %}
            {% endif %}
        {% endfor %}
    </table>
    <script>
        function turn_off_led(material) {
            fetch('/turn_off_led/' + material, { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if(data.success) {
                    alert('LED turned off');
                } else {
                    alert('Failed to turn off LED');
                }
            });
        }
    </script>
    ''', materials_with_pictures=materials_with_pictures)

@app.route('/turn_off_led/<string:material>', methods=['POST'])
def turn_off_led(material):
    if material in material_to_gpio:
        GPIO.output(material_to_gpio[material], GPIO.LOW)
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Invalid material'})

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5001, debug=True)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
