import PySimpleGUI as sg
import db
import recipe_ingredient
import recipe_ingredient_new

def recipePopup(id):
    headings = ['Ingredient', 'Quantity', 'Unit', 'Type', 'Cost']

    row = db.recipeinfo(id)[0]
    name, unit, yieldqty, id = row
    def format_data():
        data = db.recipedetails(id)
        return [(name, qty, unit, type, "${:.2f}".format(cost), id) for name, qty, unit, type, cost, id in data]

    def reload_table():
        window['-TABLE-'].Update(values=format_data())

    sg.theme('LightGrey')   # Add a touch of color
    # All the stuff inside your window.
    layout = [  [sg.Push(),sg.Text('Name'), sg.InputText(name, key='-NAME-')],
                [sg.Push(),sg.Text('Yield Unit'), sg.InputText(unit, key='-UNIT-')],
                [sg.Push(),sg.Text('Yield Qty'), sg.InputText(yieldqty, key='-YIELDQTY-')],
                [sg.Table(values=format_data(), 
                        headings=headings, 
                        max_col_width=25, 
                        auto_size_columns=True,
                        display_row_numbers=False,
                        justification='right',
                        bind_return_key=True,
                        key='-TABLE-'
                        )],
                [sg.Button('Save', key='-SAVE-'),sg.Button('New Ingredient', k='-NEW-'), sg.Button('Cancel')] ]

    # Create the Window
    window = sg.Window(name, layout)
    # Event Loop to process "events" and get the "values" of the inputs
    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == 'Cancel': # if user closes window or clicks cancel
            print('Closing without saving changes')
            break
        elif event == '-SAVE-': # save changes to database
            name = values['-NAME-']
            unit = values['-UNIT-']
            qty = values['-YIELDQTY-']
            db.updaterecipe(id,name,unit,qty)
            print('Saving changes to id: {id} name: {name} unit: {unit} yield: {qty}')
            break
        elif event == '-TABLE-': # Handle clicking on a table row
            row_index = values['-TABLE-'][0]
            clicked_row = window['-TABLE-'].get()[row_index]
            print('Clicked Ingredient', clicked_row)
            child_id = clicked_row[-1]
            mode = clicked_row[3]
            qty = clicked_row[1]

            recipe_ingredient.popup(row, clicked_row)
            reload_table()
        elif event == '-NEW-':
            recipe_ingredient_new.popup(row)
            reload_table()
        else:
            print('Unhandled Event', event, values)

    window.close()