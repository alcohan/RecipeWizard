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
WHERE c.ParentRecipe = ?