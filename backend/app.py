from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.database import fetch_food_profiles, fetch_materials
from backend.recommender import rank_materials

app = FastAPI(title='OptiPAck Recommendation API', version='1.0.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


class RecommendationInput(BaseModel):
    foodName: str = Field(..., min_length=1)
    productType: str = Field(..., min_length=1)
    temperature: float = Field(..., ge=-50, le=100)
    ph: float = Field(..., ge=0, le=14)
    humidity: int = Field(..., ge=0, le=100)


GENERAL_PROFILES = {
    'Fresh produce': {'fragility': 7, 'respiration': 25, 'temperatureSensitivity': 7, 'handlingShock': 6, 'moistureSensitivity': 9, 'bulkDensity': 5},
    'Vegetable': {'fragility': 7, 'respiration': 28, 'temperatureSensitivity': 8, 'handlingShock': 6, 'moistureSensitivity': 10, 'bulkDensity': 5},
    'Fruit': {'fragility': 7, 'respiration': 20, 'temperatureSensitivity': 7, 'handlingShock': 7, 'moistureSensitivity': 8, 'bulkDensity': 6},
    'Dairy': {'fragility': 6, 'respiration': 0, 'temperatureSensitivity': 8, 'handlingShock': 5, 'moistureSensitivity': 7, 'bulkDensity': 6},
    'Seafood': {'fragility': 7, 'respiration': 0, 'temperatureSensitivity': 10, 'handlingShock': 7, 'moistureSensitivity': 8, 'bulkDensity': 5},
    'Meat': {'fragility': 7, 'respiration': 0, 'temperatureSensitivity': 9, 'handlingShock': 7, 'moistureSensitivity': 8, 'bulkDensity': 6},
    'Baked goods': {'fragility': 7, 'respiration': 0, 'temperatureSensitivity': 6, 'handlingShock': 8, 'moistureSensitivity': 5, 'bulkDensity': 6},
    'Dry snack': {'fragility': 3, 'respiration': 0, 'temperatureSensitivity': 3, 'handlingShock': 4, 'moistureSensitivity': 8, 'bulkDensity': 7},
    'Roasted food': {'fragility': 3, 'respiration': 0, 'temperatureSensitivity': 3, 'handlingShock': 4, 'moistureSensitivity': 9, 'bulkDensity': 7},
    'Frozen food': {'fragility': 6, 'respiration': 0, 'temperatureSensitivity': 10, 'handlingShock': 7, 'moistureSensitivity': 6, 'bulkDensity': 6},
    'Grains & pulses': {'fragility': 2, 'respiration': 0, 'temperatureSensitivity': 3, 'handlingShock': 4, 'moistureSensitivity': 7, 'bulkDensity': 8},
    'Beverage': {'fragility': 4, 'respiration': 0, 'temperatureSensitivity': 7, 'handlingShock': 5, 'moistureSensitivity': 5, 'bulkDensity': 7},
    'Other': {'fragility': 5, 'respiration': 0, 'temperatureSensitivity': 5, 'handlingShock': 5, 'moistureSensitivity': 6, 'bulkDensity': 5},
}

FOOD_NAME_HINTS = {
    'Fruit': ('apple', 'banana', 'berry', 'berries', 'citrus', 'grape', 'mango', 'melon', 'orange', 'pear', 'peach', 'plum', 'fruit'),
    'Vegetable': ('vegetable', 'vegetables', 'lettuce', 'spinach', 'cabbage', 'broccoli', 'carrot', 'cucumber', 'onion', 'pepper', 'tomato', 'potato', 'mushroom', 'greens', 'asparagus', 'cauliflower', 'peas', 'beans'),
    'Fresh produce': ('produce', 'fresh produce', 'salad', 'herbs', 'green beans', 'cucumber', 'tomato', 'avocado'),
    'Dairy': ('milk', 'cheese', 'yogurt', ' yoghurt', 'cream', 'butter'),
    'Seafood': ('fish', 'salmon', 'tuna', 'shrimp', 'prawn', 'crab', 'lobster', 'shellfish', 'seafood'),
    'Meat': ('beef', 'chicken', 'pork', 'lamb', 'turkey', 'duck', 'meat', 'sausage'),
    'Baked goods': ('cake', 'bread', 'pastry', 'croissant', 'cookie', 'biscuit', 'muffin', 'donut', 'doughnut', 'pie', 'bakery'),
    'Dry snack': ('snack', 'nuts', 'almond', 'cashew', 'peanut', 'cracker', 'popcorn', 'chips'),
    'Roasted food': ('coffee', 'roasted', 'cocoa'),
    'Frozen food': ('frozen', 'ice cream'),
    'Grains & pulses': ('grain', 'rice', 'wheat', 'oat', 'oats', 'barley', 'lentil', 'bean', 'beans', 'chickpea', 'pulse', 'flour', 'pasta'),
    'Beverage': ('juice', 'drink', 'beverage', 'tea', 'water', 'soda'),
}


def _resolve_food_profile(food_name: str, product_type: str, ph: float, humidity: int, food_profiles: list[dict]) -> dict:
    clean_name = food_name.strip().casefold()
    exact_food = next(
        (item for item in food_profiles if item['foodName'].strip().casefold() == clean_name),
        None,
    )
    if exact_food:
        profile = exact_food.copy()
        selected_category = product_type.strip()
        profile['productType'] = (
            profile['productType']
            if selected_category.casefold() == 'other'
            else selected_category
        )
        return profile

    category = product_type.strip()
    if category.casefold() == 'other':
        normalized_name = f' {clean_name.replace("-", " ").replace("_", " ")} '
        for candidate, hints in FOOD_NAME_HINTS.items():
            if any(f' {hint.strip()} ' in normalized_name for hint in hints):
                category = candidate
                break

    profile = GENERAL_PROFILES.get(category, GENERAL_PROFILES['Other'])
    return {
        'foodName': food_name.strip() or 'Custom product',
        'productType': category,
        'phMin': max(0.0, ph - 1.5),
        'phMax': min(14.0, ph + 1.5),
        'humidityRange': [max(0, humidity - 10), min(100, humidity + 10)],
        **profile,
    }


@app.get('/health')
def health() -> dict:
    return {'ok': True, 'database': 'sqlite', 'model': 'weighted_similarity'}


@app.get('/food-profiles')
def food_profiles() -> list[dict]:
    return fetch_food_profiles()


@app.get('/materials')
def materials() -> list[dict]:
    return fetch_materials()


@app.post('/recommend')
def recommend(payload: RecommendationInput) -> dict:
    food_profiles = fetch_food_profiles()
    material_catalog = fetch_materials()
    profile = _resolve_food_profile(
        payload.foodName,
        payload.productType,
        payload.ph,
        payload.humidity,
        food_profiles,
    )

    ranked = rank_materials(profile, payload.ph, payload.humidity, material_catalog, payload.temperature)
    winner = ranked[0]

    return {
        'foodName': payload.foodName,
        'productType': payload.productType,
        'temperature': payload.temperature,
        'ph': payload.ph,
        'humidity': payload.humidity,
        'profile': profile,
        'bestMaterial': winner,
        'top3': ranked,
        'summary': f"{winner['details']} This recommendation was optimized for {payload.foodName.lower()} under {profile['productType'].lower()} conditions at {payload.temperature:g} C and {payload.humidity}% humidity.",
    }


if __name__ == '__main__':
    import uvicorn

    uvicorn.run('backend.app:app', host='0.0.0.0', port=8000, reload=True)
