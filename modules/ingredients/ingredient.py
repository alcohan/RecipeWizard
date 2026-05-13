import os
from io import BytesIO
import PySimpleGUI as sg
import db
import config
import window_utils
import modules.ingredients.ingredient_prices as ingredient_prices
import modules.ingredients.pricehistory as pricehistory
from re import sub

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')
PREVIEW_SIZE = (200, 200)

def _available_images():
    '''List image files currently sitting in the ingredients photo folder.'''
    os.makedirs(config.INGREDIENTS_PATH, exist_ok=True)
    files = [
        name for name in sorted(os.listdir(config.INGREDIENTS_PATH))
        if os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS
    ]
    return [''] + files

def _image_thumbnail(filename):
    '''Return PNG bytes of a downsized preview for sg.Image(data=...), or None.'''
    if not filename or PILImage is None:
        return None
    path = os.path.join(config.INGREDIENTS_PATH, filename)
    if not os.path.isfile(path):
        return None
    try:
        img = PILImage.open(path)
        img.thumbnail(PREVIEW_SIZE)
        buf = BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    except Exception as exc:
        print(f'Failed to load preview for {filename}: {exc}')
        return None

def edit(id):
    def fetch_data():
        row = db.get_ingredients(id)
        # Format the cost field as currency with accuracy to 0.01 cents
        row['Cost'] = "$ {:.4f}".format(row['Cost'])
        return row
    
    row = fetch_data()
    name = row['Name']

    def layout_demographic():
        '''Generate the demographic info GUI layout for this Ingredient'''
        fields = []
        for (key, name) in config.ingredient_demographic_fields.items():
            if key=='Cost':
                fields.append( [[sg.Text(name), sg.Push(), sg.InputText(row[key], k=key, size=(12,1), disabled=True),sg.Button('Change', k='-EDITPRICE-'), sg.Button('History', k='-HISTORY-')]])
            else:
                fields.append([[sg.Text(name), sg.Push(), sg.InputText(row[key], k=key, size=(30,1), enable_events=True)]])
        return [fields]
    

    layout_nutrition = [sg.Frame('Nutrition',[
        [sg.Text(name), sg.Push(), sg.InputText(row[key], k=f'{key}', size=(10,1), enable_events=True)]
        for (key, name) in config.nutrition_fields.items()
    ])]

    allergens_list = db.get_ingredient_allergens(id)
    # 6 per row keeps the frame within the existing window width
    allergen_rows = [allergens_list[i:i+6] for i in range(0, len(allergens_list), 6)]
    layout_allergens = [sg.Frame('Allergens', [
        [sg.Checkbox(a['name'], default=bool(a['checked']), k=f"-ALLERGEN-::{a['id']}", enable_events=True) for a in row_]
        for row_ in allergen_rows
    ])]

    current_image = row.get('ImageFilename') or ''
    layout_image = [sg.Frame('Image', [
        [sg.Text('File'),
         sg.Combo(_available_images(), default_value=current_image, k='ImageFilename', size=(40, 1), readonly=True, enable_events=True),
         sg.Button('Refresh', k='-REFRESH-IMAGES-')],
        [sg.Image(data=_image_thumbnail(current_image), k='-IMAGE-PREVIEW-', size=PREVIEW_SIZE)],
    ])]

    layout_buttons = [sg.Button('Save', key='-SAVE-'),
                      sg.Button('Delete Ingredient', key='-DELETE-', button_color=("white","red")),
                      sg.Button('Close', button_color=("white","gray"), k='-CLOSE-')
        ]

    layout = [  layout_demographic(),
                layout_nutrition,
                layout_allergens,
                layout_image,
                layout_buttons ]

    # Create the Window
    window = window_utils.subwindow(f"{config.APPNAME} | {row['Name']}", layout, icon=config.ICON)
    # Event Loop to process "events" and get the "values" of the inputs
    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == '-CLOSE-': # if user closes window or clicks cancel
            print('Closing without saving changes')
            break
        
        elif event == '-SAVE-':
            db.update_ingredient(id,values)
            break
        elif event == '-DELETE-':
            ch = sg.popup_ok_cancel(f'Delete {name}?',title='Delete')
            if ch == 'OK':
                try:
                    db.delete_ingredient(id)
                    break
                except Exception as err:
                    sg.popup_ok(err, title="Ingredient In Use")

        elif event in config.nutrition_fields or event in ('Weight', 'Cost'):
            # Strip all characters from the input that aren't valid numbers
            new = sub(r'[^\d\.]', '', values[event])
            # Format the currency
            if event == 'Cost':
                new = '$ ' + new
            # Set the input field to the result
            window[event].update(new)

        elif event == '-EDITPRICE-':
            ingredient_prices.edit_one(id)
            new = fetch_data()
            for key in new:
                if key in values.keys():
                    window[key].update(new[key])
        elif event == '-HISTORY-':
            pricehistory.render(id, name)
        elif event.startswith('-ALLERGEN-'):
            allergen_id = int(event.split('::')[1])
            db.modify_ingredient_allergen(id, allergen_id, values[event])
        elif event == '-REFRESH-IMAGES-':
            window['ImageFilename'].update(values=_available_images(), value=values['ImageFilename'])
            window['-IMAGE-PREVIEW-'].update(data=_image_thumbnail(values['ImageFilename']))
        elif event == 'ImageFilename':
            window['-IMAGE-PREVIEW-'].update(data=_image_thumbnail(values['ImageFilename']))
        else:
            print('Unhandled Event', event, values, )

    window_utils.unregister_active(window)
    window.close()


def create(params={}):
    def value_from_params(key):
        try:
            value = params[key]
        except:
            value = ''
        return value

    # All the stuff inside your window.
    layout_demographic = [[
        [sg.Push(), sg.Text(name), sg.InputText('$ 0' if key=='Cost' else value_from_params(key),k=key, size=(30,1), enable_events=True)]
        for (key, name) in config.ingredient_demographic_fields.items()
    ]]
    layout_nutrition = [sg.Frame('Nutrition',[
        [sg.Push(), sg.Text(name), sg.InputText(value_from_params(key),k=key, size=(10,1), enable_events=True)] 
        for (key, name) in config.nutrition_fields.items()
    ])]
    layout_buttons = [sg.Button('Save', key='-SAVE-'), 
                      sg.Button('Cancel', button_color=("white","gray"), k='-CLOSE-')]

    layout = [  layout_demographic,  
                layout_nutrition,
                layout_buttons ]
    
    # if we don't get a new Id, we'll return 0
    id=0
    # Create the Window
    window = window_utils.subwindow(f'{config.APPNAME} | > NEW INGREDIENT <', layout, icon=config.ICON)
    # Event Loop to process "events" and get the "values" of the inputs
    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == '-CLOSE-': # if user closes window or clicks cancel
            print('Closing without saving changes')
            break
        elif event == '-SAVE-': # save changes to database
            id = db.create_ingredient(values)
            print(f'Created new Ingredient id: {id}')
            break

        elif event in config.nutrition_fields or event in ('Weight', 'Cost'):
            # Strip all characters from the input that aren't valid numbers
            new = sub(r'[^\d\.]', '', values[event])
            # Format the currency
            if event == 'Cost':
                new = '$ ' + new
            # Set the input field to the result
            window[event].update(new)
        else:
            print('Unhandled Event', event, values)

    window_utils.unregister_active(window)
    window.close()
    return(id)