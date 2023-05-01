import PySimpleGUI as sg
import db
import modules.recipes.recipe as recipe
from functools import cache

fields = ['Name','Unit','Cost','Calories','Components', 'Id']

@cache
def format_recipes_data(): # Fetch & format the data. Move the ID column to the end so we can access it but not display
    print('fetching recipe data')
    recipedata = db.recipe_info()
    return [[row[field] for field in fields] for row in recipedata]

def render():
    return [
        [sg.Text('🔍'), sg.InputText('',enable_events=True, k='-RECIPES-FILTER-')],
        [sg.Table(values=format_recipes_data(),
                    headings=fields[:-1], 
                    max_col_width=25, 
                    auto_size_columns=True,
                    display_row_numbers=False,
                    justification='right',
                    bind_return_key=True,
                    num_rows=20,
                    key='-RECIPES-TABLE-'
                    )],
            [ sg.Button('New Recipe', key='-NEW-RECIPE-') ]
    ]

def loop(event, values, window):
    '''Run the event loop for Recipes. Return values: 0=nothing, 1=event processed, 2=event processed + refresh needed'''

    if event == '-RECIPES-TABLE-':
        if(len(values['-RECIPES-TABLE-'])==0):
            return 1
        row_index = values['-RECIPES-TABLE-'][0]
        clicked_row = window['-RECIPES-TABLE-'].get()[row_index]
        id = clicked_row[-1]

        print(f"Popup for {clicked_row[0]}")
        recipe.edit(id)
        return 2
    elif event == '-NEW-RECIPE-':
        new_id = recipe.create()
        if new_id==0:
            return 1
        recipe.edit(new_id)
        return 2
    elif event == '-RECIPES-FILTER-':
        print('Searching for: ', values[event])
        filter_value = values['-RECIPES-FILTER-'].lower()
        filtered_data = [row for row in format_recipes_data() if filter_value in ' '.join(map(str, row)).lower()]
        window['-RECIPES-TABLE-'].Update(values=filtered_data)
        return 1
    # 0 if we didn't do anything
    return 0