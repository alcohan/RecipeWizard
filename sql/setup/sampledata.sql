-- Generic sample data shipped with the repository. Three recipes
-- (Garden Salad, Chicken Wrap, Grain Bowl) built from sixteen common
-- ingredients, each tagged into a canonical ingredient category and a
-- handful with allergen flags + price history.
--
-- Canonical tags are seeded here directly (matching setup._DEFAULT_TAGS)
-- so the mapping inserts below can resolve them by name. setup.migrateDB
-- runs after this file and is idempotent — duplicates are skipped.

INSERT INTO tags (name, kind, color, shape) VALUES
 ('Salad',     'recipe',     '#16a34a', 'ring')
,('Wrap',      'recipe',     '#b45309', 'wrap')
,('Bowl',      'recipe',     '#ea580c', 'bowl')
,('Catering',  'recipe',     '#7c3aed', 'tray')
,('Greens',    'ingredient', '#15803d', 'none')
,('Grains',    'ingredient', '#92400e', 'none')
,('Toppings',  'ingredient', '#dc2626', 'none')
,('Cheese',    'ingredient', '#eab308', 'none')
,('Crunchies', 'ingredient', '#a16207', 'none')
,('Premiums',  'ingredient', '#9333ea', 'none')
,('Protein',   'ingredient', '#be185d', 'none')
,('Dressing',  'ingredient', '#0891b2', 'none')
,('Finish',    'ingredient', '#db2777', 'none')
,('Packaging', 'ingredient', '#475569', 'none')
;

INSERT INTO Ingredients
(Id, Name, Unit, Portion, Weight, Cost, Calories, TTLFatGrams, SatFatGrams, CholesterolMilligrams, SodiumMilligrams, CarbGrams, FiberGrams, SugarGrams, ProteinGrams, ImageFilename)
VALUES
 ( 1, 'Romaine Lettuce',      '3 cups', 'Portion Cup', 146, 0.65,  24, 0.3, 0.0,   0,  12,  4.6, 2.9, 1.6,  1.7, NULL)
,( 2, 'Baby Spinach',          '3 cups', 'Portion Cup',  90, 0.85,  21, 0.4, 0.1,   0,  71,  3.3, 2.0, 0.4,  2.6, NULL)
,( 3, 'Brown Rice',            '8 f.oz', 'scoop',       195, 0.40, 216, 1.8, 0.4,   0,  10, 45.0, 3.5, 0.7,  5.0, NULL)
,( 4, 'Quinoa',                '8 f.oz', 'scoop',       185, 0.95, 222, 3.6, 0.4,   0,  13, 39.0, 5.2, 1.6,  8.1, NULL)
,( 5, 'Cherry Tomato',         '2 f.oz', 'Red',          49, 0.45,   9, 0.1, 0.0,   0,   2,  2.0, 0.6, 1.3,  0.4, NULL)
,( 6, 'Cucumber',              '2 f.oz', 'Red',          50, 0.25,   8, 0.1, 0.0,   0,   1,  1.9, 0.3, 0.9,  0.3, NULL)
,( 7, 'Feta Cheese',           '2 f.oz', 'Red',          28, 0.95,  75, 6.0, 4.2,  25, 316,  1.2, 0.0, 1.2,  4.0, NULL)
,( 8, 'Cheddar Cheese',        '2 f.oz', 'Red',          28, 0.60, 113, 9.3, 5.9,  29, 174,  0.4, 0.0, 0.1,  7.0, NULL)
,( 9, 'Croutons',              '1 f.oz', 'Tongs',        14, 0.20,  60, 2.3, 0.4,   0, 110,  8.0, 0.5, 0.4,  1.6, NULL)
,(10, 'Avocado',               '.5 ea',  'Half',        100, 0.85, 160,14.7, 2.1,   0,   7,  8.5, 6.7, 0.7,  2.0, NULL)
,(11, 'Grilled Chicken',       '3 f.oz', 'White',        85, 1.35, 140, 3.0, 0.9,  73,  63,  0.0, 0.0, 0.0, 26.0, NULL)
,(12, 'Tofu',                  '3 f.oz', 'White',        85, 0.75,  70, 4.0, 0.6,   0,  12,  2.0, 0.5, 0.5,  8.0, NULL)
,(13, 'Hard-Boiled Egg',       '1 ea',   'Each',         50, 0.30,  78, 5.0, 1.6, 187, 124,  0.6, 0.0, 0.6,  6.0, NULL)
,(14, 'Ranch Dressing',        '2 f.oz', 'red',          60, 0.50, 290,30.0, 4.5,  15, 525,  3.0, 0.0, 2.5,  1.0, NULL)
,(15, 'Balsamic Vinaigrette',  '2 f.oz', 'red',          60, 0.40, 130,12.0, 1.8,   0, 360,  6.0, 0.0, 5.0,  0.0, NULL)
,(16, 'Bowl Container',        '1 ea',   'each',         30, 0.18,   0, 0.0, 0.0,   0,   0,  0.0, 0.0, 0.0,  0.0, NULL)
;

INSERT INTO Recipes (Id, Name, Unit, OutputQty) VALUES
 (1, 'Garden Salad',  'each', 1)
,(2, 'Chicken Wrap',  'each', 1)
,(3, 'Grain Bowl',    'each', 1)
;

-- (ParentRecipe, ChildRecipe, ChildIngredient, Quantity)
INSERT INTO Connections (ParentRecipe, ChildRecipe, ChildIngredient, Quantity) VALUES
 -- Garden Salad
  (1, NULL,  1, 1)   -- Romaine
 ,(1, NULL,  2, 1)   -- Spinach
 ,(1, NULL,  5, 1)   -- Cherry Tomato
 ,(1, NULL,  6, 1)   -- Cucumber
 ,(1, NULL,  7, 1)   -- Feta
 ,(1, NULL,  9, 1)   -- Croutons
 ,(1, NULL, 15, 1)   -- Vinaigrette
 ,(1, NULL, 16, 1)   -- Bowl
 -- Chicken Wrap
 ,(2, NULL,  1, 1)   -- Romaine
 ,(2, NULL,  5, 1)   -- Cherry Tomato
 ,(2, NULL,  6, 1)   -- Cucumber
 ,(2, NULL,  8, 1)   -- Cheddar
 ,(2, NULL, 11, 1)   -- Chicken
 ,(2, NULL, 14, 1)   -- Ranch
 ,(2, NULL, 16, 1)   -- Bowl
 -- Grain Bowl
 ,(3, NULL,  2, 1)   -- Spinach
 ,(3, NULL,  3, 1)   -- Brown Rice
 ,(3, NULL,  4, 1)   -- Quinoa
 ,(3, NULL,  5, 1)   -- Cherry Tomato
 ,(3, NULL, 10, 1)   -- Avocado
 ,(3, NULL, 12, 1)   -- Tofu
 ,(3, NULL, 15, 1)   -- Vinaigrette
 ,(3, NULL, 16, 1)   -- Bowl
;

INSERT INTO suppliers (name) VALUES ('Generic Supplier');

INSERT INTO allergens (name, sortOrder) VALUES
 ('Meat',      1)
,('Coconut',   2)
,('Fish',      3)
,('Shellfish', 4)
,('Dairy',     5)
,('Eggs',      6)
,('Gluten',    7)
,('Tree Nuts', 8)
,('Peanuts',   9)
,('Soy',      10)
,('Sesame',   11)
;

-- Allergen mappings — referenced by name so the order of the INSERT above
-- doesn't have to be load-bearing.
INSERT INTO ingredient_allergens (allergen_id, ingredient_id)
SELECT a.id, v.ing FROM allergens a JOIN (
    SELECT 'Meat'   AS al, 11 AS ing UNION ALL    -- Chicken
    SELECT 'Dairy',  7 UNION ALL                  -- Feta
    SELECT 'Dairy',  8 UNION ALL                  -- Cheddar
    SELECT 'Dairy', 14 UNION ALL                  -- Ranch
    SELECT 'Eggs',  13 UNION ALL                  -- HB Egg
    SELECT 'Eggs',  14 UNION ALL                  -- Ranch (mayo base)
    SELECT 'Gluten', 9 UNION ALL                  -- Croutons
    SELECT 'Soy',   12                            -- Tofu
) v ON a.name = v.al;

-- Ingredient category tags (kind='ingredient' — seeded by migrateDB).
INSERT INTO ingredient_tags_mapping (tag_id, ingredient_id)
SELECT t.id, v.ing FROM tags t JOIN (
    SELECT 'Greens'    AS tg,  1 AS ing UNION ALL
    SELECT 'Greens',    2 UNION ALL
    SELECT 'Grains',    3 UNION ALL
    SELECT 'Grains',    4 UNION ALL
    SELECT 'Toppings',  5 UNION ALL
    SELECT 'Toppings',  6 UNION ALL
    SELECT 'Cheese',    7 UNION ALL
    SELECT 'Cheese',    8 UNION ALL
    SELECT 'Crunchies', 9 UNION ALL
    SELECT 'Premiums', 10 UNION ALL
    SELECT 'Protein',  11 UNION ALL
    SELECT 'Protein',  12 UNION ALL
    SELECT 'Protein',  13 UNION ALL
    SELECT 'Dressing', 14 UNION ALL
    SELECT 'Dressing', 15 UNION ALL
    SELECT 'Packaging',16
) v ON t.name = v.tg AND t.kind = 'ingredient';

-- Recipe-format tags (kind='recipe' — seeded by migrateDB).
INSERT INTO recipe_tags_mapping (tag_id, recipe_id)
SELECT t.id, v.rec FROM tags t JOIN (
    SELECT 'Salad' AS tg, 1 AS rec UNION ALL
    SELECT 'Wrap',  2 UNION ALL
    SELECT 'Bowl',  3
) v ON t.name = v.tg AND t.kind = 'recipe';

-- Price history. The update_ingredient_price trigger derives
-- Ingredients.Cost from the latest applicable row.
INSERT INTO ingredient_prices (ingredient_id, units_per_case, case_price, effective_date, notes) VALUES
 ( 1, 30,  19.50, '2025-01-01', 'sample data')
,( 2, 24,  20.40, '2025-01-01', 'sample data')
,( 3, 50,  20.00, '2025-01-01', 'sample data')
,( 4, 40,  38.00, '2025-01-01', 'sample data')
,( 5, 40,  18.00, '2025-01-01', 'sample data')
,( 6, 60,  15.00, '2025-01-01', 'sample data')
,( 7, 20,  19.00, '2025-01-01', 'sample data')
,( 8, 40,  24.00, '2025-01-01', 'sample data')
,( 9, 80,  16.00, '2025-01-01', 'sample data')
,(10, 24,  20.40, '2025-01-01', 'sample data')
,(11, 30,  40.50, '2025-01-01', 'sample data')
,(12, 30,  22.50, '2025-01-01', 'sample data')
,(13, 60,  18.00, '2025-01-01', 'sample data')
,(14, 32,  16.00, '2025-01-01', 'sample data')
,(15, 32,  12.80, '2025-01-01', 'sample data')
,(16,100,  18.00, '2025-01-01', 'sample data')
;
