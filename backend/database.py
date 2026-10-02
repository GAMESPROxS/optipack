import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / 'data'
DB_PATH = DATA_DIR / 'packwise.db'


def _seed_from_json(connection: sqlite3.Connection) -> None:
    food_file = DATA_DIR / 'food_profiles.json'
    material_file = DATA_DIR / 'material_catalog.json'

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

    if material_file.exists():
        with material_file.open('r', encoding='utf-8') as fh:
            material_rows = json.load(fh)
        for row in material_rows:
            connection.execute(
                """
                INSERT OR IGNORE INTO materials (name, color, details, features)
                VALUES (?, ?, ?, ?)
                """,
                (
                    row['name'],
                    row.get('color', '#67b66d'),
                    row.get('details', ''),
                    json.dumps(row.get('features', {})),
                ),
            )

    connection.commit()


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
        CREATE TABLE IF NOT EXISTS recommendation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            foodName TEXT NOT NULL,
            productType TEXT NOT NULL,
            temperatureC REAL NOT NULL,
            humidity INTEGER NOT NULL,
            ph REAL NOT NULL,
            packagingScore REAL NOT NULL,
            scoreComponents TEXT NOT NULL,
            materialName TEXT NOT NULL,
            createdAt TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    connection.execute('DELETE FROM food_profiles')
    connection.execute('DELETE FROM materials')
    _seed_from_json(connection)

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
        rows = connection.execute('SELECT * FROM materials ORDER BY id').fetchall()
        return [
            {
                'id': row['id'],
                'name': row['name'],
                'color': row['color'],
                'details': row['details'],
                'features': json.loads(row['features'] or '{}'),
            }
            for row in rows
        ]


def save_recommendation(payload: dict) -> dict:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO food_profiles (
                foodName, productType, phMin, phMax, humidityRange,
                fragility, respiration, temperatureSensitivity,
                handlingShock, moistureSensitivity, bulkDensity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload['foodName'],
                payload['productType'],
                payload['phMin'],
                payload['phMax'],
                json.dumps(payload.get('humidityRange', [0, 0])),
                payload.get('fragility', 0),
                payload.get('respiration', 0),
                payload.get('temperatureSensitivity', 0),
                payload.get('handlingShock', 0),
                payload.get('moistureSensitivity', 0),
                payload.get('bulkDensity', 0),
            ),
        )

        connection.execute(
            """
            INSERT OR REPLACE INTO materials (name, color, details, features)
            VALUES (?, ?, ?, ?)
            """,
            (
                payload['materialName'],
                payload.get('materialColor', '#67b66d'),
                payload.get('materialDetails', ''),
                json.dumps(payload.get('materialFeatures', {})),
            ),
        )
        history_cursor = connection.execute(
            """
            INSERT INTO recommendation_history (
                foodName, productType, temperatureC, humidity, ph,
                packagingScore, scoreComponents, materialName
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload['foodName'],
                payload['productType'],
                payload.get('temperature', 20),
                payload.get('humidity', 0),
                payload.get('phMin', 0) + 0.5,
                payload.get('packagingScore', 0),
                json.dumps(payload.get('scoreComponents', {})),
                payload['materialName'],
            ),
        )
        connection.commit()
        return {
            'recommendationId': history_cursor.lastrowid,
            'foodName': payload['foodName'],
            'productType': payload['productType'],
            'materialName': payload['materialName'],
        }
