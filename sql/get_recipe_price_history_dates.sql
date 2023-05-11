
SELECT i.Name, rx.ingredient_id, MIN(ip.effective_date) AS earliest_date
FROM recipe_ingredients_expanded rx
JOIN ingredient_prices AS ip ON ip.ingredient_id = rx.ingredient_id
JOIN Ingredients i on rx.ingredient_id = i.Id
WHERE rx.recipe_id = ?
GROUP BY rx.ingredient_id