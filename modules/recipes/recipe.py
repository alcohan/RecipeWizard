import PySimpleGUI as sg
import db
import config
import utils
import recipe_ingredient
import modules.recipes.recipe_ingredient_new as recipe_ingredient_new
from autocomplete import Autocomplete

def edit(id):
    '''
    Window Popup to edit the Recipe with Id=id
    '''
    # Config fields to display in the 'info' pane
    info = {'Weight': 'Weight (g)','Cost': 'Cost', 'Components': 'Components'}

    def fetch_recipe_data():
        data = db.recipe_info(id)
        # data['Cost'] = "${:.2f}".format(data['Cost'])
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


    layout_demographic = [sg.Frame('Recipe',[[
            sg.Column([
                [sg.Push(),sg.Text('Name'), sg.InputText(name, key='-NAME-')],
                [sg.Push(),sg.Text('Yield Unit'), sg.InputText(unit, key='-UNIT-')],
                [sg.Push(),sg.Text('Recipe Yield'), sg.InputText(yieldqty, key='-YIELDQTY-')]
            ]),
            # Use VPush() with expand_y=True to align button to the bottom of frame
            sg.Column([
                [sg.VPush()],
                [sg.Button('Update', k='-SAVE-')]
            ], expand_y=True)
        ]
    ])]


    taglist = db.get_recipe_tags(id)
    layout_tags = [sg.Frame('Tags',[
        [sg.Checkbox(tag['name'],default=tag['checked'], k=f"-TAG-::{tag['id']}", enable_events=True) for tag in taglist]
        # [sg.Column([[sg.Listbox(taglist, size=(12,len(taglist)))]]),sg.Column(a.layout)]
    ])]
    
    # Weight and Cost info
    layout_info = [sg.Frame(f'Info (per {unit})',[
        [ sg.Text(name), sg.Push(), sg.Text(this_recipe[key], k=key) ] 
        for (key, name) in info.items()
    ])]

    # Nutrition details info
    layout_nutrition = [sg.Frame(f'Nutrition (per {unit})',[
        [ sg.Text(name), sg.Push(),sg.Text(this_recipe[key], k=key) ] 
        for (key, name) in config.nutrition_fields.items()
    ])]

    # Control buttons
    layout_buttons = [
        # sg.Button('Save', key='-SAVE-'),
        sg.Button('Add Ingredient', k='-NEW-'), 
        sg.Button('Nutrition Label', k='-LABEL-'),
        sg.Button('Delete Recipe', key='-DELETE-', button_color=("white","red")),
        # sg.Button('Close', button_color=("white","gray"), k='-CLOSE-')
    ]
    
    # Display the recipe components
    layout_components_table = [sg.Frame('Components',[
        [sg.Table(values=format_component_data(), 
                        headings=headings, 
                        max_col_width=25, 
                        auto_size_columns=True,
                        display_row_numbers=False,
                        justification='right',
                        bind_return_key=True,
                        key='-TABLE-'
                        )]
        ]
    )]
    # All the stuff inside your window.
    layout = [[
        sg.Column([
            layout_demographic,
            layout_tags,
            layout_components_table,
            layout_buttons ]),
        sg.Column([
            layout_info,
            layout_nutrition
        ])
    ]]

    # Create the Window
    window = sg.Window(f'{config.APPNAME} | {name}', layout, icon=config.ICON)

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

        elif event == '-DELETE-':
            ch = sg.popup_ok_cancel(f'Delete {name}?',title='Delete')
            if ch == 'OK':
                try:
                    db.delete_recipe(id)
                    break
                except Exception as err:
                    sg.popup_ok(err, title="Recipe In Use")
                

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

        elif event == '-LABEL-': # open the nutrition label
            utils.open_nutrition_label(id)

        elif event.startswith('-TAG-'):
            # Get the ID from the end of the event
            tag_id = int(event.split("::")[1])
            # print('Updating tag id',tag_id, values[event])
            db.modify_recipe_tag(id, tag_id, values[event])
        else:
            print('Unhandled Event', event, values)

    window.close()


def create():
    '''
    Window popup to create a new recipe. Returns Id of the new row, or 0 otherwise.
    '''
    layout = [  [sg.Push(),sg.Text('Name'), sg.InputText( key='-NAME-')],
                [sg.Push(),sg.Text('Yield Unit'), sg.InputText( key='-UNIT-')],
                [sg.Push(),sg.Text('Recipe Yield'), sg.InputText( key='-YIELDQTY-')],
                [sg.Button('Save', key='-SAVE-'), sg.Button('Cancel', button_color=("white","gray"), k='-CLOSE-')] ]

    # if we don't get a new Id, we'll return 0
    id=0
    # Create the Window
    window = sg.Window(f'{config.APPNAME} | > NEW RECIPE <', layout, icon=config.ICON)
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