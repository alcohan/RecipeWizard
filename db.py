import sqlite3

# Utility - Return the results as a dictionary
def make_dict(cursor):
    columns = [description[0] for description in cursor.description]
    records = cursor.fetchall()
    results = []
    for record in records:
        result_dict = dict(zip(columns,record))
        results.append(result_dict)
    return results

# Run a query with optional parameters
def query(sql, params=(), one=False, rawdata=False):
    connection = sqlite3.connect("builder.db")
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
    with open(file, 'r') as f:
        sql = f.read()
    return query(sql.format(filter=filter), params, one=one, rawdata=rawdata)


# returns details of ingredient with id passed, if no parameter is provided returns all ingredients in a list
def get_ingredients(id=0):
    if(id):
        filter = f" WHERE Id={id}"
    else:
        filter = ""
    sql = "SELECT * FROM Ingredients" + filter
    result = query(sql)['data']
    return(result)

# Get summmary data for recipes. If no Id is passed, we get all records
def recipe_info(id=0):
    if id:
        result = query_from_file('sql/get_recipe_info.sql',one=True, filter=f'WHERE r.Id = {id}')
        # Format the currency
        result['Cost'] = "$ {:.2f}".format(result['Cost'])
        return result
    else:
        result = query_from_file('sql/get_recipe_info.sql')['data']
        for row in result:
            row['Cost'] = "$ {:0.2f}".format(row['Cost'])
        return result

# Fields to use elsewhere
recipe_components_fields = ['Name', 'Quantity', 'Unit', 'Type', 'Cost', 'Id']
# Fetch all components on one recipe
def recipe_components(id: int):
    sql = f'''
        SELECT COALESCE(r.Name, i.Name) AS Name 
        , c.Quantity
        , COALESCE(i.Unit, r.Unit) AS Unit
        ,  CASE 
            WHEN c.ChildRecipe IS NOT NULL THEN 'recipe'
            ELSE 'ingredient'
            END AS Type
        , ROUND(COALESCE(r.Cost, i.Cost) * c.Quantity,2) AS Cost
        , COALESCE(r.Id, i.Id) AS Id
        FROM Connections c
        LEFT JOIN RecipesWithNutrition r on r.Id=c.ChildRecipe
        LEFT JOIN Ingredients i on i.Id=c.ChildIngredient
        WHERE c.ParentRecipe={id}
        ;
    '''
    result = query(sql)['data']
    for row in result:
        row['Quantity'] = "{:.2f}".format(row['Quantity']).rstrip('0').rstrip('.')
        row['Cost'] = "$ {:.2f}".format(row['Cost'])
    return(result)

def update_recipe_info(id: int, name: str, unit: str, outputqty: float):
    return query_from_file('sql/update_recipe_info.sql', (name, unit, outputqty, id))

def create_recipe(name: str, unit: str, outputqty: float):
    result = query_from_file('sql/create_recipe.sql', (name, unit, outputqty))
    return result['lastrowid']
    
def get_eligible_ingredients(id: int):
    return query_from_file('sql/get_eligible_ingredients.sql',(id,), rawdata=True)['data']

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
