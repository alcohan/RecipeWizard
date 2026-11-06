# RecipeWizard

Recipe costing and nutrition for restaurant kitchens. Build recipes from your ingredients, keep prices current from your purchase history, and print recipe pages with nutrition labels, allergens and portion guides.

Windows desktop app · Python 3.12 · PySide6 · SQLite

## Download

Get **RecipeWizard.exe** from the [latest release](https://github.com/alcohan/RecipeWizard/releases) and run it. There's no installer. Your library is created on first run, and **Help › Check for Updates** installs new versions in place.

## What it does

**Recipes**
- A library of every recipe, as a gallery or a table, with filters by format, tag, allergen and diet. You can save views, including their grouping and sort order.
- Open recipes in tabs side by side. Each recipe shows its live cost, food-cost % against the menu price, nutrition and allergens.
- Recipes can include other recipes (dressings, sauces, bases), nested as deep as you like.
- **Formats** (Salad, Wrap, Bowl…) add their packaging and other standard items automatically and set portion rules.
- **Cost over time** charts how a recipe's cost moved with ingredient prices and shows which ingredients drove the change.

**Ingredients and prices**
- Nutrition comes from a USDA FoodData Central lookup or is entered by hand. Ingredients also carry allergens, a package ingredient statement and a photo.
- Prices are entered as case price × what a case yields, so updating one is a single number.
- **Import purchases** reads your distributor's purchase-history CSV. It matches vendor items to ingredients and turns purchases into dated prices.

**Output**
- A Nutrition Facts label for any recipe, to copy or save as an image. Values are rounded the way labels round them.
- Printed recipe pages with ingredients, nutrition, allergens and a portion-scoop key, plus your logo and colors. A second version leaves out portions and amounts.
- **Analytics** compares recipes side by side by cost, calories or any macro, per serving, per 100 g or per dollar of menu price. Comparisons can be saved and exported to CSV.

**Upkeep**
- **Library health** lists what needs fixing: missing nutrition, stale prices and duplicate names. It only checks ingredients used in active recipes, and each ingredient category decides which checks apply.
- Back up and restore the whole library, photos included, in one file.
- **Ctrl+K** jumps to any recipe, ingredient or command. Search ignores accents and forgives small typos.

## How costing works

Every ingredient has a **unit**: the portion you use it in (1 oz, 1 each, 1/6 wedge). Nutrition and cost are per unit, and recipes use ingredients in multiples of that unit.

A **price** is a case price and how many units a case yields:

```
$42.00 case ÷ 120 portions = $0.350 per unit
```

A **recipe** has a yield (3 cups of syrup, 1 salad) and adds up the cost and nutrition of its components, including those inside any sub-recipes.

## Your data

Everything lives in one folder:

```
%APPDATA%\AdrianCohan\RecipeWizard\
  builder.db      the library (SQLite)
  ingredients\    ingredient photos
  recipes\        recipe photos
  branding\       print logo
```

**Tools › Open Data Folder** opens it. Backups (`.rwbackup`) are saved there by default.

## Run from source

```bash
git clone https://github.com/alcohan/RecipeWizard.git
cd RecipeWizard
pip install -r requirements.txt
python app.py
```

Optional settings, as environment variables or in a `.env` file next to `app.py`:

| Variable | Use |
|---|---|
| `USDA_API_KEY` | Your [FoodData Central key](https://fdc.nal.usda.gov/api-key-signup). Without one the shared demo key is used. A key can also be set in Configure › Preferences. |
| `RECIPEWIZARD_DB` | Use a different library file, for example a scratch copy |

Run the tests with:

```bash
pip install pytest
python -m pytest
```

## Releases

Pushing a `vX.Y.Z` tag runs the [release workflow](.github/workflows/release.yml). It sets the version, builds `RecipeWizard.exe` with PyInstaller, and publishes it with its SHA-256 checksum as a GitHub pre-release.

## Contact

adu.cohan@gmail.com
