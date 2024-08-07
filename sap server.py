from flask import Flask, render_template, request, jsonify
from pyrfc import Connection
from mysql.connector import pooling, Error as MySQLError
from datetime import datetime
import threading
import logging
import traceback
import time
import redis

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this to a secure key

# SAP and MySQL connection parameters
SAP_CONN_PARAMS = {
    "user": "MIGRATION",
    "passwd": "migSEBN99#",
    "ashost": "137.121.21.6",
    "sysnr": "06",
    "client": "100",
    "lang": "en",
}

MYSQL_CONN_PARAMS = {
    "host": "localhost",
    "user": "root",
    "password": "Passw0rd123",
    "database": "PickByLight",
    "pool_name": "mysql_pool",
    "pool_size": 10
}

# MySQL connection pool
mysql_pool = pooling.MySQLConnectionPool(**MYSQL_CONN_PARAMS)

# Redis connection
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

# Configure logging
logging.basicConfig(level=logging.INFO)

def identify_sap_system():
    if SAP_CONN_PARAMS["ashost"].endswith("15"):
        system = "FCK"
    elif SAP_CONN_PARAMS["ashost"].endswith("13"):
        system = "FCD"
    elif SAP_CONN_PARAMS["ashost"].endswith("6"):
        system = "FCP"
    else:
        system = "Unknown"
    
    client = SAP_CONN_PARAMS["client"]
    return f"{system} {client}"

def fetch_jinum_from_mysql(prodn):
    try:
        # Check cache first
        cached_jinum = redis_client.get(prodn)
        if cached_jinum:
            return cached_jinum.decode('utf-8')
        
        conn_mysql = mysql_pool.get_connection()
        cursor = conn_mysql.cursor()

        sql = "SELECT JINUM FROM Jithead WHERE PRODN = %s"
        cursor.execute(sql, (prodn,))
        result = cursor.fetchone()
        cursor.fetchall()  # Clear any unread results

        cursor.close()
        conn_mysql.close()

        if result:
            jinum = result[0]
            # Cache the result
            redis_client.set(prodn, jinum)
            return jinum
        else:
            return None

    except MySQLError as err:
        logging.error(f"Failed to fetch JINUM from MySQL: {err}")
        return None

def call_bapi_get_details(jinum):
    try:
        conn_sap = Connection(**SAP_CONN_PARAMS)
        jitcalls = [{'JITCALLNUMBER': jinum}]
        result = conn_sap.call('BAPI_JITCALLIN_GETDETAILS', JITCALLS=jitcalls)
        conn_sap.close()

        return result['JITCALLCOMPONENTS']

    except Exception as e:
        logging.error(f"Failed to call BAPI_JITCALLIN_GETDETAILS: {e}")
        return None

def fetch_bom_data(material, werks):
    try:
        conn_sap = Connection(**SAP_CONN_PARAMS)
        datuv = datetime.today().date()
        stlan = "3"

        bom_data = conn_sap.call("CS_BOM_EXPL_MAT_V2_RFC", 
                             DATUV=datuv,
                             MTNRV=material,
                             WERKS=werks,
                             STLAN=stlan,
                             CAPID="",
                             AUMNG="0",
                             EMENG="0",
                             MKTLS="x",
                             STPST="0",
                             SVWVO="x",
                             VRSVO="x",
                             STLAL="1")

        conn_sap.close()
        processed_bom_data = process_bom_data(bom_data)

        bom_materials = {item["Material"] for item in processed_bom_data if item["Material"].startswith(("P", "B"))}
        nested_bom_data = []
        for material in bom_materials:
            nested_data = fetch_bom_data(material, werks)
            if nested_data:
                nested_bom_data.extend(nested_data)

        processed_bom_data.extend(nested_bom_data)
        return processed_bom_data

    except Exception as e:
        logging.error(f"Failed to fetch BOM data for Material {material}: {e}")
        logging.error(traceback.format_exc())
        return []

def process_bom_data(bom_data):
    try:
        items = bom_data.get("STB", [])
        bom_list = []
        for item in items:
            material = item.get("IDNRK", "").lstrip('0')
            component = {
                "Material": material,
                "Description": item.get("OJTXP", ""),
                "Quantity": item.get("MNGLG", ""),
            }
            bom_list.append(component)
        return bom_list
    except Exception as e:
        logging.error(f"Error processing BOM data: {e}")
        logging.error(traceback.format_exc())
        return []

def fetch_bom_data_concurrently(material, werks, results, index):
    try:
        bom_data = fetch_bom_data(material, werks)
        results[index] = bom_data
    except Exception as e:
        logging.error(f"Error in concurrent BOM data fetch for material {material}: {e}")

@app.route('/')
def index():
    sap_system = identify_sap_system()
    return render_template('index1.html', sap_system=sap_system)

@app.route('/fetch_jit_components', methods=['POST'])
def fetch_jit_components():
    start_time = time.time()

    prodn = request.form['prodn'].strip()
    if not prodn:
        return jsonify({'error': 'Please enter a PRODN value.'}), 400

    jinum = fetch_jinum_from_mysql(prodn)
    if not jinum:
        return jsonify({'error': f'Could not find JINUM for PRODN: {prodn}'}), 404

    jitcalcomponents = call_bapi_get_details(jinum)
    if not jitcalcomponents:
        return jsonify({'error': f'No JIT Call Components found for JINUM: {jinum}'}), 404

    werks = "TN30" if prodn.startswith("52") else "TN10"
    logging.info(f"Value of werks: {werks}")

    threads = []
    results = [None] * len(jitcalcomponents)
    for i, component in enumerate(jitcalcomponents):
        material = component['MATERIAL']
        thread = threading.Thread(target=fetch_bom_data_concurrently, args=(material, werks, results, i))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    response = [{'component': component, 'bom_data': results[i]} for i, component in enumerate(jitcalcomponents)]

    execution_time = time.time() - start_time
    return jsonify({'results': response, 'execution_time': execution_time}), 200

@app.route('/fetch_jit_components_api', methods=['GET'])
def fetch_jit_components_api():
    start_time = time.time()

    prodn = request.args.get('PRODN', '').strip()
    if not prodn:
        return jsonify({'error': 'Please provide a PRODN parameter.'}), 400

    jinum = fetch_jinum_from_mysql(prodn)
    if not jinum:
        return jsonify({'error': f'Could not find JINUM for PRODN: {prodn}'}), 404

    jitcalcomponents = call_bapi_get_details(jinum)
    if not jitcalcomponents:
        return jsonify({'error': f'No JIT Call Components found for JINUM: {jinum}'}), 404

    werks = "TN30" if prodn.startswith("52") else "TN10"
    logging.info(f"Value of werks: {werks}")

    threads = []
    results = [None] * len(jitcalcomponents)
    for i, component in enumerate(jitcalcomponents):
        material = component['MATERIAL']
        thread = threading.Thread(target=fetch_bom_data_concurrently, args=(material, werks, results, i))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    response = [{'CUST_MAT': component.get('CUST_MAT', ''), 'BOM': results[i] if results[i] else []} for i, component in enumerate(jitcalcomponents)]

    execution_time = time.time() - start_time
    return jsonify({'results': response, 'execution_time': execution_time}), 200

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5000, threads=8)
