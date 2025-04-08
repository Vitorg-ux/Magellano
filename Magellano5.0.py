# app.py
from flask import Flask, render_template, request, send_file, session
import pandas as pd
import requests
import io
import os
from python_tsp.heuristics import solve_tsp_simulated_annealing

ORS_API_KEY="5b3ce3597851110001cf6248a32f48626e06474681b8d0c81e64f6fa"

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Required for session handling

ORS_API_KEY = os.environ.get('ORS_API_KEY')  # Get from environment variables

def geocode_address(address):
    url = 'https://api.openrouteservice.org/geocode/search'
    params = {
        'api_key': ORS_API_KEY,
        'text': address,
        'size': 1
    }
    response = requests.get(url, params=params)
    data = response.json()
    if data['features']:
        coords = data['features'][0]['geometry']['coordinates']
        return (coords[1], coords[0])  # Return (lat, lon)
    return None

def get_ors_matrix(coordinates):
    locations = [[lon, lat] for lat, lon in coordinates]
    
    body = {
        "locations": locations,
        "metrics": ["distance"],
        "units": "km"
    }
    
    headers = {
        'Authorization': ORS_API_KEY,
        'Content-Type': 'application/json'
    }
    
    response = requests.post(
        'https://api.openrouteservice.org/v2/matrix/driving-car',
        json=body,
        headers=headers
    )
    
    data = response.json()
    return data['distances']

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        file = request.files['file']
        df = pd.read_excel(file)
        session['addresses'] = df['address'].tolist()
        session['names'] = df['name'].tolist()
        return render_template('select_points.html', 
                             addresses=session['addresses'])
    return render_template('upload.html')

@app.route('/optimize', methods=['POST'])
def optimize():
    # Retrieve addresses and names from session
    addresses = session.get('addresses', [])
    names = session.get('names', [])
    
    # Geocode all input addresses
    coordinates = []
    valid_indices = []
    for idx, address in enumerate(addresses):
        coords = geocode_address(address)
        if coords:
            coordinates.append(coords)
            valid_indices.append(idx)
    
    # Handle start and end points
    start_type = request.form.get('start_point')
    end_type = request.form.get('end_point')
    
    # Add custom start/end to coordinates
    start_idx = None
    end_idx = None
    
    if start_type == 'custom':
        start_coords = geocode_address(request.form['custom_start'])
        if start_coords:
            coordinates.insert(0, start_coords)
            start_idx = 0
    
    if end_type == 'custom':
        end_coords = geocode_address(request.form['custom_end'])
        if end_coords:
            coordinates.append(end_coords)
            end_idx = len(coordinates) - 1
    
    # Get distance matrix
    try:
        distance_matrix = get_ors_matrix(coordinates)
    except Exception as e:
        return f"Error getting distance matrix: {str(e)}", 400
    
    # Solve TSP
    permutation, _ = solve_tsp_simulated_annealing(distance_matrix)
    
    # Apply start/end constraints
    ordered_indices = []
    start_offset = 1 if start_idx is not None else 0
    end_offset = 1 if end_idx is not None else 0
    
    # Filter input points and maintain order
    input_range = range(start_offset, len(coordinates) - end_offset)
    
    # Collect valid indices from permutation
    for idx in permutation:
        if idx in input_range:
            ordered_indices.append(idx - start_offset)
    
    # Create ordered data
    ordered_data = []
    for idx in ordered_indices:
        original_idx = valid_indices[idx]
        ordered_data.append({
            'name': names[original_idx],
            'address': addresses[original_idx]
        })
    
    # Create output
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame(ordered_data).to_excel(writer, index=False, sheet_name='Optimized Route')
    
    output.seek(0)
    return send_file(output, download_name='optimized_route.xlsx', as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)