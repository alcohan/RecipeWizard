import PySimpleGUI as sg
import db
import recipe
import ingredient
import setup
import ingredients_module as ing

fields = ['Name','Unit','Cost','Calories','Components', 'Id']

def format_component_data(): # Fetch & format the data. Move the ID column to the end so we can access it but not display
    # nutrition_fields = ['Calories', 'TTLFatGrams', 'SatFatGrams', 'CholesterolMilligrams', 'SodiumMilligrams','CarbGrams','FiberGrams','SugarGrams','ProteinGrams']

    recipedata = db.recipes_overview()
    for row in recipedata:
        row['OutputQty'] = "{:0.2g}".format(row['OutputQty'])
        row['Cost'] = "$ {:0.2f}".format(row['Cost'])

    return [[row[field] for field in fields] for row in recipedata]

def reload_table():
    window['-RECIPES-TABLE-'].Update(values=format_component_data())

sg.theme('LightGrey1')   # Add a touch of color


# All the stuff inside your window.
menu_layout = [['&File', ['[not implemented] import from csv', '[not implemented] export to csv', '[not implemented] get csv template', '---', 'E&xit']],
              ['&Tools', ['&Refresh::-REFRESH-','Reset Database::-RESET-']],
              ['&Help', ['About']]]

layout_ingredients = sg.Frame('Ingredients',[[ing.render()]])
layout_recipes = sg.Frame('Recipes',[[
    sg.Table(values=format_component_data(),
                    headings=fields[:-1], 
                    max_col_width=25, 
                    auto_size_columns=True,
                    display_row_numbers=False,
                    justification='right',
                    bind_return_key=True,
                    num_rows=20,
                    key='-RECIPES-TABLE-'
                    )],
            [ sg.Button('New Recipe', key='-NEW-RECIPE-') ]])

layout = [[sg.Menu(menu_layout, k='-MENU-'),
          [layout_ingredients], 
          [layout_recipes]
          ]]


# Create the Window
window = sg.Window('Recipe Builder', layout, icon="editveggie2.ico")

# Event Loop to process "events" and get the "values" of the inputs
while True:
    event, values = window.read()
    if event in (sg.WIN_CLOSED, '-CLOSE-', 'Exit'): # if user closes window or clicks cancel
        break
    elif event == '-INGREDIENT-TABLE-':
        if(len(values['-INGREDIENT-TABLE-'])>0):
            row_index = values['-INGREDIENT-TABLE-'][0]
            clicked_row = window['-INGREDIENT-TABLE-'].get()[row_index]
            id = clicked_row[-1]
            print(f"Popup for {clicked_row[0]}")
            ingredient.edit(id)
        reload_table()

    elif event == '-RECIPES-TABLE-':
        if(len(values['-RECIPES-TABLE-'])>0):
            row_index = values['-RECIPES-TABLE-'][0]
            clicked_row = window['-RECIPES-TABLE-'].get()[row_index]
            id = clicked_row[-1]

            print(f"Popup for {clicked_row[0]}")
            recipe.edit(id)
        reload_table()
    elif event == '-NEW-RECIPE-':
        new_id = recipe.create()
        if(new_id):
            recipe.edit(new_id)
        reload_table()
    elif event in ('-RESET-', 'Reset Database::-RESET-'):
        print('running setup script')
        setup.initializeDB()
        reload_table()
    elif event in ('Refresh', 'Refresh::-REFRESH-'):
        print('Refreshing values')
        ing.reload_table(window)
        reload_table()
    else:
        print('Unhandled Event', event, values)

window.close()