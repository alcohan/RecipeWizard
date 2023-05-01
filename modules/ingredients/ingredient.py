import PySimpleGUI as sg
import db
import config
import modules.ingredients.ingredient_prices as ingredient_prices
from re import sub

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
                fields += [[sg.Push(), sg.Text(name), sg.InputText(row[key], k=key, size=(16,1), disabled=True),sg.Button('Change Price', k='-EDITPRICE-')]]
            else:
                fields += [[sg.Push(), sg.Text(name), sg.InputText(row[key], k=key, size=(30,1), enable_events=True)]]
        return [fields]
    

    layout_nutrition = [sg.Frame('Nutrition',[
        [sg.Push(), sg.Text(name), sg.InputText(row[key], k=f'{key}', size=(10,1), enable_events=True)] 
        for (key, name) in config.nutrition_fields.items()
    ])]
    layout_buttons = [sg.Button('Save', key='-SAVE-'),
                      sg.Button('Delete Ingredient', key='-DELETE-', button_color=("white","red")),
                      sg.Button('Close', button_color=("white","gray"), k='-CLOSE-')]

    layout = [  layout_demographic(),  
                layout_nutrition,
                layout_buttons ]

    # Create the Window
    window = sg.Window(f"{config.APPNAME} | {row['Name']}", layout, icon=config.ICON)
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
        else:
            print('Unhandled Event', event, values, )

    window.close()


def create():
    # All the stuff inside your window.
    layout_demographic = [[
        [sg.Push(), sg.Text(name), sg.InputText('$ 0' if key=='Cost' else '',k=key, size=(30,1), enable_events=True)]
        for (key, name) in config.ingredient_demographic_fields.items()
    ]]
    layout_nutrition = [sg.Frame('Nutrition',[
        [sg.Push(), sg.Text(name), sg.InputText('',k=key, size=(10,1), enable_events=True)] 
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
    window = sg.Window(f'{config.APPNAME} | > NEW INGREDIENT <', layout, icon=config.ICON)
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

    window.close()
    return(id)