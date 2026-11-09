index.html is the main web UI.
User enters food/product details.
App shows the best packaging material and score.

material-details.html is the material info page.
Shows detailed performance, handling, and sustainability info for a selected packaging material.

server.js is the Node backend.
Serves the frontend.
Initializes SQLite.
Provides API endpoints for health, data fetching, and QR generation.

backend/app.py is the Python FastAPI backend.
Runs the packaging recommendation logic.
Accepts food conditions and returns top recommended materials.

backend/recommender.py is the smart scoring engine.
Compares food profile against material characteristics.
Ranks packaging options by weighted score.

backend/database.py handles SQLite data.
Creates tables.
Seeds initial food and material data.
Saves recommendation history.

data/food_profiles.json stores product profiles.

data/material_catalog.json stores available packaging materials.

data/packwise.db is the actual database file used at runtime.
