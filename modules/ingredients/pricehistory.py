import PySimpleGUI as sg
from config import ICON

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib import use as use_agg
import matplotlib.dates as mdates

from datetime import datetime
from db import get_price_history, get_recipe_price_history, get_recipe_price_history_details

use_agg('TkAgg')

def render(id, name='Ingredient', recipeMode=False):
    '''
    Render the price history popup for ingredient id {id}
    '''
    # Draw the figure on the canvas
    def draw_figure(canvas, figure):
        tkcanvas = FigureCanvasTkAgg(figure, canvas)
        tkcanvas.draw()
        tkcanvas.get_tk_widget().pack(side='top', fill='both', expand=1)
        return tkcanvas
    
    def pack_figure(graph, figure):
        canvas = FigureCanvasTkAgg(figure, graph.Widget)
        plot_widget = canvas.get_tk_widget()
        plot_widget.pack(side='top', fill='both', expand=1)
        return plot_widget
        
    def generate_figure(data):
        '''
        Generate the figure. Expects a dictionary with values 'date' and 'price'
        '''
        # Extract the dates and prices
        dates = [datetime.strptime(d['date'], '%Y-%m-%d') for d in data]
        prices = [d['price'] for d in data]

        # Activate the figure
        fig = plt.figure(1)
        ax = plt.gca()

        # Clear the current axes
        ax.cla()

        # Plot the data
        ax.plot_date(dates, prices, linestyle='solid')

        # Add labels and title
        ax.set_xlabel('Date')
        ax.set_ylabel('Price')
        ax.set_title(name)

        # Set y-axis minimum to 0
        ax.set_ylim([0, max(prices)*1.1])
        ax.yaxis.set_major_formatter('${x:1.2f}')

        # Rotate x-axis tick labels and show labels for fewer dates
        locator = mdates.AutoDateLocator()
        formatter = mdates.ConciseDateFormatter(locator)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(formatter)
        plt.xticks(rotation=45, ha='right')
        fig.subplots_adjust(bottom=0.2)

        # Add labels to data points
        for i, price in enumerate(prices):
            ax.text(dates[i], price, f"${price:.2f}", ha='center', va='bottom')

        fig.canvas.draw()
    
    def generate_pie_plot(data, date):
        '''Create a pie plot with ingredient breakdown. Expects a dictionary with values 'Name' and 'price'
        '''
        labels = [f"{item['Name']} ${item['price']:.2f}" for item in data]
        values = [item['price'] for item in data]

        fig = plt.figure(2)
        ax = plt.gca()
        # Clear the plot
        ax.cla()
        
        ax.set_title(f"{name} {date}")
        # Creating the pie chart
        ax.pie(values, labels=labels, autopct='%1.1f%%')
        # Setting aspect ratio to be equal so that pie is drawn as a circle
        ax.axis('equal')
        fig.canvas.draw()

    def plot_pieplot(date):
        data = get_recipe_price_history_details(id, date)
        generate_pie_plot(data, date)


    
    # Retrieve price history data from database
    if recipeMode:
        price_history = get_recipe_price_history(id)
        # Create table layout
        table_data = [[row['date'], "$ {:.2f}".format(row['price'])] for row in price_history]
        table_headings = ['Date', 'Unit Price']
    else:
        # Create table layout
        price_history = get_price_history(id)
        table_data = [[row['date'], "$ {:.4f}".format(row['price']), row['supplier']] for row in price_history]
        table_headings = ['Date', 'Unit Price', 'Supplier']


    layout_table = [[sg.Table(values=table_data, headings=table_headings, num_rows=20, auto_size_columns=False, k='-TABLE-')],[sg.VPush()]]
    layout_graph = [ 
                    [sg.Graph((640, 480),(0,0),(640,480),key='-CANVAS-', border_width=5),
                    sg.Graph((640, 480),(0,0),(640,480),key='-CANVAS2-', border_width=5, visible=False)]
    ]
    if recipeMode:
        buttons = [
                    [sg.Button('Ingredient Breakdown', k='-SHOW-PIE-PLOT-')],
                    [sg.Button('Cost History', k='-SHOW-LINE-CHART-')]]
        layout_graph = buttons + layout_graph

    layout = [
        [sg.Column(layout_table, expand_y=True), sg.Column(layout_graph)]
    ]

    # Create window
    window = sg.Window(f'Price History [{name}]', layout, finalize=True, icon=ICON)
    if len(price_history)>0:
        graph1 = window['-CANVAS-']
        graph2 = window['-CANVAS2-']
        plt.ioff()
        fig1 = plt.figure(1)
        ax1 = plt.subplot(111)
        fig2 = plt.figure(2)
        ax2 = plt.subplot(111)
        pack_figure(graph1, fig1)
        pack_figure(graph2,fig2)
        generate_figure(price_history)

    # Event loop
    while True:
        event, values = window.read()
        if event == sg.WINDOW_CLOSED or event == 'Exit':
            break
        if event == '-SHOW-PIE-PLOT-':
            if len(values['-TABLE-']) > 0:
                selected_row = values['-TABLE-'][-1]
            else:
                selected_row = -1
            date_to_query = price_history[selected_row]['date']
            plot_pieplot(date_to_query)

            graph1.update(visible=False)
            graph2.update(visible=True)

        if event == '-SHOW-LINE-CHART-':
            generate_figure(price_history)
            graph1.update(visible=True)
            graph2.update(visible=False)
    # Close window
    window.close()

if __name__=='__main__':
    render(2)