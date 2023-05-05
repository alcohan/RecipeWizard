import requests
import json
from os import getenv

api_key = getenv('API_KEY')

# API endpoint URL
url = 'https://trackapi.nutritionix.com/v2/natural/nutrients'

def get_nutrition(query: str):
    if api_key==None:
        raise RuntimeError('API Key not found in the environment') 
    
    # Request headers
    headers = {
        'Content-Type': 'application/json',
        'x-app-id': '84b9244e',
        'x-app-key': api_key
    }

    # Request body
    body = {
        'query': query
    }

    # Send API request
    response = requests.post(url, headers=headers, data=json.dumps(body))
    if response.ok == False:
        raise Exception(f'{response.status_code} {response.reason}')

    # Unpack response JSON into a variable
    data = json.loads(response.text)

    # Print response data
    return data


nx_fields_mapping = {
    'food_name' : 'Name',
    'serving_qty': 'Yield', #----------------------
    'serving_unit': 'Unit',
    'serving_weight_grams': 'Weight',
    'nf_calories': 'Calories',
    'nf_total_fat': 'TTLFatGrams',
    'nf_saturated_fat': 'SatFatGrams',
    'nf_cholesterol': 'CholesterolMilligrams',
    'nf_sodium': 'SodiumMilligrams',
    'nf_total_carbohydrate': 'CarbGrams',
    'nf_dietary_fiber': 'FiberGrams',
    'nf_sugars': 'SugarGrams',
    'nf_protein': 'ProteinGrams'
}

def get_simple(query):
    data = get_nutrition(query)['foods'][0]
    result = {}
    for (nx_key, my_key) in nx_fields_mapping.items():
        result[my_key] = data[nx_key]

    result['Unit'] = f"{data['serving_qty']} {data['serving_unit']}"
    return result