import configparser
import os, sys
import pkg_resources

from dotenv import load_dotenv


# https://stackoverflow.com/questions/31836104/pyinstaller-and-onefile-how-to-include-an-image-in-the-exe-file
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS2
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def get_resource(relative_path):
    resource = pkg_resources.resource_string(__name__,relative_path)
    data = resource.decode('utf-8')
    return data
def get_resource_path(relative_path):
    path = pkg_resources.resource_filename(__name__,relative_path)
    return path

def get_image(relative_path):
    image = pkg_resources.resource_string(__name__, relative_path)
    return image

envfile = get_resource_path('.env')
load_dotenv(envfile)

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
