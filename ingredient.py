import PySimpleGUI as sg
import db
import config

def edit(id):
    row = db.get_ingredients(id)[0]
    # Format the cost field as currency with accuracy to 0.01 cents
    row['Cost'] = "${:.4f}".format(row['Cost'])

    layout_demographic = [[[sg.Push(), sg.Text(field), sg.InputText(row[field], k=field, size=(30,1))] for field in config.ingredient_demographic_fields]]
    layout_nutrition = [sg.Frame('Nutrition',[[sg.Push(), sg.Text(field), sg.InputText(row[field], k=f'{field}', size=(10,1))] for field in config.nutrition_fields])]

    # All the stuff inside your window.
    layout = [  layout_demographic,  
                layout_nutrition,
                [sg.Button('Save', key='-SAVE-'),sg.Button('Close', button_color=("white","gray"), k='-CLOSE-')] ]

    # Create the Window
    window = sg.Window(row['Name'], layout, icon="editveggie2.ico")
    # Event Loop to process "events" and get the "values" of the inputs
    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == '-CLOSE-': # if user closes window or clicks cancel
            print('Closing without saving changes')
            break
        # elif event == '-SAVE-': # save changes to database
        #     name = values['-NAME-']
        #     unit = values['-UNIT-']
        #     qty = values['-PORTION-']
        #     db.update_recipe_info(id,name,unit,qty)
        #     print(f'Saving changes to id: {id} name: {name} unit: {unit} yield: {qty}')
        #     break
        else:
            print('Unhandled Event', event, values)

    window.close()


def create():
    sg.theme('LightGrey')   # Add a touch of color
    # All the stuff inside your window.
    layout = [  [sg.Push(),sg.Text('Name'), sg.InputText( key='-NAME-')],
                [sg.Push(),sg.Text('Yield Unit'), sg.InputText( key='-UNIT-')],
                [sg.Push(),sg.Text('Recipe Yield'), sg.InputText( key='-YIELDQTY-')],
                [sg.Button('Save', key='-SAVE-'), sg.Button('Cancel', button_color=("white","gray"), k='-CLOSE-')] ]

    # if we don't get a new Id, we'll return 0
    id=0
    # Create the Window
    window = sg.Window('> NEW RECIPE <', layout, icon="editveggie2.ico")
    # Event Loop to process "events" and get the "values" of the inputs
    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == '-CLOSE-': # if user closes window or clicks cancel
            print('Closing without saving changes')
            break
        # elif event == '-SAVE-': # save changes to database
        #     name = values['-NAME-']
        #     unit = values['-UNIT-']
        #     qty = values['-YIELDQTY-']
        #     id = db.create_recipe(name,unit,qty)
        #     print(f'Created new recipe id: {id} name: {name} unit: {unit} yield: {qty}')
        #     break

        else:
            print('Unhandled Event', event, values)

    window.close()
    return(id)