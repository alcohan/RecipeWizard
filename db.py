import sqlite3

def query(sql):
    connection = sqlite3.connect("builder.db")
    cursor = connection.cursor()
    cursor.execute(sql)
    columns = [description[0] for description in cursor.description]
    records = cursor.fetchall()
    results = []
    for record in records:
        result_dict = dict(zip(columns,record))
        results.append(result_dict)
    connection.commit()
    connection.close()

    return results

# returns details of ingredient with id passed, if no parameter is provided returns all ingredients in a list
def get_ingredients(id=0):
    if(id):
        filter = f" WHERE Id={id}"
    else:
        filter = ""
    sql = "SELECT * FROM Ingredients" + filter
    result = query(sql)
    return(result)

def recipes_overview():
    sql = """
        SELECT r.Id
            , r.Name
            , r.Unit
            , OutputQty
            , r.Weight
            , Cost
            , r.Calories
            , Count(c.ParentRecipe) As Components 
        FROM RecipeDetails r 
        LEFT JOIN Connections c ON r.Id = C.ParentRecipe
        GROUP BY r.Id
        ;
    """
    return(query(sql))

def recipe_detailedinfo(id: int):
    sql = f'''
        SELECT r.*
            , Count(c.ParentRecipe) As Components 
        FROM RecipeDetails r
        LEFT JOIN Connections c ON r.Id = C.ParentRecipe
        WHERE r.Id={id}
        GROUP BY r.Id
        ;
    '''
    return(query(sql))

# def recipe_components(id: int):
#     connection = sqlite3.connect("builder.db")
#     cursor = connection.cursor()
#     cursor.execute(f'''
#         SELECT COALESCE(r.Name, i.Name) AS Name 
#         , c.Quantity
#         , COALESCE(i.Unit, r.Unit) AS Unit
#         ,  CASE 
#             WHEN c.ChildRecipe IS NOT NULL THEN 'recipe'
#             ELSE 'ingredient'
#             END AS Type
#         , ROUND(COALESCE(r.Cost, i.Cost) * c.Quantity,2) AS Cost
#         , COALESCE(r.Id, i.Id) AS Id
#         FROM Connections c
#         LEFT JOIN RecipesWithNutrition r on r.Id=c.ChildRecipe
#         LEFT JOIN Ingredients i on i.Id=c.ChildIngredient
#         WHERE c.ParentRecipe={id}
#         ;
#     ''')
#     records = cursor.fetchall()
#     connection.commit()
#     connection.close()
#     return(records)

recipe_components_fields = ['Name', 'Quantity', 'Unit', 'Type', 'Cost', 'Id']

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
    result = query(sql)
    for row in result:
        row['Quantity'] = "{:.2f}".format(row['Quantity']).rstrip('0').rstrip('.')
        row['Cost'] = "$ {:.2f}".format(row['Cost'])
    return(result)

def update_recipe_info(id: int, name: str, unit: str, outputqty: float):
    # create a connection to the database
    with sqlite3.connect('builder.db') as conn:
        # create a cursor object to execute SQL statements
        cursor = conn.cursor()
        # read the SQL statement from the file
        with open('sql/update_recipe_info.sql', 'r') as f:
            query = f.read()
        # use parameter binding to update the recipe record
        cursor.execute(query, (name, unit, outputqty, id))
        # commit the changes to the database
        conn.commit()
        # return the number of affected rows
        return cursor.rowcount

def create_recipe(name: str, unit: str, outputqty: float):
    with sqlite3.connect('builder.db') as conn:
        cursor = conn.cursor()
        with open('sql/create_recipe.sql', 'r') as f:
            query = f.read()
        cursor.execute(query, (name, unit, outputqty))
        new_id = cursor.lastrowid
        conn.commit()
        return new_id
    
def get_eligible_ingredients(id: int):
    with sqlite3.connect('builder.db') as conn:
        cursor = conn.cursor()
        with open('sql/get_eligible_ingredients.sql', 'r') as f:
            query = f.read()
        cursor.execute(query.format(id=id))
        records = cursor.fetchall()
        conn.commit()
        return records

def add_ingredient(parent: int, mode: str, child: int, qty: float):
    QUERY = '''
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

    connection = sqlite3.connect("builder.db")
    cursor = connection.cursor()
    cursor.execute(QUERY, (parent, recipe, ingredient, qty))
    connection.commit()
    connection.close()

def update_ingredient(parent: int, mode: str, child: int, qty: float):
    QUERY = '''
        UPDATE Connections SET Quantity=?
        WHERE ParentRecipe=? {filter};
    '''
    if mode == 'ingredient':
        filter = 'AND ChildIngredient=?'
        params = (qty, parent, child)
    elif mode == 'recipe':
        filter = 'AND ChildRecipe=?'
        params = (qty, parent, child)
    else:
        raise ValueError(f"Invalid mode: {mode}")

    connection = sqlite3.connect("builder.db")
    cursor = connection.cursor()
    cursor.execute(QUERY.format(filter=filter), params)
    connection.commit()
    connection.close()

def delete_ingredient(parent: int, mode: str, child: int):
    QUERY = '''
        DELETE FROM Connections
        WHERE ParentRecipe=? {filter};
    '''
    if mode == 'ingredient':
        filter = 'AND ChildIngredient=?'
        params = (parent, child)
    elif mode == 'recipe':
        filter = 'AND ChildRecipe=?'
        params = (parent, child)
    else:
        raise ValueError(f"Invalid mode: {mode}")

    connection = sqlite3.connect("builder.db")
    cursor = connection.cursor()
    cursor.execute(QUERY.format(filter=filter), params)
    connection.commit()
    connection.close()