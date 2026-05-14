-- Generated from "RecipeBuilder 2025 JULY.xlsx"
-- 123 ingredients, 28 recipes, 298 connections, 183 price rows

INSERT INTO Ingredients
(Id, Name, Unit, Portion, Weight, Cost, Calories, TTLFatGrams, SatFatGrams, CholesterolMilligrams, SodiumMilligrams, CarbGrams, FiberGrams, SugarGrams, ProteinGrams, ImageFilename)
VALUES
(1,'Bread','1/40th loaf',NULL,0,0,0,0,0,0,0,0,0,0,0,'BRead-104.png')
,(2,'Packaging','1 ea',NULL,0,0,0,0,0,0,0,0,0,0,0,NULL)
,(3,'Arugula','3 cups','Portion Cup',58,0.428931718061674,18,0.6,0.5,0,18,2.4,1.2,1.2,1.8,'Arugula.png')
,(4,'Kale','3 cups','Portion Cup',63,0.438640969162996,99,1.8,0.3,0,75,18,7.2,4.5,8.6,'Kale.png')
,(5,'Mixed Greens','3 cups','Portion Cup',63,0.363105726872247,30,0,0,0,142.5,6,1.5,1.5,1.5,'Mixed Greens.png')
,(6,'Romaine','3 cups','Portion Cup',146,0.710168869309838,18,0.3,0,0,8.6,3.6,2.3,1.3,1.3,'Romaine.png')
,(7,'Spinach','3 cups','Portion Cup',103,0.565592511013216,21,0.4,0.1,0,71.1,3.3,2,0.4,2.6,'Spinach.png')
,(8,'Brown Rice','8 f.oz','2 x grey',129,0.07520264317180617,186,0,0,0,240,42,6,0,6,'Brown Rice.png')
,(9,'Wheat Wrap XTRM','1 ea','each',100,0.567638888888889,110,3,0,0,620,33,25,0,12,'Wrap.png')
,(10,'Quinoa','8 f.oz','2 x grey',126,0.321538678414097,204,6,0,0,251,36,6,0,6,'Quinoa.png')
,(11,'Ancient Grains','3 f.oz','White',50,0.43997797356828194,70,0.5,0,0,90,15,2,0,2,'Ancient Grains.png')
,(12,'Jasmine Rice','8 f.oz','scoop',186,0.27965550660793,233,2.5,0.3,0,140,47,0,0,4,'Jasmine Rice.png')
,(13,'Cucumber','2 f.oz','Red',49,0.32139011257954,4,0,0,0,0.5,1,0.2,0.5,0,'Cucumber.png')
,(14,'Green Onion','1 f.oz','Yellow',9,0.0657366617719041,0,0,0,0,0,0,0,0,0,'Green Onion.png')
,(15,'Green Papaya','3 f.oz','White',35,0.0986006737496761,15,0,0,0,5,9,2,1,1,NULL)
,(16,'Jalapenos','1 f.oz','Yellow',22,0.0493465491923642,6,0.1,0,0,0.2,1.3,0.6,0.7,0.3,'Jalapeno.png')
,(17,'Grape Tomatoes','2 f.oz','Red',49,0.190279735682819,8,0.1,0,0,2.3,1.8,0.6,1.2,0.4,'Tomato.png')
,(18,'Red Bell Peppers','2 f.oz','Red',46,0.173346758967904,12,0.1,0,0,1.5,2.2,0.8,1.6,0.4,'Red Bell Pepper.png')
,(19,'Carrots, shredded','2 f.oz','Tongs',18,0.0447819383259912,10,0,0,0,15,2,1,1,0,'Carrot.png')
,(20,'Beets, cooked','2 f.oz','Red',47,0.295044052863436,20,0,0,0,45,4,1,1,1,'Beets.png')
,(21,'Celery','1 f.oz','Tongs',14,0.0743171806167401,0,0,0,0,10,0,0,0,0,'Celery.png')
,(22,'Zucchini, grated','2 f.oz','Red',25,0.130136632709251,5,0.1,0,0,0,1,0.3,0,0.3,'Zucchini.png')
,(23,'Tofu','3 f.oz','White',53,0.383685756240822,42,2.2,0.3,0,1.7,1.2,0.6,0.2,4.3,'Tofu.png')
,(24,'Avocado +$2','.5 ea','Half',61,0.245769230769231,117,9.9,1.9,0,2,7.6,5.5,2.4,2.2,'Avocado.png')
,(25,'Apple','2 f.oz','Red',30,0.0921129451727615,29,0.1,0,0,0.5,7.3,1.4,5.8,0.1,'Cosmic Crisp Apple.png')
,(26,'Fresh Lemon','1/6th wedge','Each',14,0.08770833333333333,1,0,0,0,0,0.5,0,0.2,0,'Lemon.png')
,(27,'Watermelon Radish','2 f.oz','red',31,0.0980751595792502,9,0.1,0,0,21,1.9,0.9,0,0.4,'Watermelon Radish.png')
,(28,'Mint / Thai Basil','2 f.oz','red',4,0.174131736526946,5,0,0,0,0,0,0,0,0,NULL)
,(29,'Cilantro Leaves','1 f.oz','Tongs',5,0.0348017621145374,1,0,0,0,1,0,0.1,0,0,'Cilantro.png')
,(30,'Gorgonzola','2 f.oz','Red',38,0.397660792951542,152,12.1,9.1,38,577.1,1.5,0,0,9.1,'Gorgonzola.png')
,(31,'Fresh Mozzarella','2 f.oz','Red',45,0.46883259911894276,105,7.5,4.5,30,67.5,0,0,0,7.5,'Mozzarella.png')
,(32,'Local White Cheddar','2 f.oz','Red',29,0.348766519823789,120,10,6,30,200,1,0,0,6,'Cheddar.png')
,(33,'Parmesan','2 f.oz','Tongs',15,0.186773127753304,83,5.5,3.5,14.4,339.2,0.7,0,0.2,7.6,'Parmesean.png')
,(34,'Feta Cheese','2 f.oz','Red',32,0.198370044052863,80,7,5,30,354,1.2,0,0,4.5,'Feta.png')
,(35,'HB Egg','1 ea','Each',43,0.341111111111111,78,5,1.6,187,124,0.6,0,0.6,6,'Egg.png')
,(36,'Bacon','1 f.oz','Yellow',15,0.218623348017621,64.5,4.5,1.5,18,284,0,0,0,5.4,'Bacon.png')
,(37,'Grilled Steak','3 f.oz','White',45,0.851332599118943,80,4,1.5,33,310,1.5,0,0,10,'Steak.png')
,(38,'Chicken','3 f.oz','White',59,0.510921806167401,70,1.5,0.4,36,31.5,0,0,0,13.2,'Chicken - Short.png')
,(39,'Pork, smoked w/bbq sauce','3 f.oz','White',66,0.803775330396476,100,2,1.5,30,380,3,0,2,11,'Smoked Pork-181.png')
,(40,'Chimichurri Chicken','3 f.oz','White',63,0.7049878542510122,90,3.5,0.6,36,102,0.34,0.11,0,13.3,'Chimi Chicken.png')
,(41,'Egg w/butter (BFAST)','3 f.oz','red',83,0.7299599158629996,126,9.8,2.25,217,322,2.8,0,0,7,'Egg.png')
,(42,'Tofu, TACO Makini','3 f.oz','White',70,0.866110761485211,40,2.5,0,0,350,1,1,0,4,'Tofu.png')
,(43,'Fire Roasted Corn','2 f.oz','Red',50,0.2465859030837,41,0.7,0,0,0,7.1,1.9,2.6,1.1,'Corn.png')
,(44,'Rstd Yellow Tomatoes','1 f.oz','Yellow',25,0.437431167400881,60,0,0,0,130,3,1,0,2,'Roasted Tomato.png')
,(45,'Black Beans - Low Sodium','2 f.oz','Red',52,0.146649769677951,45,0.3,0,0,230,9.5,3,0.3,3.5,'Black Beans.png')
,(46,'Tortilla Chips','3 f.oz','White',23,0.126314243759178,140,9,1.5,0,129.9,15,1,0,2,'Tortilla Chips.png')
,(47,'Garbanzos','2 f.oz','Red',65,0.123898738307592,45,1,0,0,70,8,2,0,3,'Garbanzo.png')
,(48,'Giardiniera, Mild','2 f.oz','Red',40,0.370623840653766,80,8,0,0,560,2,1,0,0,NULL)
,(49,'Greek Olives, wedges','1 f.oz','Yellow',20,0.268766519823789,70,7,0,0,460,2,0,0,0,NULL)
,(50,'Crispy Onions','1 f.oz','Yellow',13,0.136967694566814,71,5.25,0,0,20,4.5,0,0,0,'Crispy Onion.png')
,(51,'Crispy Jalapenos','1 f.oz','Yellow',14,0.170837004405286,90,6,0,0,30,6,0,0,0,'Crispy Jalapeno.png')
,(52,'Sesame Sticks','1 f.oz','Yellow',12,0.24411764705882355,68,4.8,0.712,0,180,5.6,0.8,2.8,1.2,'Sesame Sticks.png')
,(53,'Golden Raisins','1 f.oz','Yellow',19,0.12956828193832598,65,0,0,0,5,16,1,14,1,'Golden Raisins.png')
,(54,'Pepitas, roasted','1 f.oz','Yellow',18,0.232969162995595,80,7,1.25,0,59,2,1,0,4,'Pepitas.png')
,(55,'Pita Chips','3 f.oz','White',18,0.369774341454644,84,3.2,0.3,0,173,12.2,0.6,0.6,1.9,NULL)
,(56,'Cashews','1 f.oz','Yellow',20,0.27057268722467,120,9.9,1.8,0,0,6.3,0.7,1.4,3.5,'Cashew.png')
,(57,'Pineapple, tidbits','2 f.oz','red',66,0.2649,40,0,0,0,0,9,0.5,0,0.5,'Crushed Pineapple.png')
,(58,'Sunflower Seeds','1 f.oz','Yellow',18,0.15363436123348,100,8.7,1.2,0,69.2,3.9,1.8,0.5,3.4,'Sunflower Seeds.png')
,(59,'Balsamic Glaze','1/2 f.oz','btl',15,0.212819724754977,35,0,0,0,0,8,0,8,0,'Balsamic Glaze.png')
,(60,'Hummus','2 f.oz','Blue Scoop',63,0.532831898277933,120,10,1.2,0,150,8,4,0,4,'Hummus.png')
,(61,'Dried Cranberry','1 f.oz','Yellow',20,0.176387665198238,60,0,0,0,0,16,2,15,0,'Dried Cranberry-116.png')
,(62,'Lentils w/ Pesto','2 f.oz','Red',40,0.327666666666667,56,1.9,0.2,0,96.9,5.1,2.8,0.1,3.2,'Jalapeno Pesto Lentils-08.png')
,(63,'Jalapeno Pesto','1 f.oz','Yellow',28,0.441277533039648,78,7.6,0.6,0,277,2,0.6,0,0.3,'Jalapeno Pesto Finish.png')
,(64,'MG Garlic & Cheese Crouton','3 f.oz','White',24,0.165462555066079,90,3,0,0,240,15,0,0,3,'Garlic Cheese Croutons.png')
,(65,'Candied Walnut','1 f.oz','Yellow',17,0.28503083700440524,95,7,0.75,0,45,9,0.5,8,0.5,'Candied Walnuts.png')
,(66,'Pickled Spicy Pepper','1 f.oz','Tongs',20,0.29046551768555,10,0,0,0,200,1,1,1,0,'Peperoncini.png')
,(67,'Pickled Onion - Savor','1 w.oz','Tongs',20,0.203003838524358,24,0,0,0,82.2,4.3,0.7,1.9,0.5,'Pickled Red Onion.png')
,(68,'Roasted Broccoli','3 f.oz','White',45,0.771888766519824,60,6,0.8,0,45,3,1,1,1,'Broccoli.png')
,(69,'Rstd Brussels Sprouts','3 f.oz','White',49,0.23132892804698968,46,1.5,0.2,0,101,5.9,2.2,1.5,2.2,'Roasted Brussels Sprouts.png')
,(70,'Roasted Sweet Potato - charlies','2 f.oz','Red',38,0.561546255506608,45,1.5,0.2,0,20,8,1,2,1,'Roasted Sweet Potoato.png')
,(71,'Roasted Cauliflower','2 f.oz','Red',33,0.3566519823788546,30,1.5,0.2,0,60,3,2,1,0.4,'Roasted Cauliflower.png')
,(72,'Pickles, county fair sysco','2 f.oz','Tongs',37,0.123782616062352,3,0,0,0,433,0.67,0.08,0.3,0.1,'House Pickle.png')
,(73,'Black Pepper','1/2 tsp','grinder',1,0.016082232011747428,0,0,0,0,0,0,0,0,0,'Black Pepper.png')
,(74,'BBQ Sauce - NWG','1 f.oz','bottle',35,0.197260462555066,30,0,0,0,383,6.6,0,5.6,0,NULL)
,(75,'Sriracha, FIX IT brand','1 tsp','btl',5,0.050433006535947705,3,0,0,0,127,0.7,0,0.7,0.1,NULL)
,(76,'Petes Hot Sauce','1/2 f.oz','bottle',14,0.0580217511013216,0,0,0,0,345,0,0,0,0,NULL)
,(77,'Za''Atar Spices','1 tsp','shaker',2,0.0922907488986784,0,0,0,0,180,0,0,0,0,NULL)
,(78,'Chimichurri','1 f.oz','Yellow',28,0.41830396475770926,80,8,0.7,0,353,1.7,0.56,0,0.56,'Chimichurri Sauce.png')
,(79,'BK Spices','1/4 tsp','shaker',0.7,0.0299901960784314,0,0,0,0,35,0,0,0,0,'Southern Spices.png')
,(80,'Cilantro-Lime - NWG','1 f.oz','bottle',28.375,0.2428515625,130,13,1.65,0,134,3.72,0.1,3,0.1,'Cilantro Lime.png')
,(81,'Evergreens Caesar - NWG','1 f.oz','bottle',28.375,0.3010546875,170,18,2.7,13.14,261,1.1,0,0.62,1.22,'Caesar.png')
,(82,'Red Wine Vini - NWG','1 f.oz','bottle',28.375,0.24546875,140,16,2,0,70,0,0,0,0,'Red Wine Vini.png')
,(83,'Greek Yogurt - NWG','1 f.oz','bottle',28.375,0.218984375,48,4.5,2,8.2,210,1.5,0.05,1,1,'Greek Yogurt.png')
,(84,'Dijon Balsamic - NWG','1 f.oz','bottle',28.375,0.25546875,130,12,1.5,0,210,6,0,5,0,'Dijon Balsamic.png')
,(85,'Peppercorn Ranch - NWG',' 1 f.oz','bottle',28.375,0.2263671875,113,12,1.5,11.7,229,1,0.03,0.8,0.6,'Peppercorn Ranch.png')
,(86,'Haba Mango Dressing - NWG','1 f.oz','bottle',28.375,0.353046875,70,7,1,0,70,5,0,5,0,'Habanero Mango Dressing.png')
,(87,'Green Goddess (NWG)','1 f.oz','bottle',28.375,0.24015625,110,12,1.5,10,160,1,0,1,0,'Green Goddess Dressing.png')
,(88,'Lemon Tahini Dressing, NWG','1 f.oz','bottle',28.375,0.2741796875,106,10.25,1.35,0,161.5,2.31,0.55,0.507,1,NULL)
,(89,'Creamy Cashew Dressing, NWG','1 f.oz','bottle',28.375,0.210546875,92,9.2,1.28,0,276,3.57,0.11,1.55,0.7,'Creamy Cashew Dressing.png')
,(90,'Harissa Yogurt Dressing, NWG','1 f.oz','bottle',28.375,0.2993359375,78.32,7.98,1.79,7,229,1.39,0.09,0.75,0.7,'Harissa Yogurt Dressing.png')
,(91,'Ginger Scallion Dressing, NWG','1 f.oz','bottle',28.375,0.2701171875,62,4.75,0.65,0,263,4.3,0.18,3.35,0.53,NULL)
,(92,'Jalapeno Pesto Ranch Dressing','1 f.oz','bottle',28.375,0.287037037037037,129,13.7,2.1,2,194,1,0.2,0.5,0.4,NULL)
,(93,'Lemon Basil Vini, NWG','1 f.oz','bottle',28.375,0.2912890625,120,12,1.58,0,160,3,0,2,0,'Lemon Basil Vini.png')
,(94,'Thai Green Curry, NWG','4 f.oz','ladle',100,0.627753303964758,110,8.5,7.8,0,590,6,1,5,1,'Green Curry-112.png')
,(95,'Chipotle Tomatillo, NWG','4 f.oz','ladle',100,0.844530102790015,41,1.85,0.237,0,490,5.5,1.7,3.3,1.4,'Chipotle Tomatillo.png')
,(96,'Sriracha Caesar','1 f.oz','bottle',28.375,0.350605867346939,220,22,3.5,20,520,2,0,1,1,NULL)
,(97,'Red Coconut Curry Dressing','1 f.oz','bottle',100,0.270647321428571,110,12,2.5,0,180,2,0,1,0,NULL)
,(98,'Red Coconut Curry Sauce','4 f.oz','ladle',100,1.08258928571429,440,48,10,0,720,0,0,0,0,NULL)
,(99,'Nuoc Cham Dressing','1 f.oz','bottle',28.375,0.1856640625,25,0,0,0,330,6,0,6,1,NULL)
,(100,'GRN Compost Bowl/lid, 32 oz',NULL,NULL,0,0.46,0,0,0,0,0,0,0,0,0,NULL)
,(101,'GRN Compost Ramekin',NULL,NULL,0,0.03,0,0,0,0,0,0,0,0,0,NULL)
,(102,'GRN Compost Ramekin LID',NULL,NULL,0,0.03,0,0,0,0,0,0,0,0,0,NULL)
,(103,'80 oz Catering Square, 50cs',NULL,NULL,0,1.23,0,0,0,0,0,0,0,0,0,NULL)
,(104,'120 oz Catering Bowl, 50 cs',NULL,NULL,0,1.4013999999999998,0,0,0,0,0,0,0,0,0,NULL)
,(105,'CLR Lid, catering bowls, 50 cs',NULL,NULL,0,0.636,0,0,0,0,0,0,0,0,0,NULL)
,(106,'6" serving tongs, toppings, 72 cs',NULL,NULL,0,0.39722222222222225,0,0,0,0,0,0,0,0,0,NULL)
,(107,'9'' Serving tongs, 36 cs',NULL,NULL,0,0.6266666666666666,0,0,0,0,0,0,0,0,0,NULL)
,(108,'10" Serving Spoon, 72 cs',NULL,NULL,0,0.30763888888888885,0,0,0,0,0,0,0,0,0,NULL)
,(109,'Catering Jars, 16 oz w/lid',NULL,NULL,0,0,0,0,0,0,0,0,0,0,0,NULL)
,(110,'26 oz Lid','1',NULL,1,0.26,0,0,0,0,0,0,0,0,0,NULL)
,(111,'26 oz Bowl','1',NULL,1,0.34,0,0,0,0,0,0,0,0,0,NULL)
,(112,'Bowl SugarCane compost, 32',NULL,NULL,23,0.21,0,0,0,0,0,0,0,0,0,NULL)
,(113,'Large Bowl, 48',NULL,NULL,30,0.25,0,0,0,0,0,0,0,0,0,NULL)
,(114,'Salad Dome Lid, EG LOGO',NULL,NULL,12,0.23,0,0,0,0,0,0,0,0,0,NULL)
,(115,'Ramekin and Lid',NULL,NULL,5,0.032468000000000004,0,0,0,0,0,0,0,0,0,NULL)
,(116,'Fork',NULL,NULL,5,0.05035,0,0,0,0,0,0,0,0,0,NULL)
,(117,'Napkin',NULL,NULL,5,0.01,0,0,0,0,0,0,0,0,0,NULL)
,(118,'Small Bag, #57 Logo',NULL,NULL,5,0.134125,0,0,0,0,0,0,0,0,0,NULL)
,(119,'Lg Bag, Logo',NULL,NULL,5,0.97,0,0,0,0,0,0,0,0,0,NULL)
,(120,'TOTE #65 Bag',NULL,NULL,5,0.31676,0,0,0,0,0,0,0,0,0,NULL)
,(121,'Wrap Paper, LOGO',NULL,NULL,5,0.052399999999999995,0,0,0,0,0,0,0,0,0,NULL)
,(122,'Sticker',NULL,NULL,5,0.06484999999999999,0,0,0,0,0,0,0,0,0,NULL)
,(123,'Bread Bag & Bread',NULL,NULL,5,0.2,0,0,0,0,0,0,0,0,0,'BRead-104.png');

INSERT INTO Recipes Values
(1,'Kale Caesar','each',1)
,(2,'El Sombrero','each',1)
,(3,'Cobb','each',1)
,(4,'Southern Saucepitality','each',1)
,(5,'Steak It Off','each',1)
,(6,'JAN - Julius Heat-er salad','each',1)
,(7,'JAN - Plant One on Me Wrap','each',1)
,(8,'JAN - What the Cluck','each',1)
,(9,'JAN - heat of the Moment Bowl','each',1)
,(10,'Summer Salad','each',1)
,(11,'Summer Bowl','each',1)
,(12,'Summer 3 wrap','each',1)
,(13,'Spice Spice Baby - cal BOWL','each',1)
,(14,'Jalapeno Business 3.0','each',1)
,(15,'Fast & Curryous 2.0','each',1)
,(16,'Med Over Heels 2.0','each',1)
,(17,'Papaya Don’t Preach','each',1)
,(18,'Curryous George','each',1)
,(19,'Mint Condition wrap','each',1)
,(20,'PRIDE','each',1)
,(21,'SouthWest Bound burrito','each',1)
,(22,'PORK BFAST WRAP','each',1)
,(23,'PORK QUINOA BOWL','each',1)
,(24,'Steaks On A Plane','each',1)
,(25,'FAA-vorite Bowl','each',1)
,(26,'Not Not A Burrito','each',1)
,(27,'Ranch The Wrapper','each',1)
,(28,'I Dream of Tahini','each',1)
;

INSERT INTO Connections (ParentRecipe, ChildRecipe, ChildIngredient, Quantity) VALUES
(5,NULL,3,0.25)
,(9,NULL,3,0.15)
,(10,NULL,3,0.5)
,(12,NULL,3,0.33)
,(20,NULL,3,0.5)
,(25,NULL,3,0.25)
,(27,NULL,3,0.15)
,(28,NULL,3,0.33)
,(1,NULL,4,0.5)
,(6,NULL,4,0.5)
,(11,NULL,4,0.125)
,(4,NULL,5,0.16)
,(17,NULL,5,0.5)
,(19,NULL,5,0.15)
,(20,NULL,5,0.5)
,(1,NULL,6,0.5)
,(2,NULL,6,1)
,(3,NULL,6,1)
,(4,NULL,6,0.16)
,(5,NULL,6,0.25)
,(6,NULL,6,0.5)
,(8,NULL,6,0.33)
,(10,NULL,6,0.5)
,(17,NULL,6,0.5)
,(19,NULL,6,0.15)
,(7,NULL,7,0.15)
,(13,NULL,7,0.15)
,(18,NULL,7,0.15)
,(21,NULL,7,0.15)
,(22,NULL,7,0.15)
,(24,NULL,7,0.15)
,(7,NULL,9,1)
,(8,NULL,9,1)
,(12,NULL,9,1)
,(19,NULL,9,1)
,(21,NULL,9,1)
,(22,NULL,9,1)
,(26,NULL,9,1)
,(27,NULL,9,1)
,(28,NULL,9,1)
,(7,NULL,10,0.5)
,(9,NULL,10,1)
,(11,NULL,10,1)
,(16,NULL,10,1)
,(20,NULL,10,0.4)
,(21,NULL,10,0.5)
,(23,NULL,10,1)
,(24,NULL,10,1)
,(25,NULL,10,1)
,(26,NULL,10,0.5)
,(13,NULL,12,1)
,(14,NULL,12,1)
,(15,NULL,12,1)
,(18,NULL,12,1)
,(22,NULL,12,0.5)
,(27,NULL,12,0.5)
,(6,NULL,13,1)
,(10,NULL,13,1)
,(11,NULL,13,1)
,(16,NULL,13,1)
,(17,NULL,13,1)
,(19,NULL,13,1)
,(20,NULL,13,1)
,(27,NULL,13,1)
,(28,NULL,13,1)
,(8,NULL,14,1)
,(15,NULL,14,1)
,(17,NULL,14,1)
,(18,NULL,14,1)
,(21,NULL,14,1)
,(23,NULL,14,1)
,(24,NULL,14,1)
,(25,NULL,14,1)
,(26,NULL,14,1)
,(27,NULL,14,1)
,(17,NULL,15,1)
,(19,NULL,15,1)
,(1,NULL,16,1)
,(2,NULL,16,1)
,(5,NULL,16,1)
,(6,NULL,16,1)
,(7,NULL,16,1)
,(9,NULL,16,1)
,(13,NULL,16,1)
,(14,NULL,16,1)
,(22,NULL,16,1)
,(24,NULL,16,1)
,(27,NULL,16,1)
,(1,NULL,17,1)
,(2,NULL,17,1)
,(6,NULL,17,1)
,(11,NULL,17,1)
,(12,NULL,17,1)
,(14,NULL,17,1)
,(19,NULL,17,1)
,(24,NULL,17,1)
,(27,NULL,17,1)
,(28,NULL,17,1)
,(4,NULL,18,1)
,(9,NULL,18,1)
,(10,NULL,18,1)
,(12,NULL,18,1)
,(15,NULL,18,1)
,(16,NULL,18,1)
,(17,NULL,18,1)
,(18,NULL,18,1)
,(20,NULL,18,1)
,(21,NULL,18,1)
,(23,NULL,18,1)
,(25,NULL,18,1)
,(26,NULL,18,1)
,(7,NULL,19,1)
,(8,NULL,19,1)
,(15,NULL,19,1)
,(17,NULL,19,1)
,(18,NULL,19,1)
,(20,NULL,19,1)
,(27,NULL,19,1)
,(7,NULL,20,1)
,(8,NULL,21,2)
,(13,NULL,21,1)
,(15,NULL,22,1)
,(18,NULL,23,1)
,(2,NULL,24,1)
,(3,NULL,24,1)
,(14,NULL,24,1)
,(23,NULL,24,1)
,(1,NULL,26,1)
,(6,NULL,26,1)
,(6,NULL,27,1)
,(10,NULL,27,1)
,(11,NULL,27,1)
,(20,NULL,27,1)
,(11,NULL,28,1)
,(17,NULL,28,1)
,(19,NULL,28,1)
,(7,NULL,29,1)
,(14,NULL,29,1)
,(18,NULL,29,1)
,(23,NULL,29,1)
,(26,NULL,29,1)
,(28,NULL,29,1)
,(3,NULL,30,1)
,(5,NULL,30,1)
,(2,NULL,32,1)
,(4,NULL,32,1)
,(8,NULL,32,1)
,(13,NULL,32,1)
,(14,NULL,32,1)
,(21,NULL,32,1)
,(22,NULL,32,1)
,(23,NULL,32,1)
,(24,NULL,32,1)
,(1,NULL,33,1)
,(6,NULL,33,1)
,(10,NULL,33,1)
,(12,NULL,33,1)
,(20,NULL,33,1)
,(25,NULL,33,1)
,(9,NULL,34,1)
,(11,NULL,34,1)
,(16,NULL,34,1)
,(26,NULL,34,1)
,(28,NULL,34,1)
,(3,NULL,35,1)
,(3,NULL,36,1)
,(21,NULL,36,1)
,(25,NULL,36,1)
,(5,NULL,37,1)
,(12,NULL,37,1)
,(15,NULL,37,2)
,(19,NULL,37,1)
,(24,NULL,37,1)
,(6,NULL,38,1)
,(8,NULL,38,1)
,(14,NULL,38,1)
,(16,NULL,38,2)
,(17,NULL,38,1)
,(27,NULL,38,1)
,(28,NULL,38,1)
,(13,NULL,39,1)
,(22,NULL,39,1)
,(23,NULL,39,1)
,(26,NULL,39,1)
,(21,NULL,41,1)
,(22,NULL,41,1)
,(23,NULL,41,1)
,(24,NULL,41,1)
,(25,NULL,41,1)
,(7,NULL,42,1)
,(2,NULL,43,1)
,(4,NULL,43,1)
,(13,NULL,43,1)
,(18,NULL,43,1)
,(26,NULL,43,1)
,(5,NULL,44,1)
,(10,NULL,44,1)
,(20,NULL,44,1)
,(2,NULL,45,1)
,(14,NULL,45,1)
,(21,NULL,45,1)
,(24,NULL,45,1)
,(26,NULL,45,1)
,(2,NULL,46,1)
,(12,NULL,47,1)
,(10,NULL,48,1)
,(12,NULL,48,1)
,(7,NULL,49,1)
,(11,NULL,49,1)
,(4,NULL,50,1)
,(5,NULL,50,1)
,(12,NULL,50,1)
,(15,NULL,50,1)
,(18,NULL,50,1)
,(22,NULL,50,1)
,(6,NULL,51,1)
,(8,NULL,51,1)
,(13,NULL,51,1)
,(19,NULL,51,1)
,(7,NULL,54,1)
,(20,NULL,54,1)
,(10,NULL,55,1)
,(11,NULL,55,1)
,(17,NULL,56,1)
,(18,NULL,56,1)
,(15,NULL,57,1)
,(19,NULL,57,1)
,(9,NULL,58,1)
,(16,NULL,58,1)
,(5,NULL,59,1)
,(16,NULL,60,1)
,(9,NULL,62,1)
,(11,NULL,62,1)
,(9,NULL,63,1)
,(1,NULL,64,1)
,(6,NULL,64,1)
,(5,NULL,66,1)
,(8,NULL,66,1)
,(9,NULL,66,1)
,(13,NULL,66,1)
,(28,NULL,66,1)
,(3,NULL,67,1)
,(4,NULL,67,1)
,(7,NULL,67,1)
,(14,NULL,67,1)
,(16,NULL,67,1)
,(20,NULL,67,1)
,(9,NULL,70,1)
,(4,NULL,72,1)
,(4,NULL,74,1)
,(17,NULL,75,1)
,(8,NULL,76,1)
,(13,NULL,76,1)
,(16,NULL,76,1)
,(22,NULL,76,1)
,(7,NULL,77,1)
,(9,NULL,77,1)
,(11,NULL,77,1)
,(10,NULL,78,0.25)
,(4,NULL,79,1)
,(5,NULL,79,1)
,(6,NULL,79,1)
,(8,NULL,79,1)
,(13,NULL,79,1)
,(2,NULL,80,2)
,(24,NULL,80,2)
,(1,NULL,81,2)
,(3,NULL,82,2)
,(16,NULL,83,2)
,(12,NULL,84,2)
,(4,NULL,85,2)
,(5,NULL,85,2)
,(10,NULL,85,2)
,(13,NULL,85,2)
,(22,NULL,85,2)
,(25,NULL,85,2)
,(27,NULL,85,2)
,(7,NULL,88,2)
,(9,NULL,88,2)
,(11,NULL,88,2)
,(28,NULL,88,2)
,(8,NULL,90,2)
,(20,NULL,92,1)
,(15,NULL,94,1)
,(14,NULL,95,1)
,(21,NULL,95,0.5)
,(23,NULL,95,1)
,(26,NULL,95,0.75)
,(6,NULL,96,2)
,(19,NULL,97,2)
,(18,NULL,98,1)
,(17,NULL,99,2)
,(23,NULL,110,1)
,(24,NULL,110,1)
,(25,NULL,110,1)
,(23,NULL,111,1)
,(24,NULL,111,1)
,(25,NULL,111,1)
;

-- Backfill SortOrder so each component within a parent has a distinct,
-- stable order. Same per-parent rowid-based ranking as migrateDB(); kept
-- here so freshly-initialized DBs match migrated DBs.
UPDATE Connections
SET SortOrder = (
    SELECT COUNT(*)
    FROM Connections c2
    WHERE c2.ParentRecipe = Connections.ParentRecipe
      AND c2.rowid <= Connections.rowid
);

INSERT INTO suppliers (name) VALUES ('Sysco'),('Charlies');

-- Canonical tag set. Recipe formats drive the homepage silhouette;
-- ingredient categories drive the colored badges.
INSERT INTO tags (id, name, kind, color, shape, sortOrder) VALUES
 (1,'Salad','recipe','#16a34a','ring',1)
,(2,'Wrap','recipe','#b45309','wrap',2)
,(3,'Bowl','recipe','#ea580c','bowl',3)
,(4,'Catering','recipe','#7c3aed','tray',4)
,(5,'Greens','ingredient','#15803d','none',1)
,(6,'Grains','ingredient','#92400e','none',2)
,(7,'Toppings','ingredient','#dc2626','none',3)
,(8,'Cheese','ingredient','#eab308','none',4)
,(9,'Crunchies','ingredient','#a16207','none',5)
,(10,'Premiums','ingredient','#9333ea','none',6)
,(11,'Protein','ingredient','#be185d','none',7)
,(12,'Dressing','ingredient','#0891b2','none',8)
,(13,'Finish','ingredient','#db2777','none',9)
,(14,'Packaging','ingredient','#475569','none',10)
;

-- Each ingredient gets at most one category tag. Packaging items
-- (Bread, Packaging, wraps/lids/bags 100-123) intentionally have no tag.
INSERT INTO ingredient_tags_mapping (tag_id, ingredient_id) VALUES
 -- Greens (5)
 (5,3),(5,4),(5,5),(5,6),(5,7)
 -- Grains (6)
,(6,8),(6,9),(6,10),(6,11),(6,12)
 -- Toppings (7) — produce, pickles, roasted veg, fruits
,(7,13),(7,14),(7,15),(7,16),(7,17),(7,18),(7,19),(7,20),(7,21),(7,22)
,(7,25),(7,27),(7,43),(7,44),(7,48),(7,49),(7,57)
,(7,66),(7,67),(7,68),(7,69),(7,70),(7,71),(7,72)
 -- Cheese (8)
,(8,30),(8,31),(8,32),(8,33),(8,34)
 -- Crunchies (9)
,(9,46),(9,50),(9,51),(9,52),(9,53),(9,54),(9,55),(9,56),(9,58),(9,61),(9,64),(9,65)
 -- Premiums (10) — avocado, tofu, bacon, eggs
,(10,23),(10,24),(10,35),(10,36),(10,41)
 -- Protein (11) — meat mains, marinated tofu, beans
,(11,37),(11,38),(11,39),(11,40),(11,42),(11,45),(11,47),(11,62)
 -- Dressing (12)
,(12,59),(12,60),(12,63),(12,74),(12,78)
,(12,80),(12,81),(12,82),(12,83),(12,84),(12,85),(12,86),(12,87),(12,88),(12,89)
,(12,90),(12,91),(12,92),(12,93),(12,94),(12,95),(12,96),(12,97),(12,98),(12,99)
 -- Finish (13) — small sprinkles: spices, herbs, lemon wedges, hot drips
,(13,26),(13,28),(13,29),(13,73),(13,75),(13,76),(13,77),(13,79)
 -- Packaging (14) — bread, bags, lids, utensils, etc. (every untagged item)
,(14,1),(14,2)
,(14,100),(14,101),(14,102),(14,103),(14,104),(14,105),(14,106),(14,107),(14,108),(14,109)
,(14,110),(14,111),(14,112),(14,113),(14,114),(14,115),(14,116),(14,117),(14,118),(14,119)
,(14,120),(14,121),(14,122),(14,123)
;

-- Template items per recipe-kind tag. Applied to a target recipe when its
-- format changes; items already in the recipe are skipped (no duplicates).
INSERT INTO tag_components (tag_id, child_ingredient, quantity) VALUES
 -- Salad
 (1, 113, 1)  -- Large Bowl
,(1, 114, 1)  -- Salad Dome Lid
,(1, 115, 1)  -- Ramekin and Lid
,(1, 116, 1)  -- Fork
,(1, 117, 1)  -- Napkin
,(1, 118, 1)  -- Small Bag
 -- Wrap (shell + packaging — the shell is Grains-tagged so it shows in
 -- the components list as a template-added row; packaging items get
 -- filtered out of the visual list but still factor into recipe cost.)
,(2, 9, 1)    -- Wheat Wrap XTRM (the wrap shell)
,(2, 121, 1)  -- Wrap Paper
,(2, 122, 1)  -- Sticker
,(2, 117, 1)  -- Napkin
 -- Bowl
,(3, 112, 1)  -- Bowl SugarCane compost
,(3, 110, 1)  -- 26 oz Lid
,(3, 116, 1)  -- Fork
,(3, 117, 1)  -- Napkin
 -- Catering
,(4, 103, 1)  -- 80 oz Catering Square
,(4, 105, 1)  -- CLR Lid
,(4, 106, 1)  -- 6" serving tongs
;

-- Wraps fit a smaller portion of greens than salads or bowls. Grains are
-- intentionally not scaled — the wrap shell itself sits in that category
-- and should stay at full quantity.
INSERT INTO tag_category_multipliers (tag_id, category_tag_id, multiplier) VALUES
 (2, 5, 0.3)  -- Wrap: Greens = 0.3
;

-- Each recipe gets one format tag, inferred from the existing
-- greens/grains portioning in Connections rather than the recipe name:
--   - Has 'Wheat Wrap XTRM' (id 9), or total base portions <= ~0.3 -> Wrap
--   - Total grains >= 0.5 and >= greens -> Bowl
--   - Otherwise -> Salad
INSERT INTO recipe_tags_mapping (tag_id, recipe_id) VALUES
 (1,1),(1,2),(1,3),(1,4),(1,5),(1,6),(2,7),(2,8),(3,9),(1,10)
,(3,11),(2,12),(3,13),(3,14),(3,15),(3,16),(1,17),(3,18),(2,19),(1,20)
,(2,21),(2,22),(3,23),(3,24),(3,25),(2,26),(2,27),(2,28)
;

-- Backfill from_template_tag_id on Connections rows whose ingredient is in
-- the recipe's current format's template. Without this, the seed wrap
-- recipes have their tortilla (and packaging) as plain manual rows: they
-- look like regular ingredients in the components list, and switching
-- away from Wrap doesn't remove them because the transition logic only
-- deletes provenance-marked rows. After this UPDATE, the seed matches
-- what newly Wrap-applied recipes look like, and round-tripping the
-- format cleans up correctly.
UPDATE Connections
SET from_template_tag_id = (
    SELECT rtm.tag_id FROM recipe_tags_mapping rtm
    WHERE rtm.recipe_id = Connections.ParentRecipe
    LIMIT 1
)
WHERE from_template_tag_id IS NULL
  AND ChildIngredient IS NOT NULL
  AND EXISTS (
      SELECT 1 FROM tag_components tc
      JOIN recipe_tags_mapping rtm ON rtm.tag_id = tc.tag_id
      WHERE rtm.recipe_id = Connections.ParentRecipe
        AND tc.child_ingredient = Connections.ChildIngredient
  );

INSERT INTO allergens (name, sortOrder) VALUES
('Meat',1),
('Coconut',2),
('Fish',3),
('Shellfish',4),
('Dairy',5),
('Eggs',6),
('Gluten',7),
('Tree Nuts',8),
('Peanuts',9),
('Soy',10),
('Sesame',11)
;

INSERT INTO ingredient_allergens (allergen_id, ingredient_id) VALUES
(7,9),
(5,30),
(5,31),
(5,32),
(5,33),
(5,34),
(6,35),
(1,36),
(1,37),
(1,38),
(1,39),
(3,39),
(5,41),
(6,41),
(10,42),
(7,50),
(7,51),
(7,52),
(11,52),
(8,54),
(9,54),
(10,54),
(8,56),
(5,58),
(7,58),
(8,58),
(9,58),
(10,58),
(11,60),
(7,62),
(10,63),
(5,64),
(7,64),
(8,65),
(3,74),
(11,77),
(5,79),
(7,79),
(8,79),
(9,79),
(11,79),
(3,81),
(5,81),
(6,81),
(5,83),
(5,85),
(6,85),
(10,88),
(11,88),
(8,89),
(10,89),
(5,90),
(6,90),
(7,91),
(10,91),
(11,91),
(2,94),
(3,94),
(4,94),
(3,96),
(5,96),
(6,96),
(2,97),
(4,97),
(2,98),
(4,98),
(10,99)
;

INSERT INTO ingredient_prices
    (ingredient_id, units_per_case, case_price, effective_date, notes)
VALUES
(3,31.310344827586206,13.43,'2025-07-23','COST / 4 LBS / 454 G / 100% yield')
,(4,72.06349206349206,43.19,'2025-07-23','COST / 10 LBS / 454 G / 100% yield')
,(5,86.47619047619048,32.45,'2025-07-23','COST / 12 LBS / 454 G / 100% yield')
,(6,33.583561643835615,23.7,'2025-07-23','COST / 12 LBS / 454 G / 90% yield')
,(7,44.077669902912625,28.23,'2025-07-23','COST / 4 LBS / 454 G / 100% yield')
,(8,263.95348837209303,19.85,'2025-07-23','COST / 25 LBS / 454 G / 300% yield')
,(9,0.12,37.93,'2025-07-23','COST / 72 EA')
,(10,225.1984126984127,57.2,'2025-07-23','COST / 25 LBS / 454 G / 250% yield')
,(11,90.8,39.95,'2025-07-23','COST/10/454')
,(12,122.04301075268818,33.91,'2025-07-23','COST / 25 LBS / 454 G / 200% yield')
,(13,70.87959183673469,18.78,'2025-07-23','COST / 9 lbs / 454 grams / 85% yield')
,(14,408.6,22.36,'2025-07-23','COST / 9 lbs / 454 grams / 90% yield')
,(16,742.9090909090909,29.66,'2025-07-23','COST / 10 lbs / 454 grams / 90% yield')
,(17,185.30612244897958,30.6,'2025-07-23','COST / 20 lbs / 454 grams')
,(18,172.7173913043478,33.94,'2025-07-23','COST / 25 lbs / 454 grams / 70% yield')
,(19,504.44444444444446,22.34,'2025-07-23','COST/20/454')
,(20,106.25531914893617,28.86,'2025-07-23','COST/11/454')
,(22,46.48960000000001,7.85,'2025-07-23','COST/3.2/454 - 80% yield')
,(26,48.0,4.21,'2025-07-23','COST / 2 lbs / 4 lemons / 6 wedges')
,(27,143.5225806451613,38.97,'2025-07-23','COST/10/98% yield/454')
,(29,1021.5,30.69,'2025-07-23','COST/60ct/3w.oz/28.35g')
,(30,238.94736842105263,9.22,'2025-07-23','COST / 20 lbs / 454 grams')
,(31,80.71111111111111,37.84,'2025-07-23','COST/8/454')
,(32,15.655172413793103,5.74,'2025-07-23','COST / 454 grams')
,(33,605.3333333333334,114.59,'2025-07-23','COST / 20 lbs / 454 grams')
,(34,227.0,53.61,'2025-07-23','COST/16/454')
,(35,144.0,60.32,'2025-07-23','COST /12 bags / 12 each')
,(36,302.6666666666667,65.48,'2025-07-23','COST / 10 lbs / 454 grams')
,(37,100.88888888888889,85.62,'2025-07-23','COST / 10/454 grams')
,(38,153.89830508474577,89.5,'2025-07-23','COST / 20 lbs / 454 grams')
,(39,68.78787878787878,55.29,'2025-07-23','COST+ BBQ sauce/10/454 g')
,(41,121.43132530120481,88.64,'2025-07-23','COST/22.2/454')
,(42,63.559999999999995,70.75,'2025-07-23','COST / 454 grams /98% yield')
,(43,181.6,44.42,'2025-07-23','COST / 20 lbs / 454 grams')
,(44,145.28,55.11,'2025-07-23','COST/8/454')
,(45,39.83413461538461,34.98,'2025-07-23','COST / 6 cans / 73 w.oz / 28.375 grams')
,(46,236.8695652173913,29.86,'2025-07-23','COST / 12 lbs / 454 grams')
,(47,282.89230769230767,34.98,'2025-07-23','COST/18388 g')
,(50,314.3076923076923,42.97,'2025-07-23','COST / 9 lbs / 454 grams')
,(51,324.2857142857143,52.96,'2025-07-23',NULL)
,(52,85.125,20.75,'2025-07-23','COST/1020 g')
,(53,238.94736842105263,30.96,'2025-07-23','COST / 10 lbs / 454 grams')
,(56,567.5,125.29,'2025-07-23','COST / 25 lbs / 454 grams')
,(57,8.333333333333334,20.71,'2025-07-23','COST / 12/550')
,(58,252.22222222222223,38.59,'2025-07-23','COST / 10 lbs / 454 grams')
,(59,146.41500000000002,30.3,'2025-07-23','COST/77.4/28.35')
,(60,63.41587301587302,33.71,'2025-07-23','COST / 8.8/454')
,(61,113.5,19.88,'2025-07-23','COST/ Pound / 454')
,(63,64.85714285714286,27.79,'2025-07-23','COST/4/454')
,(64,378.3333333333333,60.64,'2025-07-23','COST / 20 lbs / 454 grams')
,(65,133.52941176470588,38.06,'2025-07-23','COST/5/454')
,(66,388.17,107.6,'2025-07-23','COST/17.1/454')
,(67,388.17,82.03,'2025-07-23','COST / 17.1 lbs / 454 grams')
,(68,48.42666666666666,37.38,'2025-07-23',NULL)
,(69,37.06122448979592,12.86,'2025-07-23','COST/LBS/454')
,(70,119.47368421052632,64.09,'2025-07-23','COST/2251')
,(71,61.90909090909091,22.08,'2025-07-23','COST/4.5/454')
,(72,319.02702702702703,37.24,'2025-07-23','COST/26/454')
,(73,2724.0,109.52,'2025-07-23','COST / 15 lbs / 454 grams')
,(74,311.3142857142857,59.75,'2025-07-23','COST/4/128/28.35')
,(75,1225.8,61.73,'2025-07-23',NULL)
,(76,1037.7142857142858,75.08,'2025-07-23','COST/4/128/28.35')
,(78,64.85714285714286,27.13,'2025-07-23','COST/4/454')
,(79,728.5714285714287,22.95,'2025-07-23','COST/510 gram')
,(80,256.0,62.05,'2025-07-23','COST+ cilantro / 256 fluid ounces')
,(81,256.0,76.92,'2025-07-23','COST / 128 fluid ounces')
,(82,256.0,62.71,'2025-07-23','COST / 128 fluid ounces')
,(83,256.0,55.94,'2025-07-23','COST / 128 fluid ounces')
,(84,256.0,65.26,'2025-07-23','COST / 128 fluid ounces')
,(85,256.0,57.83,'2025-07-23','COST / 128 fluid ounces')
,(86,256.0,90.38,'2025-07-23',NULL)
,(87,256.0,61.48,'2025-07-23',NULL)
,(88,256.0,70.04,'2025-07-23',NULL)
,(89,256.0,53.9,'2025-07-23',NULL)
,(90,256.0,76.11,'2025-07-23',NULL)
,(91,256.0,69.15,'2025-07-23',NULL)
,(93,256.0,74.57,'2025-07-23',NULL)
,(84,256.0,65.26,'2025-07-23',NULL)
,(3,31.310344827586206,13.43,'2025-07-23',NULL)
,(4,72.06349206349206,43.19,'2025-07-23',NULL)
,(49,151.33333333333334,30,'2025-08-05',NULL)
,(54,126.11111111111111,29.32,'2025-08-05',NULL)
,(77,227.0,20.95,'2025-09-18',NULL)
,(27,358.80645161290323,31.75,'2025-09-18',NULL)
,(96,125.44,43.98,'2025-09-18',NULL)
,(9,72.0,37.93,'2025-09-18',NULL)
,(38,153.89830508474577,102.61,'2025-09-23',NULL)
,(37,100.88888888888889,82.67,'2025-09-23',NULL)
,(10,225.1984126984127,69.45,'2025-09-23',NULL)
,(44,145.28,58.37,'2025-09-23',NULL)
,(67,388.17,78.8,'2025-09-23',NULL)
,(72,319.02702702702703,38.1,'2025-09-23',NULL)
,(32,15.655172413793103,5.35,'2025-09-23',NULL)
,(34,227.0,52.9,'2025-09-23',NULL)
,(30,238.94736842105263,96.34,'2025-09-23',NULL)
,(50,314.3076923076923,43.41,'2025-09-23',NULL)
,(4,72.06349206349206,31.61,'2026-01-19',NULL)
,(119,200.0,194,'2026-01-19',NULL)
,(3,31.310344827586206,13.43,'2026-01-19',NULL)
,(6,33.583561643835615,23.85,'2026-01-19',NULL)
,(5,86.47619047619048,31.4,'2026-01-19',NULL)
,(7,44.077669902912625,24.93,'2026-01-19',NULL)
,(70,119.47368421052632,67.09,'2026-01-19',NULL)
,(13,70.87959183673469,22.78,'2026-01-19',NULL)
,(17,185.30612244897958,35.26,'2026-01-19',NULL)
,(14,408.6,58.84,'2026-01-19',NULL)
,(16,742.9090909090909,36.66,'2026-01-19',NULL)
,(18,172.7173913043478,29.94,'2026-01-19',NULL)
,(19,504.44444444444446,22.59,'2026-01-19',NULL)
,(21,64.85714285714286,4.82,'2026-01-19',NULL)
,(22,46.48960000000001,6.05,'2026-01-19',NULL)
,(27,358.80645161290323,35.19,'2026-01-19',NULL)
,(42,63.559999999999995,55.05,'2026-01-19',NULL)
,(24,120.0,31.95,'2026-01-19',NULL)
,(25,502.4266666666666,46.28,'2026-01-19',NULL)
,(29,1021.5,35.55,'2026-01-19',NULL)
,(79,728.5714285714287,21.85,'2026-01-19',NULL)
,(66,388.17,112.75,'2026-01-19',NULL)
,(9,72.0,40.87,'2026-01-19',NULL)
,(45,39.83413461538461,35.05,'2026-01-19',NULL)
,(20,106.25531914893617,31.35,'2026-01-19',NULL)
,(43,181.6,44.78,'2026-01-19',NULL)
,(44,145.28,59.12,'2026-01-19',NULL)
,(67,388.17,79.34,'2026-01-19',NULL)
,(72,319.02702702702703,39.49,'2026-01-19',NULL)
,(47,282.89230769230767,35.05,'2026-01-19',NULL)
,(49,151.33333333333334,61.01,'2026-01-19',NULL)
,(61,113.5,20.02,'2026-01-19',NULL)
,(57,100.0,26.49,'2026-01-19',NULL)
,(32,15.655172413793103,5.46,'2026-01-19',NULL)
,(34,227.0,45.03,'2026-01-19',NULL)
,(30,238.94736842105263,95.02,'2026-01-19',NULL)
,(33,605.3333333333334,113.06,'2026-01-19',NULL)
,(56,567.5,153.55,'2026-01-19',NULL)
,(50,314.3076923076923,43.05,'2026-01-19',NULL)
,(51,324.2857142857143,55.4,'2026-01-19',NULL)
,(64,378.3333333333333,62.6,'2026-01-19',NULL)
,(54,126.11111111111111,29.38,'2026-01-19',NULL)
,(58,252.22222222222223,38.75,'2026-01-19',NULL)
,(46,236.8695652173913,29.92,'2026-01-19',NULL)
,(36,302.6666666666667,66.17,'2026-01-19',NULL)
,(38,153.89830508474577,78.63,'2026-01-19',NULL)
,(35,144.0,49.12,'2026-01-19',NULL)
,(37,100.88888888888889,85.89,'2026-01-19',NULL)
,(39,68.78787878787878,55.29,'2026-01-19',NULL)
,(63,64.85714285714286,28.62,'2026-01-19',NULL)
,(59,146.41500000000002,31.16,'2026-01-19',NULL)
,(81,256.0,77.07,'2026-01-19',NULL)
,(83,256.0,56.06,'2026-01-19',NULL)
,(85,256.0,57.95,'2026-01-19',NULL)
,(80,256.0,62.17,'2026-01-19',NULL)
,(84,256.0,65.4,'2026-01-19',NULL)
,(82,256.0,62.84,'2026-01-19',NULL)
,(88,256.0,70.19,'2026-01-19',NULL)
,(90,256.0,76.63,'2026-01-19',NULL)
,(95,145.28,92.02,'2026-01-19',NULL)
,(94,72.64,45.6,'2026-01-19',NULL)
,(74,311.3142857142857,61.41,'2026-01-19',NULL)
,(76,1037.7142857142858,60.21,'2026-01-19',NULL)
,(60,63.41587301587302,33.79,'2026-01-19',NULL)
,(10,225.1984126984127,72.41,'2026-01-19',NULL)
,(12,122.04301075268818,34.13,'2026-01-19',NULL)
,(62,180.0,58.98,'2026-01-19',NULL)
,(15,385.9,38.05,'2026-01-20',NULL)
,(49,227.0,61.01,'2026-01-20',NULL)
,(23,102.79245283018868,39.44,'2026-01-20',NULL)
,(24,130.0,31.95,'2026-01-20',NULL)
,(97,250.88,67.9,'2026-01-20',NULL)
,(98,62.72,67.9,'2026-01-20',NULL)
,(98,71.1872,67.9,'2026-01-20',NULL)
,(97,250.88,64.2,'2026-01-20',NULL)
,(98,62.72,64.2,'2026-01-20',NULL)
,(99,256.0,47.53,'2026-01-20',NULL)
,(95,108.96,92.02,'2026-01-20',NULL)
,(28,83.5,14.54,'2026-01-20',NULL)
,(44,145.28,63.55,'2026-02-16',NULL)
,(67,388.17,78.8,'2026-02-16',NULL)
,(48,272.51349999999996,134,'2026-04-02',NULL)
,(55,135.9477777777778,50.27,'2026-04-02',NULL)
,(45,239.00480769230768,35.05,'2026-04-06',NULL)
,(14,408.6,26.86,'2026-04-06',NULL)
,(92,34.56,9.92,'2026-04-06',NULL)
,(48,272.51349999999996,101,'2026-04-10',NULL)
;