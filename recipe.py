import PySimpleGUI as sg
import db

def recipePopup(id):
    row = db.recipeinfo(id)[0]
    id, name, unit, yieldqty, *_ = row
    data = db.recipedetails(id)
    headings = ['Ingredient', 'Quantity', 'Unit', 'Type', 'Cost']
    data_format = [(name, qty, unit, type, "${:.2f}".format(cost)) for name, qty, unit, type, cost in data]

    sg.theme('LightGrey')   # Add a touch of color
    # All the stuff inside your window.
    layout = [  [sg.Push(),sg.Text('Name'), sg.InputText(name, key='-NAME-')],
                [sg.Push(),sg.Text('Yield Unit'), sg.InputText(unit, key='-UNIT-')],
                [sg.Push(),sg.Text('Yield Qty'), sg.InputText(yieldqty, key='-YIELDQTY-')],
                [sg.Table(values=data_format, 
                        headings=headings, 
                        max_col_width=25, 
                        auto_size_columns=True,
                        display_row_numbers=False,
                        justification='right',
                        bind_return_key=False,
                        key='-TABLE-'
                        )],
                [sg.Button('Save', key='-SAVE-'), sg.Button('Cancel')] ]

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
        else:
            print('Unhandled Event', event, values)

    window.close()