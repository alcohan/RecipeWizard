import sqlite3
import csv

tables = [
    'Ingredients',
    'Recipes',
    'Connections',
    'suppliers',
    'ingredient_prices',
    'tags',
    'ingredient_tags_mapping',
    'recipe_tags_mapping',
    ]

def import_data_to_tables(database_file, tables=tables):
    # Connect to the SQLite database
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()

    # Iterate over the CSV files
    for table_name in tables:
        # Extract the table name from the CSV file name
        file_name = f'export/{table_name}.csv'

        # Read the CSV file and retrieve data
        with open(file_name, "r", newline="") as file:
            reader = csv.reader(file)
            data = list(reader)

        print('importing', file_name)
        # Insert data into the table
        insert_query = f"INSERT INTO {table_name} VALUES ({', '.join(['?'] * len(data[0]))});"
        cursor.executemany(insert_query, data[1:])

    # Commit the changes and close the database connection
    conn.commit()
    conn.close()

if __name__ == '__main__':
    import_data_to_tables('builder.db', tables)