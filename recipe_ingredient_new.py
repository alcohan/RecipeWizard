import PySimpleGUI as sg
import db

def popup(parent):
    '''
    Window to add an ingredient to parent recipes
    '''
    parent_id, parent_name, *_ = parent

    # autocomplete setup
    data = db.get_eligible_ingredients(parent_id)
    choices = [f'{d[2]} ({d[3]}) - {d[1]}[{d[0]}]' for d in data]
    input_width = 60
    num_items_to_show = 10
    #autocomplete setup

    window_title = f'{parent_name} | > NEW <'
    
    layout = [  [sg.Text(f'Add to {parent_name}')],
                [sg.Input(size=(input_width, 1), enable_events=True, key='-IN-')],
                [sg.pin(sg.Col([[sg.Listbox(values=choices, size=(input_width, num_items_to_show), enable_events=True, key='-BOX-',
                                            select_mode=sg.LISTBOX_SELECT_MODE_SINGLE, no_scrollbar=True)]],
                                            key='-BOX-CONTAINER-', pad=(0, 0), visible=True))],
                [sg.Text(f'Qty'), sg.InputText(1, key='-QTY-', size=(15,1)), sg. Text('',k='-SELECTED-UNIT-')],
                [sg.Button('Save', key='-SAVE-'), sg.Button('Cancel', button_color=("white","gray"), k='-CLOSE-')]
            ]

    # Create the Window
    window = sg.Window(window_title, layout, return_keyboard_events=True, finalize=True, icon="editveggie2.ico")
    # Event Loop to process "events" and get the "values" of the inputs

    list_element:sg.Listbox = window.Element('-BOX-')           # store listbox element for easier access and to get to docstrings
    prediction_list, input_text, sel_item = [], "", 0

    # Handle item selected from the listbox
    def handle_select():
        value = values['-BOX-'][0]
        window['-IN-'].update(value)

        #get the index of selected row and reference back to data source
        index = choices.index(value) if value in choices else -1
        _, _, _, unit = data[index]

        window['-SELECTED-UNIT-'].update(f'× {unit}')
        window['-BOX-CONTAINER-'].update(visible=False)

    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == '-CLOSE-': # if user closes window or clicks cancel
            print('Closing without saving changes')
            break
        elif event == '-SAVE-': # save changes to database
            if len(values['-BOX-']) > 0: 
                value = values['-BOX-'][0]
                index = choices.index(value) if value in choices else -1
                id, mode, selected_ingredient, _ = data[index]
                print(f"Adding {values['-QTY-']} {selected_ingredient} to {parent_name}")
                db.add_recipe_ingredient(parent_id, mode, id,values['-QTY-'])
                break

        # autocomplete combo box handling
        elif event.startswith('Escape'):
            window['-IN-'].update('')
            window['-BOX-CONTAINER-'].update(visible=True)
        elif event.startswith('Down') and len(prediction_list):
            sel_item = (sel_item + 1) % len(prediction_list)
            list_element.update(set_to_index=sel_item, scroll_to_index=sel_item)
        elif event.startswith('Up') and len(prediction_list):
            sel_item = (sel_item + (len(prediction_list) - 1)) % len(prediction_list)
            list_element.update(set_to_index=sel_item, scroll_to_index=sel_item)
        elif event == '\r':
            if len(values['-BOX-']) > 0:
                handle_select()
        elif event == '-IN-':
            text = values['-IN-'].lower()
            if text == input_text:
                continue
            else:
                input_text = text
            # prediction_list = []
            # if text:
            prediction_list = [item for item in choices if text in item.lower()]

            list_element.update(values=prediction_list)
            sel_item = 0
            list_element.update(set_to_index=sel_item)

            if len(prediction_list) > 0:
                window['-BOX-CONTAINER-'].update(visible=True)
            else:
                window['-BOX-CONTAINER-'].update(visible=False)
        elif event == '-BOX-':
            handle_select()
        # end autocomplete handling

        # else:
        #     print('Unhandled Event', event, values)

    window.close()

