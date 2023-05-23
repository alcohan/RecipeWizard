import sqlite3
import csv

def export_tables_to_file(database_file):
    # Connect to the SQLite database
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()

    # Get a list of all table names in the database
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    table_names = [result[0] for result in cursor.fetchall()]

    # Export each table to a separate CSV file
    for table_name in table_names:

        # Retrieve table schema
        cursor.execute(f"PRAGMA table_info({table_name});")
        schema = cursor.fetchall()

        # get column names
        columns = [column[1] for column in schema] 

        # Retrieve all rows from the table
        cursor.execute(f"SELECT {', '.join(columns)} FROM {table_name};")
        rows = cursor.fetchall()

        # Write the table data to a CSV file
        with open(f"export/{table_name}.csv", "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(columns)  # Write column names
            writer.writerows(rows)  # Write row data

    # Close the database connection
    conn.close()


if __name__ == '__main__':
    export_tables_to_file("builder.db")
