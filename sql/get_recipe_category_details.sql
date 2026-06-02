-- Flattened per-(recipe, ingredient) breakdown across ALL recipes.
--
-- Python pivots this into the analytics spreadsheet:
--   recipe (row) x category (col) = sum(metric)
-- The per-ingredient rows are also kept around to power per-cell
-- tooltips ("Greens — Romaine $0.50, Spinach $1.00").
--
-- Sub-recipes flatten to their leaf ingredients via
-- recipe_ingredients_expanded, so a salad dressing's olive oil counts
-- as Oil/Dressing/etc., not as a single "Dressing" bucket.
--
-- LIMIT 1 on the category subquery matches the app convention used
-- elsewhere (get_ingredients, recents strip, gallery card): one
-- ingredient -> one displayed category, even if the schema allows more.
WITH ingredient_categories AS (
    SELECT i.Id, i.Name,
           i.Cost, i.Weight, i.Calories, i.TTLFatGrams, i.SatFatGrams,
           i.CholesterolMilligrams, i.SodiumMilligrams, i.CarbGrams,
           i.FiberGrams, i.SugarGrams, i.ProteinGrams,
           (SELECT t.name FROM tags t
              JOIN ingredient_tags_mapping itm ON itm.tag_id = t.id
              WHERE itm.ingredient_id = i.Id AND t.kind = 'ingredient'
              LIMIT 1) AS tag_name,
           (SELECT t.color FROM tags t
              JOIN ingredient_tags_mapping itm ON itm.tag_id = t.id
              WHERE itm.ingredient_id = i.Id AND t.kind = 'ingredient'
              LIMIT 1) AS tag_color
    FROM Ingredients i
)
SELECT
    r.Id   AS recipe_id,
    r.Name AS recipe_name,
    r.Unit AS recipe_unit,
    ic.Id  AS ingredient_id,
    ic.Name AS ingredient_name,
    COALESCE(ic.tag_name, '(uncategorized)') AS category,
    COALESCE(ic.tag_color, '#888888')        AS color,
    ic.Cost                  * rx.Quantity / r.OutputQty AS cost,
    ic.Weight                * rx.Quantity / r.OutputQty AS weight,
    ic.Calories              * rx.Quantity / r.OutputQty AS calories,
    ic.TTLFatGrams           * rx.Quantity / r.OutputQty AS fat,
    ic.SatFatGrams           * rx.Quantity / r.OutputQty AS sat_fat,
    ic.CholesterolMilligrams * rx.Quantity / r.OutputQty AS cholesterol,
    ic.SodiumMilligrams      * rx.Quantity / r.OutputQty AS sodium,
    ic.CarbGrams             * rx.Quantity / r.OutputQty AS carbs,
    ic.FiberGrams            * rx.Quantity / r.OutputQty AS fiber,
    ic.SugarGrams            * rx.Quantity / r.OutputQty AS sugar,
    ic.ProteinGrams          * rx.Quantity / r.OutputQty AS protein
FROM recipe_ingredients_expanded rx
JOIN ingredient_categories ic ON rx.ingredient_id = ic.Id
JOIN Recipes r                ON rx.recipe_id     = r.Id
ORDER BY r.Name COLLATE NOCASE, category, ic.Name COLLATE NOCASE;
