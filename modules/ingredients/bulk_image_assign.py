'''Bulk image-assignment dialog: list every ingredient with a dropdown of
files from `static/ingredients/`. Unassigned rows are sorted to the top.
Each combo change auto-saves to the database.'''
import PySimpleGUI as sg
import db
import config
import window_utils
from modules.ingredients.ingredient import _available_images


def render():
    images = _available_images()
    ingredients = db.get_ingredients()
    # Unassigned first (False sorts before True), then alphabetical by Name.
    ingredients.sort(key=lambda r: (bool(r.get('ImageFilename')), (r['Name'] or '').lower()))

    rows = []
    for ing in ingredients:
        ing_id = ing['Id']
        current = ing.get('ImageFilename') or ''
        rows.append([
            sg.Text(ing['Name'], size=(28, 1)),
            sg.Combo(images, default_value=current, size=(42, 1), readonly=True,
                     enable_events=True, key=f'-BULK-IMG-::{ing_id}'),
        ])

    layout = [
        [sg.Text('Unassigned ingredients are listed first. Selections save immediately.')],
        [sg.Column(rows, scrollable=True, vertical_scroll_only=True, size=(640, 540), key='-LIST-')],
        [sg.Button('Refresh File List', key='-REFRESH-FILES-'), sg.Push(), sg.Button('Close', key='-CLOSE-')],
    ]

    window = window_utils.subwindow(f'{config.APPNAME} | Bulk Assign Images', layout, icon=config.ICON)

    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, '-CLOSE-'):
            break
        elif event.startswith('-BULK-IMG-::'):
            ingredient_id = int(event.split('::')[1])
            db.set_ingredient_image(ingredient_id, values[event])
        elif event == '-REFRESH-FILES-':
            images = _available_images()
            for ing in ingredients:
                key = f'-BULK-IMG-::{ing["Id"]}'
                window[key].update(values=images, value=values[key])

    window_utils.unregister_active(window)
    window.close()
