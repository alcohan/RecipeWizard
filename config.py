import os, sys
import pkg_resources

from dotenv import load_dotenv


APPNAME = 'RecipeWizard'
ORGNAME = 'AdrianCohan'


# https://stackoverflow.com/questions/31836104/pyinstaller-and-onefile-how-to-include-an-image-in-the-exe-file
def resource_path(relative_path):
    '''Resolve a bundled read-only resource. Under PyInstaller --onefile,
    files live in the temp dir at sys._MEIPASS; in source runs, fall back
    to the project directory.'''
    base_path = getattr(sys, '_MEIPASS', os.path.abspath('.'))
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


def user_data_dir():
    '''Per-user writable directory for mutable state (database, ingredient
    images, etc.).

    Windows: %APPDATA%\\AdrianCohan\\RecipeWizard
    macOS:   ~/Library/Application Support/AdrianCohan/RecipeWizard
    Linux:   $XDG_DATA_HOME/AdrianCohan/RecipeWizard (or ~/.local/share/...)
    '''
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
    elif sys.platform == 'darwin':
        base = os.path.expanduser('~/Library/Application Support')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    path = os.path.join(base, ORGNAME, APPNAME)
    os.makedirs(path, exist_ok=True)
    return path


envfile = get_resource_path('.env')
load_dotenv(envfile)

# Mutable per-user paths. Both can be redirected via env var (useful for
# testing against fixtures or for sharing data internally without copying
# files into the canonical appdata location).
DATABASE = os.environ.get('RECIPEWIZARD_DB') or os.path.join(user_data_dir(), 'builder.db')
INGREDIENTS_PATH = os.environ.get('RECIPEWIZARD_INGREDIENTS') or os.path.join(user_data_dir(), 'ingredients')
os.makedirs(INGREDIENTS_PATH, exist_ok=True)

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
