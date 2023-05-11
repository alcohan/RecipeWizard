# RecipeWizard

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Description
RecipeWizard is a tool designed to help chefs manage recipes and track nutrition & costing.

## Table of Contents
- [Installation](#installation)
- [Usage](#usage)
- [Features](#features)
- [Todo](#todo)
- [Contact](#contact)

## Installation
Unpack dist.zip into a folder of your choice, then run RecipeWizard.exe.
In order to use the Nutrition Label feature, ensure you have Google Chrome installed on the system.

## Usage
RecipeWizard considers two main types of objects: Ingredients and Recipes.
### Ingredients
Are the core building blocks of information.
Ingredients have a **unit** which represents the portion you might use this ingredient in. Nutrition and costing are entered on a per-unit basis, and ingredients are added to recipes in multiples of this unit.

Price history is tracked on each ingredient. Each price update may have a Supplier, Case Price, and Yield which represents the number of [unit]s that a case yields. 
Calculating this manually means we can easily update pricing using the Case Price.

### Recipes
Are collections of **components** which may be ingredients or other recipes. 

A recipe also has a unit and a yield quantity, e.g. a recipe for simple syrup may yield 3 Cups, or a recipe for a salad may yield 1 meal.
Recipes reflect the nutritional and costing totals from all of their components.

## Features
- Infinite nesting: Create as many sub-recipes as you like!
- Label Generator: with one button, create a nutrition label for your product. [Link to package](https://github.com/nutritionix/nutrition-label)
- Natural Language Search: quickly get nutrition data for any ingredient from the web
- Price tracking: Quickly update the prices of ingredients using the case price of wholesale items.
- Charts & breakdowns: View costing trends by ingredient or by recipe. View component breakdown to see what's contributing to the cost of a recipe.

## Todo
- Improved Unit system with conversion factors between common measures
- CSV import/export tools
- Scalable / printable export for multi-batching, e.g. 2x, 5x, 10x

## Contact
adu.cohan@gmail.com
