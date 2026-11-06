'''Branding on printed recipe pages: the header logo, the accent color,
the header label and the footer line. Set on Configure › Print &
branding.

The text settings live in the library (table print_branding). The logo
is a file, <data>/branding/logo.<ext> (config.BRANDING_PATH), kept
beside the ingredient photos so data-only backups stay small: it goes
into a backup, and comes back from one, together with the photos.
Nothing is bundled with the app; until a logo is chosen, pages have none.
'''
import os

import config
import db
from utilities.backup import LOGO_EXTENSIONS, LOGO_STEM
from utilities import backup

DEFAULT_ACCENT = '#082c00'
DEFAULT_HEADER = 'Recipe card'
DEFAULT_FOOTER = ''
DEFAULT_DISCLAIMER = ('Nutrition and allergen information is estimated from manufacturer labels and supplier'
                      ' data and should be considered approximate. Actual values vary with portioning,'
                      ' preparation and ingredient substitutions.')
MAX_LOGO_BYTES = 5 * 1024 * 1024


def logo_file(folder=None):
    '''Path of the current logo file, or None.'''
    folder = folder or config.BRANDING_PATH
    name = backup.logo_file(folder)
    return os.path.join(folder, name) if name else None


def _write_logo(data, ext, folder=None):
    folder = folder or config.BRANDING_PATH
    os.makedirs(folder, exist_ok=True)
    _remove_logo(folder)
    path = os.path.join(folder, LOGO_STEM + ext.lower())
    part = path + '.part'
    with open(part, 'wb') as f:
        f.write(data)
    os.replace(part, path)
    return path


def _remove_logo(folder=None):
    folder = folder or config.BRANDING_PATH
    for ext in LOGO_EXTENSIONS:
        path = os.path.join(folder, LOGO_STEM + ext)
        if os.path.isfile(path):
            os.remove(path)


def _logo():
    '''(bytes, ext) of the logo, or None. An earlier build kept the logo
    in the library; that one moves out to the file the first time.'''
    legacy = db.take_legacy_print_logo()
    if legacy and not logo_file():
        _write_logo(*legacy)
    path = logo_file()
    if path is None:
        return None
    try:
        with open(path, 'rb') as f:
            return f.read(), os.path.splitext(path)[1].lower()
    except OSError:
        return None


def current():
    '''Everything the page painter needs: {'logo': (bytes, ext) | None,
    'accent', 'header', 'footer', 'disclaimer'}.'''
    stored = db.get_print_branding()
    return {
        'logo': _logo(),
        'accent': stored.get('accent') or DEFAULT_ACCENT,
        'header': stored['header'] if stored.get('header') is not None else DEFAULT_HEADER,
        'footer': stored['footer'] if stored.get('footer') is not None else DEFAULT_FOOTER,
        'disclaimer': stored['disclaimer'] if stored.get('disclaimer') is not None else DEFAULT_DISCLAIMER,
    }


def set_logo_file(path):
    '''Copy an image in as the logo. Raises ValueError if it's not a
    supported image or too big.'''
    ext = os.path.splitext(path)[1].lower()
    if ext not in LOGO_EXTENSIONS:
        raise ValueError('Choose an SVG, PNG, JPG, WebP or BMP image.')
    if os.path.getsize(path) > MAX_LOGO_BYTES:
        raise ValueError('That image is over 5 MB; a logo needs far less.')
    with open(path, 'rb') as f:
        _write_logo(f.read(), ext)


def clear_logo():
    _remove_logo()


def set_accent(color):
    db.set_print_branding('accent', color)


def set_header_label(text):
    db.set_print_branding('header', text)


def set_footer_text(text):
    db.set_print_branding('footer', text)


def set_disclaimer(text):
    '''Blank hides the disclaimer; None goes back to the default text.'''
    if text is None:
        db.query("DELETE FROM print_branding WHERE key = 'disclaimer';")
    else:
        db.set_print_branding('disclaimer', text)
