WITH all_ingredients AS (
  
  WITH tree AS (
    SELECT * from recipe_ingredients_expanded
    WHERE recipe_id = ?
  )

  SELECT tree.*, ? as date
  FROM tree
)
SELECT
ai.ingredient_id
, i.Name
, COALESCE((ip.unit_price * ai.Quantity ) / r.OutputQty, 0) as price

FROM 
all_ingredients ai 
JOIN ingredient_prices ip ON (
  ai.ingredient_id = ip.ingredient_id 
  AND ip.effective_date = (
    SELECT MAX(effective_date) 
    FROM ingredient_prices 
    WHERE 
      ingredient_id = ai.ingredient_id 
      AND effective_date <= ai.date
  )
)

JOIN recipes r on r.id = ai.recipe_id
JOIN ingredients i on ai.ingredient_id = i.Id

