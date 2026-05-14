DROP VIEW IF EXISTS RecipeAllergens;
DROP VIEW IF EXISTS recipe_ingredients_expanded;
DROP TABLE IF EXISTS tag_components;
DROP TABLE IF EXISTS tag_category_multipliers;
DROP TABLE IF EXISTS tags;
DROP TABLE IF EXISTS ingredient_tags_mapping;
DROP TABLE IF EXISTS recipe_tags_mapping;
DROP TABLE IF EXISTS allergens;
DROP TABLE IF EXISTS ingredient_allergens;

DROP TABLE IF EXISTS ingredient_prices;

DROP TABLE IF EXISTS Connections;
DROP TABLE IF EXISTS Recipes;
DROP TABLE IF EXISTS Ingredients;
DROP TABLE IF EXISTS suppliers;

-- Define the Tables
CREATE TABLE Ingredients (
	Id INTEGER PRIMARY KEY AUTOINCREMENT
	, Name NVarchar(100)
	, Unit NVarchar(20)
	, Portion NVarchar(20)
	, Weight NUMERIC (6,2)
	, Cost NUMERIC (6,4)
	, Calories NUMERIC (6,2)
	, TTLFatGrams NUMERIC (6,2)
	, SatFatGrams NUMERIC (6,2)
	, CholesterolMilligrams NUMERIC (6,2)
	, SodiumMilligrams NUMERIC (6,2)
	, CarbGrams NUMERIC (6,2)
	, FiberGrams NUMERIC (6,2)
	, SugarGrams NUMERIC (6,2)
	, ProteinGrams NUMERIC (6,2)
	, ImageFilename TEXT
);

CREATE TABLE Recipes (
	Id INTEGER PRIMARY KEY AUTOINCREMENT
	, Name NVarchar(100)
	, Unit NVarchar(30)
	, OutputQty float
);

CREATE TABLE Connections (
	ParentRecipe Integer
	, ChildRecipe Integer
	, ChildIngredient Integer
	, Quantity float
	, SortOrder Integer
	-- Provenance: which template tag added this row (NULL = manual). Used so
	-- switching a recipe's format can remove the previous template's items
	-- cleanly without touching anything the user added themselves.
	, from_template_tag_id Integer
);


CREATE TABLE suppliers (
  id INTEGER PRIMARY KEY AUTOINCREMENT
  , name TEXT
  , address TEXT
  , city TEXT
  , state TEXT
  , zip TEXT
);


CREATE TABLE ingredient_prices (
  id INTEGER PRIMARY KEY AUTOINCREMENT
  , ingredient_id INTEGER
  , supplier_id INTEGER
  , case_price NUMERIC
  , units_per_case NUMERIC
  , unit_price NUMERIC GENERATED ALWAYS AS (1.0*case_price / units_per_case) STORED
  , effective_date DATE NOT NULL
  , notes TEXT
  , end_date DATE
  , is_auto_generated BOOL DEFAULT False
  , FOREIGN KEY (ingredient_id) REFERENCES ingredients(id)
  , FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
);

CREATE TABLE tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT
  , name TEXT
  , kind TEXT NOT NULL DEFAULT 'ingredient' -- 'ingredient' | 'recipe'
  , color TEXT  -- hex like '#16a34a'; null falls back to a neutral default
  , shape TEXT NOT NULL DEFAULT 'none'  -- recipe-kind only: 'none'|'ring'|'bowl'|'wrap'|'tray'
  , sortOrder INTEGER
);

CREATE TABLE ingredient_tags_mapping (
  id INTEGER PRIMARY KEY AUTOINCREMENT
  , tag_id INTEGER
  , ingredient_id INTEGER
  , FOREIGN KEY (ingredient_id) REFERENCES ingredients(id)
  , FOREIGN KEY (tag_id) REFERENCES tags(id)
);

CREATE TABLE recipe_tags_mapping (
  id INTEGER PRIMARY KEY AUTOINCREMENT
  , tag_id INTEGER
  , recipe_id INTEGER
  , FOREIGN KEY (recipe_id) REFERENCES recipes(id)
  , FOREIGN KEY (tag_id) REFERENCES tags(id)
);

-- Items a recipe-format template auto-adds when applied. Shape mirrors
-- Connections (one of child_recipe / child_ingredient is set) so the same
-- "add component" UX can be reused.
CREATE TABLE tag_components (
  id INTEGER PRIMARY KEY AUTOINCREMENT
  , tag_id INTEGER NOT NULL  -- must reference a kind='recipe' tag
  , child_recipe INTEGER
  , child_ingredient INTEGER
  , quantity FLOAT NOT NULL DEFAULT 1
  , FOREIGN KEY (tag_id) REFERENCES tags(id)
);

-- Per-template portion overrides keyed by ingredient-category tag. E.g.
-- (Wrap, Base, 0.3) means "when Wrap is applied, multiply every Base
-- ingredient's quantity by 0.3 in the target recipe." Reversed on
-- template switch.
CREATE TABLE tag_category_multipliers (
  id INTEGER PRIMARY KEY AUTOINCREMENT
  , tag_id INTEGER NOT NULL              -- must reference a kind='recipe' tag
  , category_tag_id INTEGER NOT NULL     -- must reference a kind='ingredient' tag
  , multiplier FLOAT NOT NULL DEFAULT 1
  , UNIQUE (tag_id, category_tag_id)
  , FOREIGN KEY (tag_id) REFERENCES tags(id)
  , FOREIGN KEY (category_tag_id) REFERENCES tags(id)
);

CREATE TABLE allergens (
  id INTEGER PRIMARY KEY AUTOINCREMENT
  , name TEXT
  , sortOrder INTEGER
);

CREATE TABLE ingredient_allergens (
  id INTEGER PRIMARY KEY AUTOINCREMENT
  , allergen_id INTEGER
  , ingredient_id INTEGER
  , FOREIGN KEY (ingredient_id) REFERENCES ingredients(id)
  , FOREIGN KEY (allergen_id) REFERENCES allergens(id)
);

-- When we add a new price history, check if we need to update the current ingredient price
CREATE TRIGGER update_ingredient_price AFTER INSERT ON ingredient_prices
BEGIN
  UPDATE ingredients
  SET Cost = (
    SELECT unit_price
    FROM ingredient_prices
    WHERE ingredient_id = NEW.ingredient_id AND effective_date<=Date('now')
    ORDER BY 
      effective_date DESC,
      id DESC
    LIMIT 1
  )
  WHERE id = NEW.ingredient_id;
END;

-- Create a basic entry to ingredient_prices for new ingredients
-- CREATE TRIGGER insert_ingredient_price
-- AFTER INSERT ON ingredients
-- FOR EACH ROW
-- BEGIN
--   INSERT INTO ingredient_prices (ingredient_id, case_price, units_per_case, effective_date)
--   VALUES (NEW.id, NEW.cost, 1, date('now'));
-- END;
