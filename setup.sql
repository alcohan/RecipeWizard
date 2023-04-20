DROP TABLE IF EXISTS Connections;
DROP TABLE IF EXISTS Ingredients;
DROP TABLE IF EXISTS Recipes;

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

-- Test Data
INSERT INTO Ingredients Values
(9,'Arugula','3 cups','Portion Cup',66.75,0.495846640969163,18,0.6,0.5,0,18,2.4,1.2,1.2,1.8)
,(10,'Kale','3 cups','Portion Cup',62.25,0.381452643171806,99,1.8,0.3,0,75,18,7.2,4.5,8.6)
,(11,'Mixed Greens','3 cups','Portion Cup',66,0.379063876651982,30,0,0,0,142.5,6,1.5,1.5,1.5)
,(12,'Romaine','3 cups','Portion Cup',141,0.814678169358786,18,0.3,0,0,8.6,3.6,2.3,1.3,1.3)
,(13,'Spinach','3 cups','Portion Cup',84.75,0.627224669603524,21,0.4,0.1,0,71.1,3.3,2,0.4,2.6)
,(15,'Wheat Wrap XTRM','1 ea','each',100,0.51625,110,3,0,0,620,33,25,0,12)
,(17,'Quinoa','12 f.oz','4x white',252,0.874251277533039,408,12,0,0,504,72,12,0,12)
,(18,'Brown Rice (bowl)','12 f.oz','4x white',258,0.041863436123348,372,0,0,0,480,84,12,0,12)
,(21,'Black Beans','2 f.oz','Red',52,0.155729084947599,45,0.3,0,0,230,9.5,3,0.3,3.5)
,(22,'Roasted Broccoli - PREP','3 f.oz','White',45,0.452109375,60,6,0.8,0,45,3,1,1,1)
,(23,'Roasted Brussels Sprouts - PREP','3 f.oz','White',43,0.401585903083701,45,2,0.3,0,55,6,2,1,2)
,(24,'Carrot, shredded','2 f.oz','Tongs',18,0.0430770925110132,10,0,0,0,15,2,1,1,0)
,(25,'Celery','1 f.oz','Tongs',14,0.14863436123348,0,0,0,0,10,0,0,0,0)
,(26,'Edamame','2 f.oz','Red',40,0.282819383259912,45,1.5,0.3,0,3,5,2,1,4)
,(27,'Cucumber','2 f.oz','Red',49,0.391509026518096,4,0,0,0,0.5,1,0.2,0.5,0)
,(28,'Fire Roasted Corn','2 f.oz','Red',50,0.257378854625551,41,0.7,0,0,0,7.1,1.9,2.6,1.1)
,(29,'Roasted Sweet Potato','2 f.oz','Red',38,0.306565970679698,45,1.5,0.2,0,20,8,1,2,1)
,(30,'Grape Tomatoes','2 f.oz','Red',49,0.178893171806167,8,0.1,0,0,2.3,1.8,0.6,1.2,0.4)
,(31,'Daikon Kimchi','2 f.oz','Red',35,0.154716694516178,1,0.1,0,0,40,2,1,1,0)
,(32,'Green Onion','1 f.oz','Yellow',9,0.074278022515908,0,0,0,0,0,0,0,0,0)
,(33,'Jalapenos','1 f.oz','Yellow',22,0.0859324522760646,6,0.1,0,0,0.2,1.3,0.6,0.7,0.3)
,(34,'pepperoncini','2 f.oz','Tongs',28,0.228287037037037,5,0,0,0,620,0,1,0,1)
,(35,'Zucchini, grated','2 f.oz','Red',25,0.075715859030837,5,0.1,0,0,0,1,0.3,0,0.3)
,(36,'Pickled Ginger','1 f.oz','Tongs',14,0.0706167400881057,0,0,0,0,150,0.6,0,0,0)
,(37,'Capers','.5 f.oz','Yellow',10,0.104343286017295,10,0,0,0,230,1,1,0,0)
,(38,'Pickled Onion - PREP','1 w.oz','Tongs',20,0.149559471365639,24,0,0,0,82.2,4.3,0.7,1.9,0.5)
,(40,'Red Bell Peppers','2 w.oz','Red',46,0.239003146633103,12,0.1,0,0,1.5,2.2,0.8,1.6,0.4)
,(42,'Golden Raisins','1 f.oz','Yellow',19,0.115171806167401,65,0,0,0,5,16,1,14,1)
,(43,'Apple','2 f.oz','Red',30,0.0732608296622614,29,0.1,0,0,0.5,7.3,1.4,5.8,0.1)
,(44,'Grapes','2 f.oz','Red',42,0.187943426849061,25,0,0,0,0,6,0,5,0)
,(46,'Aged White Cheddar','2 f.oz','Red',29,0.365374449339207,120,10,6,30,200,1,0,0,6)
,(47,'Feta','2 f.oz','Red',32,0.253568281938326,137,10.6,6.8,38,425.2,1.5,0,0,9.1)
,(48,'Gorgonzola','2 f.oz','Red',38,0.341079295154185,152,12.1,9.1,38,577.1,1.5,0,0,9.1)
,(49,'Parmesan','2 f.oz','Tongs',15,0.1559140969163,83,5.5,3.5,14.4,339.2,0.7,0,0.2,7.6)
,(52,'Candied Walnuts - PREP','2 f.oz','Red',33,0.253920704845815,180,11,1.1,0,1,19,2,16,3)
,(53,'Garlic Croutons','3 f.oz','White',19,0.259052863436123,33,1.3,0.3,0,97.3,4.3,0,0,1)
,(54,'Sunflower Seeds','1 f.oz','Yellow',18,0.126118942731278,100,8.7,1.2,0,69.2,3.9,1.8,0.5,3.4)
,(55,'Tortilla Chips','3 f.oz','White',23,0.125047723935389,140,9,1.5,0,129.9,15,1,0,2)
,(56,'Cashews','1 f.oz','Yellow',20,0.219612334801762,120,9.9,1.8,0,0,6.3,0.7,1.4,3.5)
,(57,'Crispy Onions','1 f.oz','Yellow',13,0.15278022515908,71,5.25,0,0,20,4.5,0,0,0)
,(59,'Avocado +$2','.5 ea','Half',61,0.359416666666667,117,9.9,1.9,0,2,7.6,5.5,2.4,2.2)
,(60,'Bacon','1 f.oz','Yellow',15,0.241321585903084,64.5,4.5,1.5,18,284,0,0,0,5.4)
,(61,'Brown Rice','2 f.oz','Red',43,0.0250675477239354,62,0,0,0,80,14,2,0,2)
,(62,'HB Egg','1 ea','Each',43,0.336145833333333,78,5,1.6,187,124,0.6,0,0.6,6)
,(64,'Quinoa','12 f.oz','4x white',252,0.874251277533039,408,12,0,0,504,72,12,0,12)
,(65,'Tofu','2 f.oz','Red',46,0.333010279001468,42,2.2,0.3,0,1.7,1.2,0.6,0.2,4.3)
,(67,'Chicken','3 f.oz','White',59,0.474144273127753,70,1.5,0.4,36,31.5,0,0,0,13.2)
,(68,'Turkey','3 f.oz','White',59,1.46266744583296,38,0.8,0,19,341.7,0.8,0,0.8,7.6)
,(69,'Steak','3 f.oz','White',45,0.681938325991189,94,5.3,1.9,40,21.3,0,0,0,10.9)
,(70,'Mindful Chkn','3 f.oz','White',50,0.790381791483113,77,2.35,0,0,194,3.5,3,0,11)
,(73,'Dijon Balsamic - PREP','1 f.oz','bottle',28.375,0.166484375,116,9.4,1.4,0,148,9.7,0.2,8.3,0.1)
,(74,'Evergreens Caesar - PREP','1 f.oz','bottle',28.375,0.156328125,154,16,1.3,0,123.1,3.3,0,3,0.1)
,(75,'Red Wine Vini - PREP','1 f.oz','bottle',28.375,0.146171875,140,16,2.6,0,31.1,0.1,0,0,0)
,(77,'Lemon Yogurt Dressing - PREP','1 f.oz','bottle',28.375,0.137734375,34,2.5,1.1,5,110,1,0,0.7,2.1)
,(78,'Sweet Cider Vini','1 f.oz','bottle',28,0.14828125,0,0,0,0,0,0,0,0,0)
,(79,'Cilantro-Lime - PREP','1 f.oz','bottle',28.375,0.17140625,103,10,1.5,0,31,4.7,0.1,4,0.1)
,(80,'Gochujang Vini','1 f.oz','bottle',28,0.1784375,0,0,0,0,0,0,0,0,0)
,(81,'Peppercorn Ranch - PREP',' 1 f.oz','bottle',28,0.16734375,120,12,2,4,140,0.8,0,0.8,0)
,(83,'Black Pepper','1/2 tsp','grinder',1,0.0160822320117474,0,0,0,0,0,0,0,0,0)
,(84,'Evergreens Hot Sauce - PREP','1 Tbl','bottle',14.1875,0.0552734375,0,0,0,0,690,0,0,0,0)
,(85,'Fresh Lemon','1/6th wedge','Each',14,0.0877083333333333,1,0,0,0,0,0.5,0,0.2,0)
,(86,'Herb Pesto','1 f.oz','bottle',28.375,0.411777777777778,48,4.5,0.8,2.5,100,0.5,0.3,0,1.3)
,(87,'Sriracha','1 Tbl','bottle',14.1875,0.0450744047619048,15,0,0,0,300,3,0,3,0)
,(88,'Furikake','.5 Tbl','shaker',2,0.2,0,0,0,0,1,0.3,0,0,0)
,(91,'Black Pepper Hoison Glaze','4 f.oz','ladle',113,0.477995480599647,127,7,0.1,0,1373,14,0.5,7.5,2.4)
,(92,'Chipotle Tomatillo Sauce','4 f.oz','ladle',113,0.283683311287478,60,2.5,0,0,580,9,2,6,1)
,(93,'Cranberry Cream Cheese','2 f.oz','scoop',53,0.389002375296912,157,13.7,9.1,53.2,159.5,2.5,0,1,3.1)
,(94,'Cornbread Stuffing','2 f.oz','Red',25,0.135369318181818,144,7.8,5,20.8,17.2,16.9,0.4,5.7,1.9)
,(95,'Pecans','1 f.oz','Yellow',15,0.206828193832599,100,0.75,0,0,0,2,2,0.75,2)
,(96,'Tahini Lemon Dressing','1 f.oz','bottle',28,0.147299382716049,70,6,0.8,0,65,3,1,0,2)
,(97,'Garbanzos','2 f.oz','Red',65,0.136235588427235,45,1,0,0,70,8,2,0,3)
,(98,'ZaAtar Crunch','2 f.oz','Red',28,0.117421875,40,0.5,0.1,0,20,8,0.5,2,1)
,(99,'NW Farm Kale','8 f.oz','Tongs',20,0.220704845814978,0,0,0,0,0,0,0,0,0)
,(100,'Potlatch Pilaf','12 f.oz','4x white',258,0.735129515418502,430,0,0,0,380,88,11,0,16)
,(101,'Fig Chutney','1 f.oz','Yellow',38,0.305625,120,0,0,0,45,31,2,28,1)
,(102,'Pork Tenderloin','6 f.oz','White',98,0.720969162995595,110,2,1,65,290,1,0,1,21)
,(103,'Marsala Sauce','4 f.oz','ladle',113,0.605668540564374,120,3,0.4,0,760,19,0,12,0)
,(104,'Rosemary Potato','2 f.oz','Red',30,0.182492581602374,40,1,0.1,0,70,8,1,0,1)
,(105,'Radish','2 f.oz','Red',56,0.173985624855089,8,0.5,0,0,20,1.8,0.8,0,0.34)
,(106,'Herb Salt','1/8th','tsp',0.125,0.00182247899159664,0,0,0,0,50,0,0,0,0)
,(107,'Mozzarella Pearls','2 fl oz','Red',45,0.484815528634361,105,7.5,4.5,30,67.5,0,0,0,7.5)
,(108,'Olive Tapenade','2 fl oz','red',44,0.476074400391581,80,6,1,0,360,2,2,0,0)
,(109,'Italian Herb Finish','1','tsp',1.5,0.0316666666666667,5,0,0,0,220,1,0.2,0,0)
,(142,'Regular Bowl, 32','0','0',23,0.16,0,0,0,0,0,0,0,0,0)
,(143,'Large Bowl, 48','0','0',30,0.21,0,0,0,0,0,0,0,0,0)
,(144,'Salad Lid','0','0',12,0.09,0,0,0,0,0,0,0,0,0)
,(145,'Ramekin and Lid','0','0',5,0.07,0,0,0,0,0,0,0,0,0)
,(146,'Fork','0','0',5,0.04,0,0,0,0,0,0,0,0,0)
,(147,'Napkin','0','0',5,0.01,0,0,0,0,0,0,0,0,0)
,(148,'Water Cup, 9 oz','0','0',5,0,0,0,0,0,0,0,0,0,0)
,(149,'Small Bag, #16 Logo','0','0',5,0.1,0,0,0,0,0,0,0,0,0)
,(150,'Tote Bag','0','0',5,0.25,0,0,0,0,0,0,0,0,0)
,(151,'Cargo Bag','0','0',5,0.49,0,0,0,0,0,0,0,0,0)
,(152,'Wrap','0','0',5,0.032,0,0,0,0,0,0,0,0,0)
,(153,'Sticker','0','0',5,0.05,0,0,0,0,0,0,0,0,0)
,(154,'Bread Bag & Bread','0','0',5,0.18,0,0,0,0,0,0,0,0,0)
;

INSERT INTO Recipes Values
(2,'El Sombrero', 'each', 1)
,(3,'Kale Caesar', 'each', 1)
,(4,'Super Bowl', 'each', 1)
,(5,'Cobb', 'each', 1)
,(6,'Along Came A Cider', 'each', 1)
,(7,'Daikon Another Day', 'each', 1)
,(8,'Et Tu Fruite', 'each', 1)
,(9,'Wok This Way', 'each', 1)
,(10,'Jalapeno Business', 'each', 1)
,(11,'Stuffin of Dreams', 'each', 1)
,(12,'Morocc the Casbah', 'each', 1)
,(13,'Getting Figgy With It', 'each', 1)
,(14,'Steak Me Home Tonight', 'each', 1)
,(15,'Godfather', 'each', 1)
,(16, 'Sombrero With Packaging', 'each', 1)
,(17, 'Two Sombrero Combo', 'each', 1)
,(18, 'Snack', '1/5 Salad',5)
;

INSERT INTO CONNECTIONS Values
(2,NULL,12,1)
,(2,NULL,21,1)
,(2,NULL,28,1)
,(2,NULL,30,1)
,(2,NULL,33,1)
,(2,NULL,46,1)
,(2,NULL,55,1)
,(2,NULL,59,1)
,(2,NULL,79,2)
,(3,NULL,10,0.5)
,(3,NULL,12,0.5)
,(3,NULL,30,1)
,(3,NULL,33,1)
,(3,NULL,49,1)
,(3,NULL,53,1)
,(3,NULL,74,2)
,(3,NULL,85,1)
,(4,NULL,9,1)
,(4,NULL,30,1)
,(4,NULL,49,1)
,(4,NULL,17,1)
,(4,NULL,68,1)
,(4,NULL,75,2)
,(4,NULL,86,1)
,(5,NULL,12,1)
,(5,NULL,38,1)
,(5,NULL,48,1)
,(5,NULL,59,1)
,(5,NULL,60,1)
,(5,NULL,62,1)
,(5,NULL,75,2)
,(6,NULL,10,.5)
,(6,NULL,12,.5)
,(6,NULL,23,1)
,(6,NULL,37,1)
,(6,NULL,40,1)
,(6,NULL,42,1)
,(6,NULL,54,1)
,(6,NULL,78,2)
,(7,NULL,12,.5)
,(7,NULL,13,.5)
,(7,NULL,27,1)
,(7,NULL,29,1)
,(7,NULL,31,1)
,(7,NULL,61,1)
,(7,NULL,65,1)
,(7,NULL,80,2)
,(8,NULL,9,.5)
,(8,NULL,12,.5)
,(8,NULL,25,1)
,(8,NULL,42,1)
,(8,NULL,43,1)
,(8,NULL,44,1)
,(8,NULL,46,1)
,(8,NULL,52,1)
,(8,NULL,77,2)
,(9,NULL,22,1)
,(9,NULL,26,1)
,(9,NULL,36,1)
,(9,NULL,61,6)
,(9,NULL,67,2)
,(9,NULL,88,1)
,(9,NULL,91,1)
,(10,NULL,21,1)
,(10,NULL,28,1)
,(10,NULL,30,1)
,(10,NULL,33,1)
,(10,NULL,46,1)
,(10,NULL,61,6)
,(10,NULL,67,2)
,(10,NULL,92,1)
,(11,NULL,12,.5)
,(11,NULL,13,.5)
,(11,NULL,25,1)
,(11,NULL,29,1)
,(11,NULL,68,1)
,(11,NULL,93,1)
,(11,NULL,94,1)
,(11,NULL,95,1)
,(12,NULL,11,.67)
,(12,NULL,24,1)
,(12,NULL,27,1)
,(12,NULL,35,1)
,(12,NULL,40,1)
,(12,NULL,42,1)
,(12,NULL,54,1)
,(12,NULL,97,1)
,(12,NULL,98,1)
,(12,NULL,99,1)
,(13,NULL,10,.33)
,(13,NULL,23,1)
,(13,NULL,29,1)
,(13,NULL,100,1)
,(13,NULL,101,1)
,(13,NULL,102,1)
,(13,NULL,103,1)
,(13,NULL,152,1)
,(13,NULL,153,1)
,(14,NULL,9,1)
,(14,NULL,30,1)
,(14,NULL,32,1)
,(14,NULL,48,1)
,(14,NULL,57,1)
,(14,NULL,69,1)
,(14,NULL,81,1)
,(14,NULL,104,1)
,(14,NULL,105,1)
,(14,NULL,106,1)
,(15,NULL,9,.5)
,(15,NULL,12,.5)
,(15,NULL,27,1)
,(15,NULL,30,1)
,(15,NULL,35,1)
,(15,NULL,53,1)
,(15,NULL,75,2)
,(15,NULL,107,1)
,(15,NULL,108,1)
,(15,NULL,109,1)
,(16,2,NULL,1)
,(16,NULL,142,1)
,(16,NULL,144,1)
,(16,NULL,145,1)
,(16,NULL,146,1)
,(16,NULL,147,1)
,(16,NULL,148,0.5)
,(16,NULL,149,0.5)
,(16,NULL,151,0.25)
,(16,NULL,154,1)
,(17,16,NULL,2)
,(18,2,NULL,1)
;

DROP VIEW IF EXISTS RecipeTotalValues;
CREATE VIEW RecipeTotalValues 
AS 
WITH tree AS (
  SELECT ParentRecipe as Id, ParentRecipe, ChildRecipe, ChildIngredient, Quantity, 1 AS level
  FROM connections
  
  UNION ALL
  
  SELECT t.Id, c.ParentRecipe, c.ChildRecipe, c.ChildIngredient, c.Quantity*t.Quantity/r.OutputQty, t.level + 1
  FROM connections c
  INNER JOIN tree t ON c.ParentRecipe = t.ChildRecipe
  INNER JOIN Recipes r on t.ChildRecipe = r.Id
  WHERE t.ChildRecipe IS NOT NULL

)
SELECT 
  r.Id
  , COALESCE( SUM(i.Weight * t.Quantity)/r.OutputQty , 0) AS Weight
  , COALESCE( SUM(i.Cost * t.Quantity)/r.OutputQty , 0) AS Cost
  , COALESCE( SUM(i.Calories * t.Quantity)/r.OutputQty , 0) AS Calories
  , COALESCE( SUM(i.TTLFatGrams * t.Quantity)/r.OutputQty , 0) AS TTLFatGrams
  , COALESCE( SUM(i.SatFatGrams * t.Quantity)/r.OutputQty , 0) AS SatFatGrams
  , COALESCE( SUM(i.CholesterolMilligrams * t.Quantity)/r.OutputQty , 0) AS CholesterolMilligrams
  , COALESCE( SUM(i.SodiumMilligrams * t.Quantity)/r.OutputQty , 0) AS SodiumMilligrams
  , COALESCE( SUM(i.CarbGrams * t.Quantity)/r.OutputQty , 0) AS CarbGrams
  , COALESCE( SUM(i.FiberGrams * t.Quantity)/r.OutputQty , 0) AS FiberGrams
  , COALESCE( SUM(i.SugarGrams * t.Quantity)/r.OutputQty , 0) AS SugarGrams
  , COALESCE( SUM(i.ProteinGrams * t.Quantity)/r.OutputQty , 0) AS ProteinGrams

 FROM Recipes r
 LEFT JOIN tree t on t.Id=r.Id
 LEFT JOIN ingredients i ON t.ChildIngredient = i.id
 GROUP BY r.Id,r.OutputQty;

-- Join recipe data back to the result from view above
DROP VIEW IF EXISTS RecipesWithNutrition;
CREATE VIEW RecipesWithNutrition 
AS SELECT r.Name, r.Unit, r.OutputQty, rtv.* FROM Recipes r LEFT JOIN RecipeTotalValues rtv ON r.id=rtv.Id;

DROP VIEW IF EXISTS RecipeDetails;
CREATE VIEW RecipeDetails
AS SELECT Id
 , Name
 , Unit
 , OutputQty
 , CAST(Weight AS Int) AS Weight
 , '$' + CAST(ROUND(Cost, 2) AS Varchar) AS Cost
 , CAST(Calories AS Int) AS Calories
 , CAST(TTLFatGrams AS Int) AS TTLFatGrams
 , CAST(SatFatGrams AS Int) AS SatFatGrams
 , CAST(CholesterolMilligrams AS Int) AS CholesterolMilligrams
 , CAST(SodiumMilligrams AS Int) AS SodiumMilligrams
 , CAST(CarbGrams AS Int) AS CarbGrams
 , CAST(FiberGrams AS Int) AS FiberGrams
 , CAST(SugarGrams AS Int) AS SugarGrams
 , CAST(ProteinGrams AS Int) AS ProteinGrams
FROM RecipesWithNutrition;