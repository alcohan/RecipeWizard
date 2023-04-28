import configparser
import os, sys
import pkg_resources

# https://stackoverflow.com/questions/31836104/pyinstaller-and-onefile-how-to-include-an-image-in-the-exe-file
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS2
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def get_resource(relative_path):
    # try:
    #     with open(resource_path(relative_path), 'r') as f:
    #         data = f.read()
    # except Exception:
    print('Fetching resource from package ',relative_path)
    resource = pkg_resources.resource_string(__name__,relative_path)
    data = resource.decode('utf-8')
    return data

config = configparser.ConfigParser()
config.read(resource_path('config.ini'))
APPNAME = 'RecipeWizard'
DATABASE = resource_path(config.get('database','location'))
ICON = resource_path('icon.ico')

ingredient_demographic_fields = ['Name','Unit','Portion','Cost','Weight']
ingredient_demographic_fields = {
    'Name': 'Name',
    'Unit': 'Unit',
    'Portion': 'Portion',
    'Cost': 'Cost',
    'Weight': 'Weight (g)',
}

nutrition_fields = {
    'Calories': 'Calories',
    'TTLFatGrams': 'TTL Fat (g)',
    'SatFatGrams': 'Sat Fat (g)',
    'CholesterolMilligrams': 'Cholesterol (mg)',
    'SodiumMilligrams': 'Sodium (mg)',
    'CarbGrams': 'Carb (g)',
    'FiberGrams': 'Fiber (g)',
    'SugarGrams': 'Sugar (g)',
    'ProteinGrams': 'Protein (g)',
}
