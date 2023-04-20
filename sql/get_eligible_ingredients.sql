-- Get all eligible recipes (avoiding circular references)
WITH tree AS (
    SELECT {id} AS ParentRecipe
    
    UNION ALL
    
    SELECT c.ParentRecipe
    FROM connections c
    INNER JOIN tree ON c.ChildRecipe = tree.ParentRecipe
)
SELECT Id, 'recipe' AS Type, Name, Unit
FROM Recipes
WHERE Id NOT IN (
    SELECT ParentRecipe FROM tree
)

UNION
SELECT Id, 'ingredient' AS Type, Name, Unit
FROM Ingredients
ORDER BY Name;