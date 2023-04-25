import PySimpleGUI as sg
import db
import recipe
import ingredient
import setup
import config
import ingredients_module as ing

fields = ['Name','Unit','Cost','Calories','Components', 'Id']

def format_recipes_data(): # Fetch & format the data. Move the ID column to the end so we can access it but not display
    recipedata = db.recipe_info()
    return [[row[field] for field in fields] for row in recipedata]

def refresh():
    window['-INGREDIENT-TABLE-'].Update(values=ing.format_data())
    window['-RECIPES-TABLE-'].Update(values=format_recipes_data())

sg.theme('LightGrey1')   # Add a touch of color


# All the stuff inside your window.
menu_layout = [['&File', ['[not implemented] import from csv', '[not implemented] export to csv', '[not implemented] get csv template', '---', 'E&xit']],
              ['&Tools', ['&Refresh::-REFRESH-','Reset Database::-RESET-']],
              ['&Help', ['About']]]

layout_ingredients = sg.Frame('Ingredients',[[ing.render()], [ sg.Button('New Ingredient', key='-NEW-INGREDIENT-') ]])
layout_recipes = sg.Frame('Recipes',[[
    sg.Table(values=format_recipes_data(),
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
window = sg.Window(f'Recipe Builder - {config.DATABASE}', layout, icon="editveggie2.ico")

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
        refresh()

    elif event == '-RECIPES-TABLE-':
        if(len(values['-RECIPES-TABLE-'])>0):
            row_index = values['-RECIPES-TABLE-'][0]
            clicked_row = window['-RECIPES-TABLE-'].get()[row_index]
            id = clicked_row[-1]

            print(f"Popup for {clicked_row[0]}")
            recipe.edit(id)
        refresh()
    elif event == '-NEW-RECIPE-':
        new_id = recipe.create()
        if(new_id):
            recipe.edit(new_id)
        refresh()
    elif event == '-NEW-INGREDIENT-':
        new_id = ingredient.create()
        if(new_id):
            ingredient.edit(new_id)
        refresh()
    elif event in ('-RESET-', 'Reset Database::-RESET-'):
        print('running setup script')
        setup.initializeDB()
        refresh()
    elif event in ('Refresh', 'Refresh::-REFRESH-'):
        print('Refreshing values')
        ing.reload_table(window)
        refresh()
    else:
        print('Unhandled Event', event, values)

window.close()