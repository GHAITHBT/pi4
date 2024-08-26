from flask import Flask, request, jsonify
import RPi.GPIO as GPIO
import threading
import time
import mysql.connector
import requests
import socket

app = Flask(__name__)

# Define constants and configurations
status_led_pin = 9  # Pin for the status LED
main_app_url = "http://10.110.10.204:8000/confirm_material"  # Replace with your main app's IP address and port
hostname = socket.gethostname()

# Database configuration
db_config = {
    'host': '10.110.10.204',
    'user': 'root',
    'password': 'Passw0rd123',
    'database': 'PickByLight'
}

# Set up GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Fetch database connection
def get_db_connection():
    return mysql.connector.connect(**db_config)

# Fetch LED and Button configuration from the database
def fetch_led_button_config():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT material_code, led_pin, button_pin FROM led_button_config")
    config = cursor.fetchall()
    conn.close()
    
    return {entry['material_code']: {'led': entry['led_pin'], 'button': entry['button_pin']} for entry in config}

# Setup GPIO pins based on the predefined configuration
def setup_gpio(predefined_materials):
    for material, pins in predefined_materials.items():
        GPIO.setup(pins['led'], GPIO.OUT)
        GPIO.output(pins['led'], GPIO.LOW)
        GPIO.setup(pins['button'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(status_led_pin, GPIO.OUT)
    GPIO.output(status_led_pin, GPIO.LOW)

# Activate LED for a specific material
@app.route('/activate_led', methods=['POST'])
def activate_led():
    data = request.json
    material = data.get('material')
    
    if material in predefined_materials:
        GPIO.output(predefined_materials[material]['led'], GPIO.HIGH)
        return jsonify({'status': 'LED activated'}), 200
    return jsonify({'error': 'Invalid material'}), 400

# Deactivate LED for a specific material
@app.route('/deactivate_led', methods=['POST'])
def deactivate_led():
    data = request.json
    material = data.get('material')
    
    if material in predefined_materials:
        GPIO.output(predefined_materials[material]['led'], GPIO.LOW)
        return jsonify({'status': 'LED deactivated'}), 200
    return jsonify({'error': 'Invalid material'}), 400

# Activate LEDs for all matched materials
@app.route('/activate_leds', methods=['POST'])
def activate_leds():
    data = request.json
    matched_materials = data.get('materials', [])
    
    if not isinstance(matched_materials, list):
        return jsonify({'error': 'Invalid request format, expected a list of materials'}), 400
    
    for material in matched_materials:
        if material in predefined_materials:
            GPIO.output(predefined_materials[material]['led'], GPIO.HIGH)
        else:
            print(f"Warning: Material '{material}' not found in database.")
    
    return jsonify({'status': 'LEDs activated for matched materials'}), 200

# Handle button press callback
def button_callback(channel):
    material = next((mat for mat, pins in predefined_materials.items() if pins['button'] == channel), None)
    
    if material:
        GPIO.output(predefined_materials[material]['led'], GPIO.LOW)
        print(f"Button pressed for {material}, LED turned off.")
        
        # Send confirmation to the main app
        try:
            response = requests.post(main_app_url, json={'material': material})
            if response.status_code == 200:
                print(f"Confirmation sent for material {material}.")
            else:
                print(f"Failed to send confirmation for material {material}. HTTP status code: {response.status_code}")
        except Exception as e:
            print(f"Error sending confirmation for material {material}: {e}")

# Verify that LEDs work properly
def verify_leds(predefined_materials):
    print("Verifying LEDs...")
    for pins in predefined_materials.values():
        GPIO.output(pins['led'], GPIO.HIGH)
    time.sleep(2)
    for pins in predefined_materials.values():
        GPIO.output(pins['led'], GPIO.LOW)
    print("LED verification complete.")

# Run Flask in a separate thread
def run_flask():
    app.run(host='0.0.0.0', port=5000)

# Main program execution
def main():
    try:
        global predefined_materials
        predefined_materials = fetch_led_button_config()
        setup_gpio(predefined_materials)
        
        # Blink status LED to indicate system is ready
        GPIO.output(status_led_pin, GPIO.HIGH)
        
        verify_leds(predefined_materials)
        
        # Set up button event detection
        for material, pins in predefined_materials.items():
            GPIO.add_event_detect(pins['button'], GPIO.FALLING, callback=button_callback, bouncetime=200)
        
        # Start the Flask server in a separate thread
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        while True:
            # Keep the main thread alive for handling GPIO
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        GPIO.output(status_led_pin, GPIO.LOW)
        GPIO.cleanup()

if __name__ == '__main__':
    main()
