import config
import sqlite3
from re import sub

def make_dict(cursor):
    '''
    Return the results from query on cursor as a list of dictionaries, with keys as the column names
    '''
    columns = [description[0] for description in cursor.description]
    records = cursor.fetchall()
    results = []
    for record in records:
        result_dict = dict(zip(columns,record))
        results.append(result_dict)
    return results

# Run a query with optional parameters
def query(sql, params=(), one=False, rawdata=False):
    connection = sqlite3.connect(config.DATABASE)
    cursor = connection.cursor()
    cursor.execute(sql, params)
    # If we have rows to parse, then make them into a dict
    if rawdata:
        data = cursor.fetchall()
    else:
        if cursor.description:
            data = make_dict(cursor) 
        else:
            data = []
    results = {'data': data, 'rowcount': cursor.rowcount, 'lastrowid': cursor.lastrowid}
    connection.commit()
    connection.close()
    return (data[0] if data else None) if one else results

def query_from_file(file, params=(), one=False,rawdata=False,filter=""):
    # with open(config.resource_path(file), 'r') as f:
    #     sql = f.read()
    sql = config.get_resource(file)
    return query(sql.format(filter=filter), params, one=one, rawdata=rawdata)


def get_ingredients(id=0):
    '''
    Returns details of ingredient with id passed, if no parameter is provided returns all ingredients in a list
    '''
    if(id):
        filter = f" WHERE Id={id}"
        sql = "SELECT * FROM Ingredients" + filter
        result = query(sql, one=True)
    else:
        sql = "SELECT * FROM Ingredients ORDER BY Name ASC"
        result = query(sql)['data']
    return(result)

def update_ingredient(id, values):
    '''
    Updates ingredient Id with new values
    '''
    params = (
        values['Name'],
        values['Unit'],
        values['Portion'],
        values['Weight'],
        sub(r'[^\d.]', '', values['Cost']),
        values['Calories'],
        values['TTLFatGrams'],
        values['SatFatGrams'],
        values['CholesterolMilligrams'],
        values['SodiumMilligrams'],
        values['CarbGrams'],
        values['FiberGrams'],
        values['SugarGrams'],
        values['ProteinGrams'],
    )
    result = query_from_file('sql\\update_ingredient_info.sql',params,filter = f'WHERE Id={id}')
    return result

def create_ingredient( values):
    '''
    Updates ingredient Id with new values
    '''
    params = (
        values['Name'],
        values['Unit'],
        values['Portion'],
        values['Weight'],
        sub(r'[^\d.]', '', values['Cost']),
        values['Calories'],
        values['TTLFatGrams'],
        values['SatFatGrams'],
        values['CholesterolMilligrams'],
        values['SodiumMilligrams'],
        values['CarbGrams'],
        values['FiberGrams'],
        values['SugarGrams'],
        values['ProteinGrams'],
    )
    result = query_from_file('sql\\create_ingredient.sql',params)
    return result['lastrowid']

def ingredient_price_latest(id):
    return query('''SELECT * FROM ingredient_prices WHERE ingredient_id=? AND effective_date<=Date('now') ORDER BY effective_date DESC, id DESC;''', (id,), one=True)

def ingredient_price_new(id, values):
    '''
    Add a new row to the ingredient_prices table
    '''
    print('Adding new row to price history: ', values)
    return query(f'INSERT INTO ingredient_prices (ingredient_id, supplier_id, case_price, units_per_case, effective_date) VALUES ({id},?,?,?,?)', values)

def get_suppliers():
    '''
    Get all of the possible suppliers
    '''
    return query('SELECT * FROM suppliers;')['data']
def delete_ingredient(id):
    '''
    Delete the ingredient Id
    Raises Exception if the ingredient is included in any recipes
    '''
    number_of_references = query(f'SELECT COUNT(*) AS Count FROM Connections WHERE ChildIngredient={id};', one=True)['Count']

    if number_of_references==0:
        sql = f'''DELETE FROM Ingredients WHERE Id={id}'''
        return query(sql)
    else:
        used_in = f'''
            SELECT Id, Name FROM
            Connections c JOIN Recipes r
            ON c.ParentRecipe = r.Id 
            WHERE C.ChildIngredient = {id} 
        '''
        # We still need to pass this
        recipelist = query(used_in)['data']
        readable = ', '.join(i['Name'] for i in recipelist)
        raise Exception(f'Unable to delete. Ingredient used in {number_of_references} recipe(s). {readable}')
    
def delete_recipe(id):
    '''
    Delete the Recipe Id
    Raises Exception if the recipe is included as an ingredient in any others
    '''
    number_of_references = query(f'SELECT COUNT(*) AS Count FROM Connections WHERE ChildRecipe={id};', one=True)['Count']

    if number_of_references==0:
        return query(f'DELETE FROM Recipes WHERE Id={id}')
    else:
        used_in = f'''
            SELECT Id, Name FROM
            Connections c JOIN Recipes r
            ON c.ParentRecipe = r.Id 
            WHERE C.ChildRecipe = {id} 
        '''
        # We still need to pass this
        recipelist = query(used_in)['data']
        readable = ', '.join(i['Name'] for i in recipelist)
        raise Exception(f'Unable to delete. Recipe used in {number_of_references} other recipe(s). {readable}')


# Get summmary data for recipes. If no Id is passed, we get all records
def recipe_info(id=0):
    if id:
        result = query_from_file('sql\\get_recipe_info.sql',one=True, filter=f'WHERE r.Id = {id}')
        # Format the currency
        result['Cost'] = "$ {:.2f}".format(result['Cost'])
        return result
    else:
        result = query_from_file('sql\\get_recipe_info.sql')['data']
        for row in result:
            row['Cost'] = "$ {:0.2f}".format(row['Cost'])
        return result

# Fields to use elsewhere
recipe_components_fields = ['Name', 'Quantity', 'Unit', 'Type', 'Cost', 'Id']
# Fetch all components on one recipe
def recipe_components(id: int):
    result = query_from_file('sql\\get_recipe_components.sql', (id,))['data']

    # Format the data
    for row in result:
        # Strip trailing zeroes from quantity
        row['Quantity'] = "{:.2f}".format(row['Quantity']).rstrip('0').rstrip('.')
        # Format cost as "$ 0.00"
        row['Cost'] = "$ {:.2f}".format(row['Cost'])
    return(result)

def update_recipe_info(id: int, name: str, unit: str, outputqty: float):
    return query_from_file('sql\\update_recipe_info.sql', (name, unit, outputqty, id))

def create_recipe(name: str, unit: str, outputqty: float):
    result = query_from_file('sql\\create_recipe.sql', (name, unit, outputqty))
    return result['lastrowid']
    
def get_eligible_ingredients(id: int):
    return query_from_file('sql\\get_eligible_ingredients.sql',(id,), rawdata=True)['data']


# Interact with Recipe Ingredients
def add_recipe_ingredient(parent: int, mode: str, child: int, qty: float):
    sql = '''
        INSERT INTO Connections Values (?, ?, ?, ?);
    '''
    if mode == 'ingredient':
        recipe = None
        ingredient = child
    elif mode == 'recipe':
        recipe = child
        ingredient = None
    else:
        raise ValueError(f"Invalid mode: {mode}")
    return query(sql, (parent, recipe, ingredient, qty))

def update_recipe_ingredient(parent: int, mode: str, child: int, qty: float):
    sql = '''
        UPDATE Connections SET Quantity=?
        WHERE ParentRecipe=? {filter};
    '''
    if mode == 'ingredient':
        filter = 'AND ChildIngredient=?'
    elif mode == 'recipe':
        filter = 'AND ChildRecipe=?'
    else:
        raise ValueError(f"Invalid mode: {mode}")
    params = (qty, parent, child)
    return query(sql.format(filter=filter), params)


def delete_recipe_ingredient(parent: int, mode: str, child: int):
    sql = '''
        DELETE FROM Connections
        WHERE ParentRecipe=? {filter};
    '''
    if mode == 'ingredient':
        filter = 'AND ChildIngredient=?'
    elif mode == 'recipe':
        filter = 'AND ChildRecipe=?'
    else:
        raise ValueError(f"Invalid mode: {mode}")

    params = (parent, child)
    return query(sql.format(filter=filter), params)
