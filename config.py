import os, sys
import pkg_resources

from dotenv import load_dotenv


APPNAME = 'RecipeWizard'
# The one version number. Release builds stamp it from the git tag
# (vX.Y.Z); update checks compare GitHub release tags against it. Source
# runs read it from git instead (source_version, below), so this literal
# only matters when git can't answer.
__version__ = '0.1.0'
ORGNAME = 'AdrianCohan'


def source_version():
    '''For a source run in a git checkout: (version of the latest vX.Y.Z
    tag, commits since it, short commit, uncommitted changes) from
    `git describe`. None in a release build or without git.'''
    if getattr(sys, 'frozen', False):
        return None
    root = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(os.path.join(root, '.git')):
        return None
    import re
    import subprocess
    try:
        out = subprocess.run(
            ['git', 'describe', '--tags', '--long', '--dirty', '--match', 'v[0-9]*', '--exclude', '*-*'],
            cwd=root, capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.fullmatch(r'v(\d+\.\d+\.\d+)-(\d+)-g([0-9a-f]+)(-dirty)?', out)
    if not m:
        return None
    return m.group(1), int(m.group(2)), m.group(3), bool(m.group(4))


SOURCE = source_version()
if SOURCE:
    __version__ = SOURCE[0]


def build_text():
    '''"Release build", or for a source run e.g. "Source · 3 commits
    after v0.0.5 · 36aad67 · uncommitted changes".'''
    if SOURCE is None:
        return 'Release build' if getattr(sys, 'frozen', False) else 'Source'
    version, ahead, commit, dirty = SOURCE
    parts = ['Source']
    if ahead:
        parts.append(f"{ahead} commit{'s' if ahead != 1 else ''} after v{version}")
    parts.append(commit)
    if dirty:
        parts.append('uncommitted changes')
    return ' · '.join(parts)


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
# The print logo (Configure › Print & branding): a file, like the photos,
# so data-only backups stay small; it goes into backups with the photos.
BRANDING_PATH = os.environ.get('RECIPEWIZARD_BRANDING') or os.path.join(user_data_dir(), 'branding')
# Recipe photos: like ingredient photos, a file per recipe named in
# Recipes.ImageFilename. A recipe's photo stands in for its wedge.
RECIPE_IMAGES_PATH = os.environ.get('RECIPEWIZARD_RECIPE_IMAGES') or os.path.join(user_data_dir(), 'recipes')
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
