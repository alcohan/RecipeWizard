import PySimpleGUI as sg
import db  # assuming you have a db module with a get_tags() and update_tag() function

def render():
    # Define the PySimpleGUI layout
    layout = [
        [sg.Text('Edit Tags')],
        [sg.HorizontalSeparator()],
    ]

    def render_tag(name, id):
        return [
            sg.InputText(name, key=f'input_{id}', size=(20,1), disabled=True),
            sg.Button('Edit', key=f'edit_{id}', visible=True, size=(6,1), pad=(0,0)),
            sg.Button('✓', key=f'save_{id}', visible=False, pad=(3,0)),
            sg.Button('␡', key=f'delete_{id}', visible=False, pad=(3,0))
        ]
    # Fetch the tags data using db.get_tags() and add a label and edit button for each tag
    tags = db.get_tags()
    layout.append([sg.Column(
        [render_tag(tag['name'],tag['id']) for tag in tags],
        k='-TAGSCOL-'
    )])

    # Add a Submit button at the bottom of the window
    layout.append([sg.Button('New', k='-NEW-')])

    # Create the PySimpleGUI window
    window = sg.Window('Edit Tags', layout)

    # Event loop
    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED:
            break

        # If the event is an edit button, hide the edit button and show the save button and input field
        # for tag in tags:
        if event.startswith('edit_'):
            tag_id = event.split('_')[1]
            window[f'input_{tag_id}'].update(disabled=False)
            window[f'edit_{tag_id}'].update(visible=False)
            window[f'save_{tag_id}'].update(visible=True)
            window[f'delete_{tag_id}'].update(visible=True)

            # If the event is a save button, call db.update_tag() with the new tag name and update the label and button back to their original state
        elif event.startswith('save_'):
            tag_id = event.split('_')[1]
            new_tag_name = values[f'input_{tag_id}']
            db.update_tag(tag_id, new_tag_name)
            window[f'edit_{tag_id}'].update(visible=True)
            window[f'save_{tag_id}'].update(visible=False)
            window[f'delete_{tag_id}'].update(visible=False)
            window[f'input_{tag_id}'].update(disabled=True)

        elif event.startswith('delete_'):
            tag_id = event.split('_')[1]
            db.delete_tag(tag_id)
            window[f'edit_{tag_id}'].hide_row()
        # Handle creating a new tag
        if event == '-NEW-':
            input = sg.popup_get_text('Enter a name for the new tag','New Tag', default_text='Tag')
            if input == None:
                continue
            new_id = db.create_tag(input)
            window.extend_layout(window['-TAGSCOL-'], rows=[render_tag(input, new_id)])

    # Close the window
    window.close()
