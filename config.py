import configparser

config = configparser.ConfigParser()
config.read('config.ini')
DATABASE = config.get('database','location')

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
