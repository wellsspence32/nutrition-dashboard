# Nutrition & Fitness Dashboard

Personal health dashboard built from Cronometer exports, published via GitHub Pages.

## Weekly update

1. Export 3 CSVs from Cronometer (Settings > Export Data, select All Time):
   - Daily Nutrition Summary
   - Exercises
   - Biometrics
2. Upload to the `data/` folder in this repo (replace old files)
3. GitHub Actions rebuilds the dashboard automatically (~60 sec)

## Dashboard URL

https://wellsspence32.github.io/nutrition-dashboard/

## Changing targets

Edit the `TARGETS` dict near the top of `build_dashboard.py`.

## Adding a hydrostatic test

Add a row to the `HYDROSTATIC` list in `build_dashboard.py`.
