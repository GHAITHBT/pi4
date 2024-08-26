from flask import Flask, request, jsonify
import RPi.GPIO as GPIO
import threading
import time
import mysql.connector
import requests
import json
from mysql.connector import pooling
import socket

app = Flask(__name__)

# Configuration
status_led_pin = 9  # Pin for the status LED
main_app_url = "http://10.110.10.204:8000/confirm_material"  # Main app URL for confirmations

# Database configurations
db_pick_by_light = {
    'host': '10.110.10.204',
    'user': 'root',
    'password': 'Passw0rd123',
    'database': 'PickByLight'
}

db_inventory_management = {
    'host': '10.110.10.204',
    'user': 'Zaineb',
    'password': 'Passw0rd123',
    'database': 'inventory_management'
}

# Set up database connection pools
mysql_pool_pick_by_light = pooling.MySQLConnectionPool(
    pool_name="pick_by_light_pool",
    pool_size=5,
    **db_pick_by_light
)

mysql_pool_inventory_management = pooling.MySQLConnectionPool(
    pool_name="inventory_management_pool",
    pool_size=5,
    **db_inventory_management
)

def get_db_connection(pool):
    return pool.get_connection()

# GPIO Setup
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

def initialize_gpio(predefined_materials, inventory_materials):
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    for material, pins in predefined_materials.items():
        GPIO.setup(pins['led'], GPIO.OUT)
        GPIO.output(pins['led'], GPIO.LOW)
        GPIO.setup(pins['button'], GPIO.IN, pull_up_down=GPIO.PUD_UP)

    for material, pins in inventory_materials.items():
        GPIO.setup(pins['led'], GPIO.OUT)
        GPIO.output(pins['led'], GPIO.LOW)
        GPIO.setup(pins['button'], GPIO.IN, pull_up_down=GPIO.PUD_UP)

    GPIO.setup(status_led_pin, GPIO.OUT)
    GPIO.output(status_led_pin, GPIO.LOW)

# Fetch configurations from PickByLight database
def fetch_pick_by_light_configuration():
    connection = get_db_connection(mysql_pool_pick_by_light)
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM rasp_pi_configurations WHERE ip_address = %s", (get_ip_address(),))
        config = cursor.fetchone()
        if config:
            config['led_pins'] = json.loads(config['led_pins'])
            config['button_pins'] = json.loads(config['button_pins'])
            config['predefined_materials'] = json.loads(config['predefined_materials'])
        return config if config else {}
    finally:
        cursor.close()
        connection.close()

# Fetch configuration from inventory_management database
def fetch_led_button_config_inventory():
    connection = get_db_connection(mysql_pool_inventory_management)
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT material_code, led_pin, button_pin FROM led_button_config")
    config = cursor.fetchall()
    connection.close()
    
    return {entry['material_code']: {'led': entry['led_pin'], 'button': entry['button_pin']} for entry in config}

# Activate LEDs for materials (PickByLight)
@app.route('/activate_led', methods=['POST'])
def activate_led_pick_by_light():
    data = request.json
    material = data.get('material')
    
    if material in led_pins_pick_by_light:
        GPIO.output(led_pins_pick_by_light[material], GPIO.HIGH)
        return jsonify({'status': 'LED activated'}), 200
    
    return jsonify({'error': 'Invalid material'}), 400

# Deactivate LEDs for materials (PickByLight)
@app.route('/deactivate_led', methods=['POST'])
def deactivate_led_pick_by_light():
    data = request.json
    material = data.get('material')
    
    if material in led_pins_pick_by_light:
        GPIO.output(led_pins_pick_by_light[material], GPIO.LOW)
        return jsonify({'status': 'LED deactivated'}), 200
    
    return jsonify({'error': 'Invalid material'}), 400

# Activate LEDs for materials (Inventory Management)
@app.route('/activate_leds_inventory', methods=['POST'])
def activate_leds_inventory():
    data = request.json
    matched_materials = data.get('materials', [])
    
    for material in matched_materials:
        if material in led_pins_inventory:
            GPIO.output(led_pins_inventory[material]['led'], GPIO.HIGH)
    
    return jsonify({'status': 'LEDs activated for matched materials'}), 200

# Button callback for PickByLight
def button_callback_pick_by_light(channel):
    material = [m for m, p in button_pins_pick_by_light.items() if p == channel][0]
    GPIO.output(led_pins_pick_by_light[material], GPIO.LOW)
    
    try:
        response = requests.post(main_app_url, json={'material': material})
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error sending confirmation: {e}")

# Button callback for Inventory Management
def button_callback_inventory(channel):
    material = [m for m, p in button_pins_inventory.items() if p == channel][0]
    GPIO.output(led_pins_inventory[material]['led'], GPIO.LOW)
    
    try:
        response = requests.post(main_app_url, json={'material': material})
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error sending confirmation: {e}")

# Verify LEDs for both configurations
def verify_leds(predefined_materials, inventory_materials):
    for pins in predefined_materials.values():
        GPIO.output(pins['led'], GPIO.HIGH)
    for pins in inventory_materials.values():
        GPIO.output(pins['led'], GPIO.HIGH)
    time.sleep(2)
    for pins in predefined_materials.values():
        GPIO.output(pins['led'], GPIO.LOW)
    for pins in inventory_materials.values():
        GPIO.output(pins['led'], GPIO.LOW)
    print("LED verification complete.")

def run_flask():
    app.run(host='0.0.0.0', port=5000)

def main():
    try:
        # Fetch configurations for both systems
        config_pick_by_light = fetch_pick_by_light_configuration()
        predefined_materials_pick_by_light = config_pick_by_light.get('predefined_materials', {})
        led_pins_pick_by_light = config_pick_by_light.get('led_pins', {})
        button_pins_pick_by_light = config_pick_by_light.get('button_pins', {})
        
        inventory_materials = fetch_led_button_config_inventory()
        
        global led_pins_inventory, button_pins_inventory
        led_pins_inventory = {m: p['led'] for m, p in inventory_materials.items()}
        button_pins_inventory = {m: p['button'] for m, p in inventory_materials.items()}

        initialize_gpio(predefined_materials_pick_by_light, inventory_materials)
        
        verify_leds(predefined_materials_pick_by_light, inventory_materials)

        # Setup button event listeners
        for pin in button_pins_pick_by_light.values():
            GPIO.add_event_detect(pin, GPIO.FALLING, callback=button_callback_pick_by_light, bouncetime=200)
        
        for pin in button_pins_inventory.values():
            GPIO.add_event_detect(pin, GPIO.FALLING, callback=button_callback_inventory, bouncetime=200)
        
        # Start Flask server
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        GPIO.output(status_led_pin, GPIO.LOW)
        GPIO.cleanup()

if __name__ == '__main__':
    main()
