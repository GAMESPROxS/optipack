from __future__ import annotations

from typing import Any


SCORE_WEIGHTS = {
    'Food': 0.22,
    'Product Type': 0.18,
    'Temperature': 0.14,
    'Humidity': 0.10,
    'pH': 0.05,
    'OTR': 0.10,
    'WVTR': 0.09,
    'Heat Sealability': 0.06,
    'Biodegradability': 0.06,
}

PRODUCT_TYPE_RULES = {
    'fresh produce': (('breathable', 'perforated', 'modified atmosphere'), ('tray', 'pulp'), ('vacuum',)),
    'vegetable': (('breathable', 'perforated', 'modified atmosphere', 'vented'), ('tray', 'pulp', 'film'), ('vacuum',)),
    'fruit': (('tray', 'pulp', 'foam', 'clamshell'), ('perforated', 'breathable'), ('vacuum',)),
    'dairy': (('pet tray', 'lidding', 'vacuum', 'tray'), ('barrier', 'laminate', 'pouch'), ('breathable',)),
    'seafood': (('vacuum', 'barrier', 'laminate'), ('tray', 'pouch'), ('breathable',)),
    'meat': (('vacuum', 'barrier', 'laminate'), ('tray', 'pouch'), ('breathable',)),
    'baked goods': (('paperboard', 'carton', 'pulp', 'corrugate'), ('pouch', 'film'), ('vacuum',)),
    'dry snack': (('pouch', 'laminate', 'carton', 'paperboard'), ('barrier', 'film'), ('breathable',)),
    'roasted food': (('metalized', 'pouch', 'laminate'), ('barrier', 'carton'), ('breathable',)),
    'frozen food': (('vacuum', 'barrier', 'laminate', 'tray'), ('carton', 'paperboard'), ('breathable',)),
    'grains & pulses': (('pouch', 'barrier', 'paperboard', 'carton'), ('laminate', 'film'), ('breathable',)),
    'beverage': (('bottle', 'pet', 'carton', 'aseptic'), ('pouch',), ()),
}


def clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _feature_fit(material: dict[str, Any], targets: dict[str, float]) -> float:
    features = material.get('features') or {}
    matches = [
        100 - abs(float(features.get(key, 60)) - target)
        for key, target in targets.items()
    ]
    return clamp(sum(matches) / max(1, len(matches)))


def _product_type_fit(product_type: str, material_name: str) -> float:
    rules = PRODUCT_TYPE_RULES.get(product_type.lower())
    if not rules:
        return 65.0

    preferred, suitable, unsuitable = rules
    if any(term in material_name for term in preferred):
        return 95.0
    if any(term in material_name for term in unsuitable):
        return 45.0
    if any(term in material_name for term in suitable):
        return 80.0
    return 65.0


def _score_material_components(
    material: dict[str, Any],
    food_profile: dict[str, Any],
    ph: float,
    humidity: int,
    temperature: float,
) -> dict[str, float]:
    features = material.get('features') or {}
    material_name = str(material.get('name', '')).lower()
    product_type = str(food_profile.get('productType', 'Other'))
    fragility = float(food_profile.get('fragility', 5))
    handling_shock = float(food_profile.get('handlingShock', 5))
    temperature_sensitivity = float(food_profile.get('temperatureSensitivity', 5))
    moisture_sensitivity = float(food_profile.get('moistureSensitivity', 5))
    bulk_density = float(food_profile.get('bulkDensity', 5))
    respiration = float(food_profile.get('respiration', 0))

    food_score = _feature_fit(material, {
        'Product fragility': clamp(42 + fragility * 6),
        'Required cushioning': clamp(28 + fragility * 6),
        'Box strength required': clamp(30 + fragility * 5),
        'Expected handling/shock': clamp(26 + handling_shock * 7 + fragility * 3),
        'Estimated damage risk': clamp(20 + fragility * 4 + moisture_sensitivity * 2),
        'Product dimensions': clamp(40 + bulk_density * 5),
    })

    temperature_target = clamp(50 + abs(float(temperature) - 5) * 1.5 + temperature_sensitivity * 1.5)
    temperature_score = clamp(100 - abs(float(features.get('Temperature sensitivity', 60)) - temperature_target))

    humidity_target = clamp(35 + humidity * 0.35 + moisture_sensitivity * 2.5)
    humidity_score = clamp(100 - abs(float(features.get('Moisture sensitivity', 60)) - humidity_target))

    oxygen_target = clamp(35 + respiration * 0.8 + temperature_sensitivity * 0.8)
    if product_type.lower() in {'fresh produce', 'fruit', 'meat', 'seafood'}:
        oxygen_target += 10
    if any(term in material_name for term in ('paperboard', 'pulp', 'carton', 'corrugate')):
        oxygen_target -= 12
    oxygen_score = clamp(100 - abs(float(features.get('Oxygen transmission rate (OTR)', 60)) - oxygen_target))

    wvtr_target = clamp(30 + humidity * 0.4 + moisture_sensitivity * 2.0)
    if product_type.lower() in {'fresh produce', 'fruit', 'dairy'}:
        wvtr_target += 8
    if any(term in material_name for term in ('barrier', 'laminate', 'vacuum', 'film', 'pouch')):
        wvtr_target -= 10
    wvtr_score = clamp(100 - abs(float(features.get('Water vapor transmission rate (WVTR)', 60)) - wvtr_target))

    seal_target = 75 if any(term in material_name for term in ('pouch', 'laminate', 'film', 'vacuum', 'lidding', 'bag')) else 62
    if product_type.lower() in {'dairy', 'seafood', 'meat', 'frozen food', 'beverage'}:
        seal_target += 8
    heat_seal_score = clamp(100 - abs(float(features.get('Heat sealability', 60)) - seal_target))

    biodegradability_target = 78 if any(term in material_name for term in ('paperboard', 'pulp', 'carton', 'corrugate', 'cellulose')) else 58
    if any(term in material_name for term in ('barrier', 'laminate', 'metalized', 'vacuum', 'pet')):
        biodegradability_target -= 15
    biodegradability_score = clamp(100 - abs(float(features.get('Biodegradability', 60)) - biodegradability_target))

    ph_score = float(features.get('Packaging material', 60))
    chemistry_load = max(0.0, 5.5 - ph, ph - 8.0)
    if chemistry_load:
        if any(term in material_name for term in ('barrier', 'laminate', 'pouch', 'pet', 'tray', 'vacuum', 'film')):
            ph_score += min(15, chemistry_load * 4)
        elif any(term in material_name for term in ('paperboard', 'pulp', 'corrugate', 'carton')):
            ph_score -= min(20, chemistry_load * 5)
    ph_score = clamp(ph_score)

    return {
        'Food': food_score,
        'Product Type': _product_type_fit(product_type, material_name),
        'Temperature': temperature_score,
        'Humidity': humidity_score,
        'pH': ph_score,
        'OTR': oxygen_score,
        'WVTR': wvtr_score,
        'Heat Sealability': heat_seal_score,
        'Biodegradability': biodegradability_score,
    }


def score_material(
    material: dict[str, Any],
    food_profile: dict[str, Any],
    ph: float,
    humidity: int,
    temperature: float = 20.0,
) -> tuple[float, str]:
    components = _score_material_components(material, food_profile, ph, humidity, temperature)
    total = sum(components[name] * weight for name, weight in SCORE_WEIGHTS.items())
    return round(total, 1), material.get('name', '')


def rank_materials(
    food_profile: dict[str, Any],
    ph: float,
    humidity: int,
    materials: list[dict[str, Any]],
    temperature: float = 20.0,
) -> list[dict[str, Any]]:
    ranked = []
    for material in materials:
        components = _score_material_components(material, food_profile, ph, humidity, temperature)
        score = sum(components[name] * weight for name, weight in SCORE_WEIGHTS.items())
        ranked.append({
            'name': material.get('name', ''),
            'score': round(score, 1),
            'components': {name: round(value, 1) for name, value in components.items()},
            'details': material.get('details', 'Optimized packaging solution.'),
            'color': material.get('color', '#67b66d'),
            'features': material.get('features', {}),
        })

    ranked.sort(
        key=lambda item: (
            item['score'],
            (item['components'].get('OTR', 0) + item['components'].get('WVTR', 0)) / 2,
            item['features'].get('Packaging cost', 0),
            item['features'].get(
                'Sustainability/recyclability',
                item['features'].get('Biodegradability', 0),
            ),
        ),
        reverse=True,
    )
    return ranked[:3]
