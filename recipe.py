import PySimpleGUI as sg
import db
import config
import recipe_ingredient
import recipe_ingredient_new

def edit(id):
    # Config fields to display in the 'info' pane
    info = ['Weight','Cost', 'Components']

    def fetch_recipe_data():
        data = db.recipe_detailedinfo(id)[0]
        data['Cost'] = "${:.2f}".format(data['Cost'])
        return data

    this_recipe = fetch_recipe_data()
    name, unit, yieldqty = this_recipe['Name'], this_recipe['Unit'], this_recipe['OutputQty']

    # Exclude the last item (Id) from the fields to use as headings
    headings = db.recipe_components_fields[:-1]

    # Config for recipe components table display
    def format_component_data():
        data = db.recipe_components(id)
        return [[row[field] for field in db.recipe_components_fields] for row in data]

    def refresh():
        # update the components table
        window['-TABLE-'].Update(values=format_component_data())

        # update the calcualted values
        new_data = fetch_recipe_data()
        for field in config.nutrition_fields:
            window[field].update(new_data[field])
        for field in info:
            window[field].update(new_data[field])


    layout_demographic = [sg.Frame('',[
        [sg.Push(),sg.Text('Name'), sg.InputText(name, key='-NAME-')],
        [sg.Push(),sg.Text('Yield Unit'), sg.InputText(unit, key='-UNIT-')],
        [sg.Push(),sg.Text('Recipe Yield'), sg.InputText(yieldqty, key='-YIELDQTY-')]
    ])]
    
    # Weight and Cost info
    layout_info = [sg.Frame(f'Info (per {unit})',[
        [ sg.Text(field), sg.Push(), sg.Text(this_recipe[field], k=field) ] 
        for field in info
    ])]

    # Nutrition details info
    layout_nutrition = [sg.Frame(f'Nutrition (per {unit})',[
        [ sg.Text(field), sg.Push(),sg.Text(this_recipe[field], k=field) ] 
        for field in config.nutrition_fields
    ])]

    # Control buttons
    layout_buttons = [
        sg.Button('Save', key='-SAVE-'),
        sg.Button('Add Ingredient', k='-NEW-'), 
        sg.Button('Close', button_color=("white","gray"), k='-CLOSE-')
    ]
    
    # Display the recipe components
    layout_components_table = [sg.Table(values=format_component_data(), 
                        headings=headings, 
                        max_col_width=25, 
                        auto_size_columns=True,
                        display_row_numbers=False,
                        justification='right',
                        bind_return_key=True,
                        key='-TABLE-'
                        )]
    
    # All the stuff inside your window.
    layout = [[
        sg.Column([
            layout_demographic,
            layout_components_table,
            layout_buttons ]),
        sg.Column([
            layout_info,
            layout_nutrition
        ])
    ]]

    # Create the Window
    window = sg.Window(name, layout, icon="editveggie2.ico")
    # Event Loop to process "events" and get the "values" of the inputs
    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == '-CLOSE-': # if user closes window or clicks cancel
            print('Closing without saving changes')
            break
        elif event == '-SAVE-': # save changes to database
            name = values['-NAME-']
            unit = values['-UNIT-']
            qty = values['-YIELDQTY-']
            db.update_recipe_info(id,name,unit,qty)
            print(f'Saving changes to id: {id} name: {name} unit: {unit} yield: {qty}')
            break
        elif event == '-TABLE-': # Handle clicking on a table row
            row_index = values['-TABLE-'][0]
            clicked_row = window['-TABLE-'].get()[row_index]
            print('Clicked Ingredient', clicked_row)
            child_id = clicked_row[-1]
            mode = clicked_row[3]
            qty = clicked_row[1]

            recipe_ingredient.popup([id, name], clicked_row)
            refresh()
        elif event == '-NEW-':
            recipe_ingredient_new.popup([id, name])
            refresh()
        else:
            print('Unhandled Event', event, values)

    window.close()


def create():
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
        elif event == '-SAVE-': # save changes to database
            name = values['-NAME-']
            unit = values['-UNIT-']
            qty = values['-YIELDQTY-']
            id = db.create_recipe(name,unit,qty)
            print(f'Created new recipe id: {id} name: {name} unit: {unit} yield: {qty}')
            break

        else:
            print('Unhandled Event', event, values)

    window.close()
    return(id)