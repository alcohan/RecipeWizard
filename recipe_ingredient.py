import PySimpleGUI as sg
import db

def popup(parent,child):
    sg.theme('LightGrey')   # Add a touch of color

    parent_name, _, _, parent_id = parent
    child_name, child_qty, child_unit, mode, _, child_id = child

    window_title = f'{parent_name} | {child_name}'
    
    layout = [  [sg.Text(f'Editing {child_name} in {parent_name}')],
                [sg.Text(f'Qty ({child_unit})'), sg.InputText(child_qty, key='-QTY-')],
                [sg.Button('Save', key='-SAVE-'), sg.Button('Cancel')]
            ]

    # Create the Window
    window = sg.Window(window_title, layout)
    # Event Loop to process "events" and get the "values" of the inputs

    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == 'Cancel': # if user closes window or clicks cancel
            print('Closing without saving changes')
            break
        elif event == '-SAVE-': # save changes to database
            print(f"Update {child_name} on {parent_name} to qty {values['-QTY-']}")
            db.update_ingredient(parent_id,mode,child_id,values['-QTY-'])
            break

        else:
            print('Unhandled Event', event, values)

    window.close()
