WITH all_ingredients AS (
  
  WITH tree AS (
    SELECT ParentRecipe as Id, ParentRecipe, ChildRecipe, ChildIngredient, Quantity, 1 AS level
    FROM connections
    -- SET THE RECIPE HERE
    WHERE ParentRecipe=?
    
    UNION ALL
    
    SELECT t.Id, c.ParentRecipe, c.ChildRecipe, c.ChildIngredient, c.Quantity*t.Quantity/r.OutputQty, t.level + 1
    FROM connections c
    INNER JOIN tree t ON c.ParentRecipe = t.ChildRecipe
    INNER JOIN Recipes r on t.ChildRecipe = r.Id
    WHERE t.ChildRecipe IS NOT NULL
  
  )
  SELECT tree.*, ? as date
  FROM tree
)
SELECT
ai.ChildIngredient
, i.Name
, COALESCE((ip.unit_price * ai.Quantity ) / r.OutputQty, 0) as price

FROM 
all_ingredients ai 
JOIN ingredient_prices ip ON (
  ai.ChildIngredient = ip.ingredient_id 
  AND ip.effective_date = (
    SELECT MAX(effective_date) 
    FROM ingredient_prices 
    WHERE 
      ingredient_id = ai.ChildIngredient 
      AND effective_date <= ai.date
  )
)

JOIN recipes r on r.id = ai.id
JOIN ingredients i on ai.ChildIngredient = i.Id

