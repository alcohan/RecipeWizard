import PySimpleGUI as sg
import db
import recipe
import setup

headings = ['Name','Unit','Yield','Weight','Cost','Calories','TTLFat','SatFat','Choles','Sodium','Carb','Fiber','Sugar','Protein']

def format_data(): # Fetch & format the data. Move the ID column to the end so we can access it but not display
    data = db.query()
    return [(name, unit, yd, weight, "${:.2f}".format(cost), calories, fat, satfat, choles, sodium, carb, fiber, sugar, protein, id) 
            for id, name, unit, yd, weight, cost, calories, fat, satfat, choles, sodium, carb, fiber, sugar, protein in data]

def reload_table():
    window['-TABLE-'].Update(values=format_data())

sg.theme('LightGrey')   # Add a touch of color

# All the stuff inside your window.
layout = [# [sg.Text('Enter something on Row 2'), sg.InputText()],
            [sg.Table(values=format_data(),
                    headings=headings, 
                    max_col_width=25, 
                    auto_size_columns=True,
                    display_row_numbers=False,
                    justification='right',
                    bind_return_key=True,
                    num_rows=20,
                    key='-TABLE-'
                    )],
            [sg.Button('Setup'), sg.Button('Cancel'), sg.Button('Refresh')] 
        ]

# Create the Window
window = sg.Window('Recipe Builder', layout)
# Event Loop to process "events" and get the "values" of the inputs
while True:
    event, values = window.read()
    if event == sg.WIN_CLOSED or event == 'Cancel': # if user closes window or clicks cancel
        break
    elif event == '-TABLE-':
        row_index = values['-TABLE-'][0]
        clicked_row = window['-TABLE-'].get()[row_index]
        id = clicked_row[-1]

        print(f"Popup for {clicked_row[0]}")
        recipe.recipePopup(id)
        reload_table()
    elif event == 'Setup':
        print('running setup script')
        setup.initializeDB()
        reload_table()
    elif event == 'Refresh':
        print('Refreshing values')
        reload_table()
    else:
        print('Unhandled Event', event, values)

window.close()