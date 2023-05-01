import PySimpleGUI as sg
from config import ICON

def render():
    '''
    Popup window for "About" this application
    '''
    # Define the layout for the popup window
    layout = [[sg.Text('RecipeWizard v0.10')],
            [sg.Text('Author: Adrian Cohan')]]

    # Create the popup window
    window = sg.Window('About', layout,icon=ICON)

    # Display the popup window and wait for a button press
    event, values = window.read()

    # Close the popup window
    window.close()
