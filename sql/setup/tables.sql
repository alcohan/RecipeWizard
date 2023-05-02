DROP TABLE IF EXISTS tags;
DROP TABLE IF EXISTS ingredient_tags_mapping;
DROP TABLE IF EXISTS recipe_tags_mapping;

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
  , end_date DATE
  , is_auto_generated BOOL DEFAULT False
  , FOREIGN KEY (ingredient_id) REFERENCES ingredients(id)
  , FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
);

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

CREATE TABLE tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT
  , name TEXT
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

-- CREATE TRIGGER update_ingredient_price_before_update
-- AFTER UPDATE ON ingredients
-- FOR EACH ROW
-- WHEN NEW.Cost <> OLD.Cost
-- BEGIN
--   INSERT INTO ingredient_prices (ingredient_id, case_price, units_per_case, supplier_id, effective_date, is_auto_generated)
--   VALUES (OLD.id, NEW.Cost, 1, NULL, datetime('now'), True);
-- END;
