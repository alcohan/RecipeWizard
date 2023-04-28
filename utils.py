import os.path
import json
import config
import db
import subprocess
import pkg_resources
# from utils.render_html import render

def fill_template(id):
    '''
    Save the data in JSON for the template to render 
    '''
    jquery_formatted_defaults = {
        'itemName' : 'NAME',
        'ingredientList' : 'INGREDIENTS',
        'valueCalories' :  0,
        'valueTotalFat' :  0,
        'valueSatFat' :  0,
        'valueCholesterol' :  0,
        'valueSodium' :  0,
        'valueTotalCarb' :  0,
        'valueFibers' :  0,
        'valueSugars' :  0,
        'valueProteins' :  0,
    }

    data = db.recipe_info(id)
    ingredients = db.recipe_components(id)
    names = [i['Name'] for i in ingredients]
    friendly = ', '.join(names)

    jquery_formatted_my_data = {
        'itemName' : data['Name'],
        'ingredientList' : friendly,
        'valueCalories' :  data['Calories'],
        'valueTotalFat' :  data['TTLFatGrams'],
        'valueSatFat' :  data['SatFatGrams'],
        'valueCholesterol' :  data['CholesterolMilligrams'],
        'valueSodium' :  data['SodiumMilligrams'],
        'valueTotalCarb' :  data['CarbGrams'],
        'valueFibers' :  data['FiberGrams'],
        'valueSugars' :  data['SugarGrams'],
        'valueProteins' :  data['ProteinGrams'],
    }
    values = {**jquery_formatted_defaults, **jquery_formatted_my_data}

    output = 'var data = '
    output += json.dumps(values)

    # with open(config.resource_path('static\\data.js'), 'w') as f:
    with open(pkg_resources.resource_filename(__name__,'static/data.js'), 'w') as f:
        f.write(output)

def open_nutrition_label(id):
    fill_template(id)
    # url = '--app=file:///' + os.path.realpath(config.resource_path('static\\label.html'))

    filename = pkg_resources.resource_filename(__name__,'static/label.html')
    url = '--app=file:///' + filename

    chrome_path = 'C:\Program Files (x86)\Google\Chrome\Application\Chrome.exe'

    command = [chrome_path, url]
    subprocess.Popen(command)
    
if __name__=="__main__":
    open_nutrition_label(2)