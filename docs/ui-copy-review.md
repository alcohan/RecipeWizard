# UI copy review: proposed changes

**Status (Nov 6, 2026):** applied, in the app and on the canvas, with these exceptions:
- R10 is "Ctrl+Tab next tab · Ctrl+W close".
- I17 is "Printed in small type on recipe print-out".
- I20 is kept as it was.
- I21 is "No matches".

Rule applied: a label, hint or tooltip says only what the user needs at that moment. Cut how things work under the hood, what a link or button does when its label already says it, where else a feature lives, and shortcut reminders the menus already show. Keep wording that warns about consequences in confirmations (deleting, undoing, overwriting), shortened.

"—" means remove the text, or the whole widget when it's only a note. IDs are for approving or rejecting items ("all but R5, P8").

After approval, the same copy also goes onto the canvas artboards.

## Recipe tab

| # | Where | Now | Proposed |
|---|---|---|---|
| R1 | recipe_edit.py:527 Change photo tooltip | The photo shows in place of the wedge everywhere. | — |
| R2 | recipe_edit.py:530 Add photo tooltip | A photo shows in place of the wedge everywhere, printed pages included. You can also drop an image here. | Or drop an image here |
| R3 | recipe_edit.py:813 Archive button tooltip | Put it back on the menu / Take it off the menu: hidden from the Library and analytics, kept for later | Put back on the menu / Take off the menu |
| R4 | recipe_edit.py:816 menu chip | Archived · off the menu, tooltip "Hidden from the Library and analytics. Click to restore it." | Archived, tooltip "Click to restore" |
| R5 | recipe_edit.py:820–826 menu chip tooltips | Click to archive it (take it off the menu). / Set a menu price to see its food cost. Click to archive it (take it off the menu). | Click to take off the menu (both) |
| R6 | recipe_edit.py:832 sub-recipe chip tooltip | Used as a sub-recipe in {names}. Click to open one. | Used in {names} |
| R7 | recipe_edit.py:846 prices-changed chip tooltip | Supplier prices moved since this recipe was last saved. Save to confirm the new cost. | Save to confirm the new cost |
| R8 | recipe_edit.py:785 tag pill tooltip | Tag this recipe {tag}. Manage tags in Configure › Recipe tags. | — |
| R9 | recipe_edit.py:1031, portion_review.py:169 | Its unit isn’t a volume, so the rule can’t size it. (+ "Give it a unit like “3 cups” or move it to another category.") | Not a volume unit; size by hand |
| R10 | editor_tabs.py:326 tab strip hint | Ctrl+Tab next tab · Ctrl+W close · Ctrl+0 Library | — |
| R11 | template_summary.py:80 template line tooltip | Items this format adds to every recipe, and how it sizes portions. Edit in Configure › Formats & templates. | — |
| R12 | editor_results.py:203 | Set a menu price to see food cost | No menu price |
| R13 | recipe_component_add.py:420 | Not here? Create "x" as a new ingredient (Ctrl+Shift+N) | Create “x” as a new ingredient |
| R14 | format_segments.py:71 format tooltips | {Format}: applies the {Format} template / No format — e.g. a sub-recipe | — / Sub-recipe |

## New recipe dialog

| # | Where | Now | Proposed |
|---|---|---|---|
| N1 | recipe_create.py:127 header note | Opens in a new tab beside Library | — |
| N2 | recipe_create.py:226 footer note | Add components next with Ctrl+Enter | — |
| N3 | recipe_create.py:278 None card tooltip | No format: no template items, e.g. a dressing or sauce used in other recipes | For sub-recipes like dressings |
| N4 | recipe_create.py:304 None template note | No template: starts empty. For sub-recipes like dressings and sauces, which other recipes use. | Starts empty |
| N5 | recipe_create.py:357 duplicate name | There is already a recipe called “X”. You can still create this one. | A recipe called “X” already exists |

## Library and inspector

| # | Where | Now | Proposed |
|---|---|---|---|
| L1 | recipe_inspector.py:112 | Archived · off the menu, hidden from the Library and analytics | Archived |
| L2 | recipe_inspector.py:182 empty state | Select a recipe to see its cost, components, diets and allergens. | Select a recipe |
| L3 | recipe_inspector.py:262 | Archive (take off the menu) / Restore to the menu | Archive / Restore to menu |
| L4 | recipes_facet_pane.py:88 Include archived tooltip | Archived recipes are off the menu. Archive or restore one from its right-click menu or the inspector. | — |
| L5 | recipes_facet_pane.py:195 | The Needs review rule is still on. Click to turn it off. | Click to turn off |
| L6 | recipes_facet_pane.py:374 food cost filter, no prices | Set menu prices on recipes to filter by food cost. | No menu prices yet |
| L7 | recipes_tab.py:212 Group by tooltip | Gallery groups. A recipe with several tags or diets shows in each. | — |
| L8 | recipe_gallery.py:174 card pill tooltip | Costs have changed since this recipe was last saved. | — |

Kept: the Needs review tooltip (recipes_facet_pane.py:239). It defines what the view includes.

## Analytics and compare tray

| # | Where | Now | Proposed |
|---|---|---|---|
| A1 | analytics_tab.py:111 | None yet. Save comparison keeps this set and its settings. | None yet |
| A2 | analytics_tab.py:204 empty state | Add recipes with the box on the left, press Space on a recipe in the Library, or open a saved comparison. | Add recipes on the left, or press Space on one in the Library |
| A3 | analytics_tab.py:473 subtitle | The compare tray, expanded · N recipes | N recipes |
| A4 | analytics_tab.py:77 Dock tooltip | Back to Recipes with the compare tray docked (Ctrl+Shift+C) | Ctrl+Shift+C |
| A5 | analytics_tab.py:738 saved comparison tooltip | N recipes · right-click to update, rename or delete | N recipes |
| A6 | analytics_tab.py:687 card tooltip | Double-click to open · drag to reorder | — |
| A7 | compare_tray_dock.py:101 | N recipes · Space adds the selected recipe | N recipes |
| A8 | compare_tray_dock.py:105 empty tray | Select a recipe and press Space to add it here. | Press Space on a recipe to add it |
| A9 | compare_tray_dock.py:54 Print tooltip | Print a recipe page for each recipe in the tray | — |
| A10 | status_bar.py:62 tray chip tooltip | Show / hide the compare tray (Ctrl+Shift+C) | Ctrl+Shift+C |
| A11 | status_bar.py:138 update chip tooltip | See what’s new and download it | — |

## Ingredients, Edit and New ingredient

| # | Where | Now | Proposed |
|---|---|---|---|
| I1 | ingredient_inspector.py:143 empty state | Select an ingredient to see its price, usage and allergens. | Select an ingredient |
| I2 | ingredient_inspector.py:233 | No price yet. Add one with New price. | No price yet |
| I3 | ingredient_inspector.py:256 section label | USED IN N RECIPES · IMPACT OF THE CHANGE | USED IN N RECIPES · CHANGE |
| I4 | ingredients_tab.py:181 Import purchases tooltip | Update prices from a purchase history export (Ctrl+Shift+I) | Ctrl+Shift+I |
| I5 | ingredient_edit.py:277 | No price yet. It shows up in Library health under "No price" until you add one. | No price yet |
| I6 | ingredient_edit.py:292 USDA button tooltip | Find this ingredient in USDA FoodData Central and fill in its nutrition, scaled to this unit | — |
| I7 | ingredient_edit.py:389 footer | Used in N recipes — remove it from them to delete | — (disabled Delete button gets tooltip "Used in N recipes") |
| I8 | ingredient_edit.py:498 portion rule line | Portion rules: one unit = 24 f.oz (3 cups). Salad, Wrap, Bowl size this category by rule. | Sized by rule in Salad, Wrap, Bowl |
| I9 | ingredient_edit.py:501 | {reason}, so {formats} can’t size it by portion rule. Use a volume unit such as “3 cups” or “8 f.oz”. | Portion rules need a volume unit, like “3 cups” |
| I10 | ingredient_edit.py:524, ingredient_new.py:386 USDA note suffix | … Save to keep these values. / … Edit anything before saving. | (drop the suffix) |
| I11 | ingredient_edit.py:579 Used-in list | 9 more · links open the recipe in a tab | 9 more |
| I12 | ingredient_edit.py:567 recipe link tooltip | Close and open this recipe in a tab | — |
| I13 | ingredient_new.py:180 | Look it up in USDA, check the numbers, then save | — |
| I14 | ingredient_new.py:273 first price note | Optional. Skip it and the ingredient shows up in Library health under "No price". | Optional |
| I15 | ingredient_fields.py:111 allergen legend | Red = contains, dashed amber = facility. Click to cycle; right-click to choose. | Red = contains · dashed amber = facility |
| I16 | ingredient_fields.py:240 diet hint | Facility warnings only: no diet rules these out. | — (now wrong too: strict diets do rule them out) |
| I17 | ingredient_fields.py:295 statement note | Printed in small type under this ingredient on recipe pages. | — |
| I18 | ingredient_fields.py:290 statement placeholder | Paste the ingredients list from the manufacturer’s label | From the manufacturer’s label |
| I19 | usda_panel.py:300 | N results for "x" — lab-measured foods first, then branded products. | N results for “x” |
| I20 | usda_panel.py:255 | Using the shared demo key (30 lookups an hour). Add your own free key in Tools › Preferences. | Demo key: 30 lookups an hour. Add your own in Preferences. |
| I21 | usda_panel.py:308 | No USDA matches — try fewer or different words. | No matches. Try fewer words. |
| I22 | usda_panel.py:413 | Per 100 g (USDA basis). Enter the weight of 1 × {unit} to scale. | Per 100 g. Enter the weight of 1 × {unit} to scale. |
| I23 | bulk_image_assign.py:39 | Unassigned ingredients are listed first. Selections save immediately. | — |

## Purchase import, Vendor items, Import formats

| # | Where | Now | Proposed |
|---|---|---|---|
| P1 | import_purchases.py:557 weekly basis note | One price per ingredient per week (Mon–Sun): total spend ÷ total portions. This file gives up to N price points, dated … | N weeks: Oct 5, Oct 12, … |
| P2 | import_purchases.py:490 latest basis note | One price per ingredient, from its most recent purchase date, averaged across the locations that bought it that day. | Each item’s most recent purchase |
| P3 | import_purchases.py:632 locations note | Remembered with the import format. Prices are blended: total spend ÷ total units across the checked locations. | Prices blend the checked locations |
| P4 | import_purchases.py:703 swing hint | Blended case price with your checked locations, against all N. Ingredients move by the same % per portion. | Compared with all N locations |
| P5 | import_purchases.py:706 | All N locations are checked, so every price is blended across all of them. Uncheck a location to see which items it moves by 10% or more. | Uncheck a location to see what it changes |
| P6 | import_purchases.py:709 | Leaving these out moves no item’s price by 10% or more. | No item moves 10% or more |
| P7 | import_purchases.py:753 new items note | Only items never mapped or ignored land here. Each is mapped once; later imports price it automatically. | New items only. Each is mapped once. |
| P8 | import_purchases.py:1015 review note | Checked ingredients get the new prices when you apply; unchecked ones keep their current price. In the chart, the dashed line is the current price. | Only checked ingredients are updated |
| P9 | import_purchases.py:1123 first-price tooltip | This ingredient has no price yet; the import gives it its first one. | First price |
| P10 | import_purchases.py:550 overlap note | These dates overlap import #N. Weeks in both are replaced by this import’s prices; undoing it brings the earlier ones back. | Overlaps import #N. This import’s prices replace those weeks. |
| P11 | import_purchases.py:980 confirm | Ignore the N items not mapped yet? Ignored items are never priced; you can map them later in Configure › Vendor items. | Ignore N unmapped items? You can map them later in Vendor items. |
| P12 | import_purchases.py:1205 done note | You can also undo it later in Configure › Import formats & history. | Undo it anytime in Import formats & history |
| P13 | import_purchases.py:1248, import_formats_page.py:402 undo confirms | Undo import #N? Every price it wrote is removed; weeks it had replaced in earlier imports come back. Vendor item mappings stay. | Undo import #N? Its prices are removed; mappings stay. |
| P14 | import_purchases.py:1254 after undo | Its prices were removed. Your vendor item mappings were kept, so importing this file again goes straight to review. | Prices removed; mappings kept |
| P15 | vendor_items_page.py:46 page note | What each case on an invoice yields, in portions of an ingredient. Many vendor items can feed one ingredient. | — |
| P16 | vendor_items_page.py:299 | No imports have priced this item yet. | — (keep "Saving re-prices N imports…") |
| P17 | vendor_item_editor.py:124 | Pack size “88CT” was read as 88 ea. Change it if the case is packed differently. | Read “88CT” as 88 ea |
| P18 | vendor_item_editor.py:127 | Pack size “X” couldn’t be read; enter what a case holds (for cans, the drained weight). | Couldn’t read “X”. Enter what a case holds. |
| P19 | vendor_item_editor.py:193 | Pick an ingredient to work out portions per case. | Pick an ingredient |
| P20 | import_formats_page.py:269 list note | A format tells the importer which column is which. Files are matched to a format by their headers. | — |
| P21 | import_formats_page.py:292 history note | Undo removes every price an import wrote. Re-price applies today’s vendor item yields to it. | — |
| P22 | import_formats_page.py:170 columns note | Sample values from the last file imported with this format. Bold fields are required. | Bold = required |
| P23 | import_formats_page.py:107 | When the item code is blank, items are told apart by description + pack size. | — |

## Configure pages

| # | Where | Now | Proposed |
|---|---|---|---|
| C1 | allergens_page.py:51 | The order here is the order allergens appear everywhere. Drag to reorder; double-click to rename. Diets use them in Configure › Diets. | Drag to reorder |
| C2 | diets_page.py:55 | A recipe fits a diet when none of its ingredients have the excluded allergens and it meets the nutrient rule. Drag to reorder. Changes save as you make them. | — |
| C3 | diets_page.py:69 | Recipes with any of these anywhere in their ingredients don’t fit. | — |
| C4 | diets_page.py:79 strict note | With Strict on, a recipe whose ingredients are only “made in a facility that also handles” one of these allergens doesn’t fit either. Turn it off for diets where a trace is fine. | — (the checkbox label says it) |
| C5 | diets_page.py:85 | Per serving: one unit of the recipe’s yield. | Per serving |
| C6 | diets_page.py:308 delete confirm | Delete the diet “X”? Recipes stay as they are; saved views that filter by it stop narrowing by it. | Delete the diet “X”? |
| C7 | main_window.py:303, tags_manager.py:168 categories note | Categories color the wedge slices and group components in a recipe tab. Their order is the wedge order. Double-click a name to rename; click the swatch to pick a color. Changes save as you make them. | Order sets the wedge order |
| C8 | main_window.py:311, tags_manager.py:196 recipe tags note | Labels such as Core or Seasonal. A recipe can have several; assign them in a recipe tab. … | — |
| C9 | template_editor.py:167 | A format is a recipe tag with a shape, a color and a template. Changes save as you make them. | — |
| C10 | template_editor.py:341 portion rules note | How this format sizes a category. Shared base: the category’s ingredients split one amount. Each: every ingredient gets the amount. Categories without a rule are sized by hand. | Shared base: ingredients split one amount. Each: every ingredient gets it. |
| C11 | template_editor.py:485 | Added to every recipe tagged Salad; changes apply to its 11 recipes right away. | Added to 11 recipes |
| C12 | template_editor.py:331 / 582 empty states | No items yet. Add packaging or anything every recipe of this format includes. / No rules: every category in this format is sized by hand. | No items yet / No rules |
| C13 | template_editor.py:345 Check recipes tooltip | Recipes with portions sized by hand where a format has a rule | — |
| C14 | portion_tools_page.py:100 | Printed recipe pages name the tool for each ingredient. A sized tool is worked out again … (5 sentences) | — |
| C15 | portion_tools_page.py:110 | Portion text that names no tool, or whose tool doesn’t fit the unit. Linking sets … Text left unlinked prints only when the recipe uses exactly one unit. | Portion text that matches no tool |
| C16 | print_page.py:80 | How printed recipe pages look. Print a recipe from its tab, the Library’s right-click menu, Recipe › Print Recipe (Ctrl+P), or the compare tray. | — |
| C17 | print_page.py:40 logo note | SVG or PNG, printed about 20 pt tall at the top left. It’s kept in the data folder … | SVG or PNG |
| C18 | print_page.py:50 accent note | Colors the recipe name, the rule under the header and section labels. The allergen box always stays red. | — |
| C19 | print_page.py:74 disclaimer note | Printed in small italics above the footer on every page. Leave it blank to print none. | Leave blank for none |
| C20 | preferences.py:81 | Settings for this computer. Changes save as you make them. | — |
| C21 | preferences.py:92 food cost note | Recipes over the target are marked ▲ in amber on Library cards, in the inspector, Analytics and the recipe editor, and land in Needs review. Turn it off to show food cost without judging it. | Recipes over target get ▲ and appear in Needs review |
| C22 | preferences.py:46 USDA note | New ingredient looks up nutrition with the USDA FoodData Central API. Without a key it uses a shared demo key capped at 30 searches an hour. Get a free key at … and paste it below. | Without a key, a shared demo key allows 30 searches an hour. Get a free key at fdc.nal.usda.gov. |
| C23 | preferences.py:62 Test tooltip | Run a quick USDA search with the key above (doesn’t save it) | — |
| C24 | preferences.py:128 | This is RecipeWizard v0.0.4. Help › Check for Updates… checks any time. | Version 0.0.4 |
| C25 | preferences.py:174 | The shared demo key works. Paste your own for more searches. | Demo key works |
| C26 | library_health_tab.py:94 | Data-quality signals, worst first. Address each when you have a moment. | — |
| C27 | library_health_tab.py:32–38 card notes | Ingredients with no calories recorded. USDA search fills these in automatically. / No supplier price newer than 90 days — add a current price or confirm the latest. / Not referenced by any recipe. Candidates for cleanup if intentionally retired. | No calories recorded / No price in 90 days / Not in any recipe |
| C28 | library_health_tab.py:239 | No backup files yet — Tools > Back Up Library Now makes one. | No backups yet |
| C29 | main_window.py:337 / 349 launcher notes (Data & backups, Images) | Back up the whole library to a single file … / Match ingredient photos in the data folder … | — (both pages are due a redesign) |

## Dialogs and confirmations

| # | Where | Now | Proposed |
|---|---|---|---|
| D1 | backup_restore.py:40 | Recipes, ingredients, prices, suppliers and settings go into one .rwbackup file. | — |
| D2 | backup_restore.py:48 | Photos make the file much larger. Without them, a restore keeps the photos already on that computer. | Without photos, a restore keeps the ones already there |
| D3 | backup_restore.py:146 Overwrite note | Your library is replaced by the backup, and photos with the same name are replaced by the backup’s. | Replaces your library with the backup |
| D4 | backup_restore.py:151 Merge note | Adds what the backup has that this library doesn't; nothing here is changed or deleted. Anything with the same name (…) keeps your current version, and the summary lists what was kept. Price history … | Adds what’s missing. Anything with the same name keeps your version. |
| D5 | backup_restore.py:167 safety note | Saved to the data folder. Untick this on a new install, where there's only the sample data to lose. | — |
| D6 | archive_confirm.py:18 | It comes off the menu and is hidden from the Library and analytics. You can restore it later, or undo with Ctrl+Z. | You can restore it later |
| D7 | update.py:94 | Back up your library before installing X? Your recipes stay where they are, but the new version upgrades the database the first time it opens. A backup lets you go back. | Back up your library before installing X? The update upgrades it when it first opens. |
| D8 | update.py:109 | RecipeWizard X is downloaded and verified. Restart now to finish installing? You'll be asked to save any open edits. | X is ready. Restart now to install? |
| D9 | portion_review.py:62–66 intro | (first run) Portion multipliers are now portion rules. These recipes have ingredients sized by hand that differ from their format’s rule; nothing has changed yet. Tick the ones to bring onto the rules; the rest stay as they are. A base keeps its current split. | These recipes size some ingredients by hand where their format has a rule. Tick the ones to bring onto the rules. |

Kept as they are: the sub-recipe archive warning (archive_confirm.py:27–30), Reset Database / Reset With Sample Data, the overwrite-restore confirmation, and validation messages. They're already short, or they state a consequence that matters.
