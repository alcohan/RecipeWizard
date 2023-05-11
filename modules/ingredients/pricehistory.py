import PySimpleGUI as sg
from config import ICON

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib import use as use_agg
import matplotlib.dates as mdates

from datetime import datetime
from db import get_price_history, get_recipe_price_history, get_recipe_price_history_details, get_recipe_price_history_dates

from functools import cache

use_agg('TkAgg')

def render(id, name='Ingredient', recipeMode=False):
    '''
    Render the price history popup for ingredient id {id}
    '''
    # Draw the figure on the canvas  
    def pack_figure(graph, figure):
        canvas = FigureCanvasTkAgg(figure, graph.Widget)
        plot_widget = canvas.get_tk_widget()
        plot_widget.pack(side='top', fill='both', expand=1)
        return plot_widget
        
    def plot_price_over_time(data, highlight_index=None):
        '''
        Generate the line chart. Expects a dictionary with values 'date' and 'price'
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
        # Add padding to the bottom to fit the labels
        fig.subplots_adjust(bottom=0.2)

        # Add labels to data points
        for i, price in enumerate(prices):
            if highlight_index is not None and i==highlight_index:
                ax.text(dates[i], price, f"${price:.2f}", ha='center', va='bottom', fontweight='bold')
            else:
                ax.text(dates[i], price, f"${price:.2f}", ha='center', va='bottom')

        fig.canvas.draw()
    
    def plot_ingredients_pieplot(data, date):
        '''Create a pie plot with ingredient breakdown. Expects a dictionary with values 'Name' and 'price'
        '''
        labels = [f"{item['Name']} ${item['price']:.2f}" for item in data]
        values = [item['price'] for item in data]

        # Select the relevant figure
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

    @cache
    def get_ingredients_price_data(id, date):
        '''Call database function to retrieve price breakdown. Wrapping function so that we can cache the result
        '''
        return get_recipe_price_history_details(id, date)
    
    def plot_pieplot(date):
        data = get_ingredients_price_data(id, date)
        plot_ingredients_pieplot(data, date)

    # Retrieve price history data from database
    if recipeMode:
        price_history = get_recipe_price_history(id)
        # Create table layout
        table_data = [[row['date'], "$ {:.2f}".format(row['price'])] for row in price_history]
        table_headings = ['Date', 'Unit Price']
    else:
        price_history = get_price_history(id)
        # Create table layout
        table_data = [[row['date'], "$ {:.4f}".format(row['price']), row['supplier']] for row in price_history]
        table_headings = ['Date', 'Unit Price', 'Supplier']

    element_table = sg.Table(values=table_data, headings=table_headings, num_rows=20, auto_size_columns=False, k='-TABLE-', enable_events = True)
    element_history_graph = sg.Graph((640, 480),(0,0),(640,480),key='-LINE-CHART-', border_width=5)
    element_pie_chart = sg.Graph((640, 480),(0,0),(640,480),key='-PIE-PLOT-', border_width=5)

    layout_table = [[element_table],[sg.VPush()]]

    if recipeMode:
        ingredient_limiting_dates = get_recipe_price_history_dates(id)
        max_date = max(i['earliest_date'] for i in ingredient_limiting_dates)
        callout_string = f"Price data starting from {max_date} \ndue to history available on ingredients.\nTo extend, check the following:"
        limits = [f"{ing['Name']}" for ing in ingredient_limiting_dates if ing['earliest_date'] == max_date]
        limits_elements = [[sg.Text(callout_string)],[sg.Listbox(limits, no_scrollbar=True,size=(30, len(limits)))]]
        layout_table += limits_elements

    layout_graph = [ 
                    [sg.TabGroup([[
                        sg.Tab('History Over Time', [[element_history_graph]]),
                        sg.Tab('Ingredient Breakdown', [[element_pie_chart]], visible=recipeMode)
                    ]])]
    ]

    layout = [
        [sg.Column(layout_table, expand_y=True), sg.Column(layout_graph,)]
    ]

    # Create window
    window = sg.Window(f'Price History [{name}]', layout, finalize=True, icon=ICON)
    if len(price_history)>0:
        graph1 = window['-LINE-CHART-']
        graph2 = window['-PIE-PLOT-']
        plt.ioff()
        fig1 = plt.figure(1)
        ax1 = plt.subplot(111)
        fig2 = plt.figure(2)
        ax2 = plt.subplot(111)
        pack_figure(graph1, fig1)
        pack_figure(graph2,fig2)
        plot_price_over_time(price_history)
        plot_pieplot(price_history[-1]['date'])

    # Event loop
    while True:
        event, values = window.read()
        if event == sg.WINDOW_CLOSED or event == 'Exit':
            break
        if event == '-TABLE-':
            if len(values['-TABLE-']) > 0:
                selected_row = values['-TABLE-'][-1]
            else:
                selected_row = -1
            date_to_query = price_history[selected_row]['date']
            if recipeMode:
                plot_pieplot(date_to_query)
            plot_price_over_time(price_history, selected_row)

    # Close window
    window.close()

if __name__=='__main__':
    render(2)