import PySimpleGUI as sg
import db  # assuming you have a db module with a get_tags() and update_tag() function

def render():
    # Define the PySimpleGUI layout
    layout = [
        [sg.Text('Edit Tags')],
        [sg.HorizontalSeparator()],
    ]

    # Fetch the tags data using db.get_tags() and add a label and edit button for each tag
    tags = db.get_tags()
    for tag in tags:
        layout.append([
            sg.InputText(tag['name'], key=f'input_{tag["id"]}', size=(20,1), disabled=True),
            sg.Button('Edit', key=f'edit_{tag["id"]}', visible=True),
            sg.Button('Save', key=f'save_{tag["id"]}', visible=False)
        ])

    # Add a Submit button at the bottom of the window
    layout.append([sg.Submit()])

    # Create the PySimpleGUI window
    window = sg.Window('Edit Tags', layout)

    # Event loop
    while True:
        event, values = window.read()

        if event == sg.WIN_CLOSED:
            break

        # If the event is an edit button, hide the edit button and show the save button and input field
        for tag in tags:
            if event == f'edit_{tag["id"]}':
                window[f'input_{tag["id"]}'].update(disabled=False)
                window[f'edit_{tag["id"]}'].update(visible=False)
                window[f'save_{tag["id"]}'].update(visible=True)

            # If the event is a save button, call db.update_tag() with the new tag name and update the label and button back to their original state
            elif event == f'save_{tag["id"]}':
                new_tag_name = values[f'input_{tag["id"]}']
                db.update_tag(tag['id'], new_tag_name)
                window[f'edit_{tag["id"]}'].update(visible=True)
                window[f'save_{tag["id"]}'].update(visible=False)
                window[f'input_{tag["id"]}'].update(disabled=True)

        # If the event is the Submit button, close the window
        if event == 'Submit':
            break

    # Close the window
    window.close()
