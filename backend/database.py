import json
import hashlib
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / 'data'
DB_PATH = DATA_DIR / 'packwise.db'

SCORE_TO_FEATURE = {
    'product_fragility_compatibility': 'Product fragility',
    'product_dimensions_compatibility': 'Product dimensions',
    'required_cushioning': 'Required cushioning',
    'material_suitability': 'Packaging material',
    'box_strength': 'Box strength required',
    'transportation_risk_suitability': 'Transportation risk',
    'moisture_resistance': 'Moisture sensitivity',
    'temperature_resistance': 'Temperature sensitivity',
    'handling_shock_resistance': 'Expected handling/shock',
    'packaging_cost': 'Packaging cost',
    'sustainability_recyclability': 'Sustainability/recyclability',
    'damage_risk_performance': 'Estimated damage risk',
    'packaging_dimensions_compatibility': 'Packaging dimensions',
    'otr_barrier': 'Oxygen transmission rate (OTR)',
    'wvtr_barrier': 'Water vapor transmission rate (WVTR)',
    'heat_sealability': 'Heat sealability',
    'biodegradability': 'Biodegradability',
}
FEATURE_TO_SCORE = {value: key for key, value in SCORE_TO_FEATURE.items()}
SCORE_KEYS = tuple(SCORE_TO_FEATURE)
DEFAULT_MATERIAL_SCORE = 50
MATERIAL_COLORS = {
    'Conventional Plastics': '#4a8ca4',
    'Paper': '#d7a44d',
    'Paperboard': '#b78a5f',
    'Metals': '#8f9196',
    'Glass': '#7ca3d0',
    'Bioplastics': '#67b66d',
    'Natural Polymers': '#82c7af',
    'Protein Materials': '#d89b5d',
    'Lipid Materials': '#a8b65d',
    'Composite Materials': '#8c6bb7',
    'Protective Materials': '#d7a263',
    'Edible Packaging': '#71b06a',
    'Active Packaging': '#8a7fd6',
    'Intelligent Packaging': '#9ba5d1',
    'Legacy': '#7aa86c',
}


def _infer_material_category(name: str) -> str:
    lowered = name.casefold()
    if any(term in lowered for term in ('metalized', 'metalised', 'aluminium', 'aluminum', 'tinplate', 'steel', 'foil')):
        return 'Metals'
    if any(term in lowered for term in ('paperboard', 'carton', 'corrugate', 'pulp tray', 'honeycomb')):
        return 'Paperboard'
    if 'glass' in lowered:
        return 'Glass'
    if any(term in lowered for term in ('paper', 'kraft', 'glassine', 'parchment')):
        return 'Paper'
    if any(term in lowered for term in ('foam', 'eps', 'epe', 'epp', 'polyurethane', 'eva')):
        return 'Protective Materials'
    if any(term in lowered for term in ('laminate', 'composite', 'vacuum skin', 'modified atmosphere')):
        return 'Composite Materials'
    if any(term in lowered for term in ('polyethylene', 'polypropylene', 'pet', 'pvc', 'polystyrene', 'nylon', 'evoh', 'pvdc', 'plastic', 'film', 'pouch', 'clamshell', 'tray')):
        return 'Conventional Plastics'
    return 'Legacy'


def _features_from_scores(scores: dict) -> dict:
    return {
        feature_name: float(scores.get(score_name, DEFAULT_MATERIAL_SCORE))
        for score_name, feature_name in SCORE_TO_FEATURE.items()
    }


def _scores_from_features(features: dict) -> dict:
    scores = {
        score_name: float(features.get(feature_name, DEFAULT_MATERIAL_SCORE))
        for score_name, feature_name in SCORE_TO_FEATURE.items()
    }
    return scores


def _expand_material_catalog() -> list[dict]:
    legacy_file = DATA_DIR / 'material_catalog.json'
    additions_file = DATA_DIR / 'material_catalog_additions.json'
    rows = []

    if legacy_file.exists():
        with legacy_file.open('r', encoding='utf-8') as fh:
            legacy_rows = json.load(fh)
        for index, row in enumerate(legacy_rows, start=1):
            rows.append({
                **row,
                'material_id': f'PKG-{index:04d}',
                'material_name': row.get('material_name') or row['name'],
                'material_category': row.get('material_category') or _infer_material_category(row['name']),
                'composition': row.get('composition') or row['name'],
                'development_status': row.get('development_status', 'Commercial'),
                'legacy_features': row.get('features', {}),
                'measurements': row.get('measurements', {
                    'otr': None,
                    'otr_unit': 'cc/m2/day',
                    'wvtr': None,
                    'wvtr_unit': 'g/m2/day',
                }),
                'food_contact_status': row.get('food_contact_status', 'Requires verification'),
                'recyclability': row.get('recyclability', 'Depends on local facilities'),
                'source_references': row.get('source_references', []),
            })

    if additions_file.exists():
        with additions_file.open('r', encoding='utf-8') as fh:
            catalog = json.load(fh)
        score_profiles = catalog.get('score_profiles', {})
        score_keys = catalog.get('score_keys', SCORE_KEYS)
        references = catalog.get('references', {})

        for row in catalog.get('materials', []):
            profile = score_profiles.get(row.get('score_profile'), {})
            if isinstance(profile, list):
                profile = dict(zip(score_keys, profile))
            scores = {**profile, **row.get('score_overrides', {})}
            sources = row.get('source_references')
            if sources is None:
                sources = [
                    reference
                    for reference_id in row.get('source_reference_ids', [])
                    for reference in references.get(reference_id, [])
                ]
            rows.append({
                **row,
                'scores': scores,
                'source_references': sources,
                'measurements': row.get('measurements', {
                    'otr': None,
                    'otr_unit': 'cc/m2/day',
                    'wvtr': None,
                    'wvtr_unit': 'g/m2/day',
                }),
            })

    expanded = []
    seen_names = set()
    for row in rows:
        material_name = str(row['material_name']).strip()
        if not material_name or material_name.casefold() in seen_names:
            continue
        seen_names.add(material_name.casefold())

        scores = {
            key: float(value)
            for key, value in row.get('scores', {}).items()
            if key in SCORE_TO_FEATURE
        }
        if row.get('legacy_features'):
            scores.update(_scores_from_features(row['legacy_features']))
        scores = {
            key: scores.get(key, float(row.get('score_overrides', {}).get(key, DEFAULT_MATERIAL_SCORE)))
            for key in SCORE_KEYS
        }
        category = row.get('material_category', 'Legacy')
        expanded.append({
            'material_id': row['material_id'],
            'material_name': material_name,
            'material_category': category,
            'composition': row.get('composition', material_name),
            'development_status': row.get('development_status', 'Commercial'),
            'scores': scores,
            'measurements': row['measurements'],
            'food_contact_status': row.get('food_contact_status', 'Requires verification'),
            'recyclability': row.get('recyclability', 'Depends on local facilities'),
            'source_references': row.get('source_references', []),
            'color': row.get('color', MATERIAL_COLORS.get(category, '#67b66d')),
            'details': row.get('details', row.get('composition', material_name)),
        })
    return expanded


def _seed_from_json(connection: sqlite3.Connection) -> None:
    food_file = DATA_DIR / 'food_profiles.json'
    if food_file.exists():
        with food_file.open('r', encoding='utf-8') as fh:
            food_rows = json.load(fh)
        for row in food_rows:
            connection.execute(
                """
                INSERT OR IGNORE INTO food_profiles (
                    foodName, productType, phMin, phMax, humidityRange,
                    fragility, respiration, temperatureSensitivity,
                    handlingShock, moistureSensitivity, bulkDensity
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row['foodName'],
                    row['productType'],
                    row['phMin'],
                    row['phMax'],
                    json.dumps(row.get('humidityRange', [0, 0])),
                    row.get('fragility', 0),
                    row.get('respiration', 0),
                    row.get('temperatureSensitivity', 0),
                    row.get('handlingShock', 0),
                    row.get('moistureSensitivity', 0),
                    row.get('bulkDensity', 0),
                ),
            )

    for row in _expand_material_catalog():
        features = _features_from_scores(row['scores'])
        values = (
            row['material_category'],
            row['composition'],
            row['development_status'],
            json.dumps(row['scores']),
            json.dumps(row['measurements']),
            row['food_contact_status'],
            row['recyclability'],
            json.dumps(row['source_references']),
        )
        existing = connection.execute(
            'SELECT material_id FROM material_catalog WHERE material_name = ?',
            (row['material_name'],),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE material_catalog SET material_category = ?, composition = ?,
                    development_status = ?, scores = ?, measurements = ?,
                    food_contact_status = ?, recyclability = ?, source_references = ?
                WHERE material_id = ?
                """,
                (*values, existing['material_id']),
            )
        else:
            connection.execute(
                """
                INSERT INTO material_catalog (
                    material_id, material_name, material_category, composition,
                    development_status, scores, measurements, food_contact_status,
                    recyclability, source_references
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(material_id) DO UPDATE SET
                    material_name = excluded.material_name,
                    material_category = excluded.material_category,
                    composition = excluded.composition,
                    development_status = excluded.development_status,
                    scores = excluded.scores,
                    measurements = excluded.measurements,
                    food_contact_status = excluded.food_contact_status,
                    recyclability = excluded.recyclability,
                    source_references = excluded.source_references
                """,
                (
                    row['material_id'],
                    row['material_name'],
                    *values,
                ),
            )
        updated = connection.execute(
            'UPDATE materials SET color = ?, details = ?, features = ? WHERE name = ?',
            (row['color'], row['details'], json.dumps(features), row['material_name']),
        )
        if updated.rowcount == 0:
            connection.execute(
                """
                INSERT OR IGNORE INTO materials (name, color, details, features)
                VALUES (?, ?, ?, ?)
                """,
                (row['material_name'], row['color'], row['details'], json.dumps(features)),
            )


def _migrate_legacy_materials(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT name, details, features FROM materials AS material
        WHERE id = (
            SELECT MIN(id) FROM materials WHERE name = material.name
        )
        """
    ).fetchall()
    for row in rows:
        material_name = row['name']
        features = json.loads(row['features'] or '{}')
        scores = _scores_from_features(features)
        existing = connection.execute(
            'SELECT material_id FROM material_catalog WHERE material_name = ?',
            (material_name,),
        ).fetchone()
        if existing:
            connection.execute(
                'UPDATE material_catalog SET scores = ? WHERE material_id = ?',
                (json.dumps(scores), existing['material_id']),
            )
            continue

        material_id = f'LEGACY-{hashlib.sha1(material_name.encode("utf-8")).hexdigest()[:12]}'
        category = _infer_material_category(material_name)
        connection.execute(
            """
            INSERT OR IGNORE INTO material_catalog (
                material_id, material_name, material_category, composition,
                development_status, scores, measurements, food_contact_status,
                recyclability, source_references
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                material_id,
                material_name,
                category,
                row['details'] or material_name,
                'Commercial',
                json.dumps(scores),
                json.dumps({
                    'otr': None,
                    'otr_unit': 'cc/m2/day',
                    'wvtr': None,
                    'wvtr_unit': 'g/m2/day',
                }),
                'Requires verification',
                'Depends on local facilities',
                '[]',
            ),
        )


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS food_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            foodName TEXT NOT NULL,
            productType TEXT NOT NULL,
            phMin REAL,
            phMax REAL,
            humidityRange TEXT,
            fragility INTEGER,
            respiration INTEGER,
            temperatureSensitivity INTEGER,
            handlingShock INTEGER,
            moistureSensitivity INTEGER,
            bulkDensity INTEGER,
            createdAt TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            color TEXT,
            details TEXT,
            features TEXT NOT NULL,
            createdAt TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS material_catalog (
            material_id TEXT PRIMARY KEY,
            material_name TEXT NOT NULL UNIQUE,
            material_category TEXT NOT NULL,
            composition TEXT NOT NULL,
            development_status TEXT NOT NULL,
            scores TEXT NOT NULL,
            measurements TEXT NOT NULL,
            food_contact_status TEXT NOT NULL,
            recyclability TEXT NOT NULL,
            source_references TEXT NOT NULL,
            createdAt TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _seed_from_json(connection)
    _migrate_legacy_materials(connection)

    vegetable_profile = {
        'foodName': 'Vegetable',
        'productType': 'Vegetable',
        'phMin': 4.0,
        'phMax': 7.0,
        'humidityRange': '[85, 98]',
        'fragility': 7,
        'respiration': 28,
        'temperatureSensitivity': 8,
        'handlingShock': 6,
        'moistureSensitivity': 10,
        'bulkDensity': 5,
    }
    connection.execute(
        """
        INSERT OR IGNORE INTO food_profiles (
            foodName, productType, phMin, phMax, humidityRange,
            fragility, respiration, temperatureSensitivity,
            handlingShock, moistureSensitivity, bulkDensity
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            vegetable_profile['foodName'],
            vegetable_profile['productType'],
            vegetable_profile['phMin'],
            vegetable_profile['phMax'],
            vegetable_profile['humidityRange'],
            vegetable_profile['fragility'],
            vegetable_profile['respiration'],
            vegetable_profile['temperatureSensitivity'],
            vegetable_profile['handlingShock'],
            vegetable_profile['moistureSensitivity'],
            vegetable_profile['bulkDensity'],
        ),
    )

    connection.commit()
    return connection


def fetch_food_profiles() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute('SELECT * FROM food_profiles ORDER BY id').fetchall()
        return [
            {
                'id': row['id'],
                'foodName': row['foodName'],
                'productType': row['productType'],
                'phMin': float(row['phMin'] or 0),
                'phMax': float(row['phMax'] or 0),
                'humidityRange': json.loads(row['humidityRange'] or '[0,0]'),
                'fragility': int(row['fragility'] or 0),
                'respiration': int(row['respiration'] or 0),
                'temperatureSensitivity': int(row['temperatureSensitivity'] or 0),
                'handlingShock': int(row['handlingShock'] or 0),
                'moistureSensitivity': int(row['moistureSensitivity'] or 0),
                'bulkDensity': int(row['bulkDensity'] or 0),
            }
            for row in rows
        ]

def fetch_materials() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute('SELECT * FROM material_catalog ORDER BY material_id').fetchall()
        materials = []
        for row in rows:
            scores = json.loads(row['scores'] or '{}')
            features = _features_from_scores(scores)
            materials.append({
                'id': row['material_id'],
                'material_id': row['material_id'],
                'material_name': row['material_name'],
                'material_category': row['material_category'],
                'composition': row['composition'],
                'development_status': row['development_status'],
                'scores': scores,
                'measurements': json.loads(row['measurements'] or '{}'),
                'food_contact_status': row['food_contact_status'],
                'recyclability': row['recyclability'],
                'source_references': json.loads(row['source_references'] or '[]'),
                'name': row['material_name'],
                'color': MATERIAL_COLORS.get(row['material_category'], '#67b66d'),
                'details': row['composition'],
                'features': features,
            })
        return materials
