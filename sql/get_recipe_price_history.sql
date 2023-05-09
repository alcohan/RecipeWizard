WITH prices_by_date AS (
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
    
      SELECT *
      FROM (
        -- Define the dates we'll use to query by. Start with all dates that have price changes logged
        SELECT DISTINCT ip.effective_date as date
        FROM ingredient_prices ip
        -- Start the query from the earliest date that has price info for all ingredients
        WHERE ip.effective_date >= (
          -- This will be the max of (min date for each ingredient)
            SELECT MAX(effective_date) FROM (
              SELECT t.id, ip.effective_date
              FROM tree t
              JOIN ingredient_prices ip ON t.ChildIngredient = ip.ingredient_id
              JOIN (
                -- Min date for each ingredient
                  SELECT ingredient_id, MIN(effective_date) AS earliest_date
                  FROM ingredient_prices
                  GROUP BY ingredient_id
              ) subq ON ip.ingredient_id = subq.ingredient_id AND ip.effective_date = subq.earliest_date
          )
        )
      ) AS dates
      
      CROSS JOIN tree t
  )
  SELECT
    ai.date
    , r.Name as name
    , COALESCE(SUM(ip.unit_price * ai.Quantity ) / r.OutputQty, 0) as price
    , COUNT(*) as ComponentsWithData

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
  GROUP BY date

)

SELECT 
  date, 
  name, 
  price
FROM (
  SELECT 
    date, 
    name, 
    price, 
    LAG(price) OVER (
      PARTITION BY name 
      ORDER BY date
    ) AS prev_price
  FROM prices_by_date
) sub
WHERE prev_price IS NULL OR prev_price <> price