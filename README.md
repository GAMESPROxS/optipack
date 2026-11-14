index.html is the main web UI.
User enters food/product details.
App shows the best packaging material and score.

material-details.html is the material info page.
Shows detailed performance, handling, and sustainability info for a selected packaging material.

traceability.html displays saved recommendation records.

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

To run the database-backed web application:
1. Run `npm install`.
2. Run `npm start`.
3. Open `http://localhost:3000`.

The web UI loads food profiles and materials through the Node `/api` endpoints, scores recommendations from the loaded material catalog, and saves traceability records to SQLite. The standalone Python API is not required to run the web UI.
