import PySimpleGUI as sg
import config
import db

def popup(parent,child):
    '''
    Edit ingredient child from recipe parent
    '''
    parent_id, parent_name, *_ = parent
    child_name, child_qty, child_unit, mode, _, child_id = child

    window_title = f'{parent_name} | {child_name}'
    
    layout = [  [sg.Text(f'Editing {child_name} in {parent_name}')],
                [sg.Text(f'Qty ({child_unit})'), sg.InputText(child_qty, key='-QTY-')],
                [sg.Button('Save', key='-SAVE-'), sg.Button('Delete', key='-DELETE-', button_color=("white","red")), sg.Button('Cancel', button_color=("white","gray"))]
            ]

    # Create the Window
    window = sg.Window(window_title, layout, icon=config.ICON)
    # Event Loop to process "events" and get the "values" of the inputs

    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == 'Cancel': # if user closes window or clicks cancel
            print('Closing without saving changes')
            break
        elif event == '-SAVE-': # save changes to database
            print(f"Update {child_name} on {parent_name} to qty {values['-QTY-']}")
            db.update_recipe_ingredient(parent_id,mode,child_id,values['-QTY-'])
            break
        elif event == '-DELETE-':
            print(f'Deleted {child_name} from {parent_name}')
            db.delete_recipe_ingredient(parent_id,mode,child_id)
            break
        else:
            print('Unhandled Event', event, values)

    window.close()
