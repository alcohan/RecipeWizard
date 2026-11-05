DROP VIEW IF EXISTS RecipeAllergens;
DROP VIEW IF EXISTS recipe_ingredients_expanded;
DROP TABLE IF EXISTS tag_components;
DROP TABLE IF EXISTS tag_category_multipliers;  -- retired: replaced by tag_portion_rules
DROP TABLE IF EXISTS tag_portion_rules;
DROP TABLE IF EXISTS tags;
DROP TABLE IF EXISTS ingredient_tags_mapping;
DROP TABLE IF EXISTS recipe_tags_mapping;
DROP TABLE IF EXISTS saved_views;
DROP TABLE IF EXISTS saved_comparisons;
DROP TABLE IF EXISTS diets;
DROP TABLE IF EXISTS diet_allergens;
DROP TABLE IF EXISTS app_meta;  -- one-time seed markers: a reset library seeds afresh
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
	, updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE Recipes (
	Id INTEGER PRIMARY KEY AUTOINCREMENT
	, Name NVarchar(100)
	, Unit NVarchar(30)
	, OutputQty float
	, menu_price NUMERIC            -- NULL = not on menu / price unknown; drives food-cost %
	, cost_snapshot NUMERIC         -- Last cost the user saw. Set on editor close.
	, cost_snapshot_at TEXT         -- When that snapshot was taken (sqlite datetime).
	, updated_at TEXT NOT NULL DEFAULT (datetime('now'))
	, status TEXT NOT NULL DEFAULT 'active'  -- 'active' (on the menu) or 'archived'
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
	-- Portion rules (utilities/portions.py): NULL = pinned, Quantity is
	-- typed by hand. Set = the row follows its format's rule for the
	-- ingredient's category; for a base rule it's this row's share of
	-- the category's total, and Quantity is derived from it.
	, portion_share float
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

-- Named Library filter states (JSON from the filter pane).
CREATE TABLE saved_views (
  id INTEGER PRIMARY KEY AUTOINCREMENT
  , name TEXT NOT NULL
  , state TEXT NOT NULL
  , sortOrder INTEGER
);

-- Named Analytics comparisons: recipe ids and chart settings (JSON).
CREATE TABLE saved_comparisons (
  id INTEGER PRIMARY KEY AUTOINCREMENT
  , name TEXT NOT NULL
  , recipe_ids TEXT NOT NULL
  , settings TEXT NOT NULL
  , sortOrder INTEGER
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

-- How a format sizes each ingredient category (utilities/portions.py).
-- mode 'base': the category's ingredients share `amount` by portion_share
-- (Salad greens: 3 cup). mode 'fixed': each ingredient gets `amount`
-- (rice on a Salad: 3 f.oz). Amounts are volumes; `measure` is one of
-- portions.RULE_MEASURES. A category with no rule is sized by hand.
CREATE TABLE tag_portion_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT
  , tag_id INTEGER NOT NULL              -- kind='recipe' tag (the format)
  , category_tag_id INTEGER NOT NULL     -- kind='ingredient' tag
  , mode TEXT NOT NULL                   -- 'base' | 'fixed'
  , amount REAL NOT NULL
  , measure TEXT NOT NULL
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

-- Bump updated_at on every UPDATE so the home tab can list "recently
-- edited" items. The WHEN guard breaks the recursion: when our own
-- UPDATE fires the trigger again, NEW.updated_at != OLD.updated_at, so
-- the guard fails and the trigger is a no-op.
CREATE TRIGGER ingredients_bump_updated_at AFTER UPDATE ON Ingredients
WHEN NEW.updated_at = OLD.updated_at
BEGIN
  UPDATE Ingredients SET updated_at = datetime('now') WHERE Id = NEW.Id;
END;

-- Snapshot-only writes (updating cost_snapshot / cost_snapshot_at after
-- an editor close) shouldn't count as "the user edited this recipe", so
-- we skip the bump when the only columns that moved are the snapshot ones.
CREATE TRIGGER recipes_bump_updated_at AFTER UPDATE ON Recipes
WHEN NEW.updated_at = OLD.updated_at
  AND NOT (NEW.cost_snapshot IS NOT OLD.cost_snapshot
           OR NEW.cost_snapshot_at IS NOT OLD.cost_snapshot_at)
BEGIN
  UPDATE Recipes SET updated_at = datetime('now') WHERE Id = NEW.Id;
END;

-- A recipe's "last edited" should also bump when its components change,
-- not just its demographic fields. Adding/removing/reordering an
-- ingredient or sub-recipe counts as editing the recipe.
CREATE TRIGGER connections_bump_recipe_after_insert AFTER INSERT ON Connections
BEGIN
  UPDATE Recipes SET updated_at = datetime('now') WHERE Id = NEW.ParentRecipe;
END;

CREATE TRIGGER connections_bump_recipe_after_update AFTER UPDATE ON Connections
BEGIN
  UPDATE Recipes SET updated_at = datetime('now') WHERE Id = NEW.ParentRecipe;
END;

CREATE TRIGGER connections_bump_recipe_after_delete AFTER DELETE ON Connections
BEGIN
  UPDATE Recipes SET updated_at = datetime('now') WHERE Id = OLD.ParentRecipe;
END;

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
