const express = require('express');
const fs = require('fs');
const path = require('path');
const initSqlJs = require('sql.js');

const app = express();
const port = process.env.PORT || 3000;
const rootDir = __dirname;
const dataDir = path.join(rootDir, 'data');
const dbPath = path.join(dataDir, 'packwise.db');

if (!fs.existsSync(dataDir)) {
  fs.mkdirSync(dataDir, { recursive: true });
}

let sqlModule;
let db;

function saveDatabase() {
  if (!db) return;
  const binary = Buffer.from(db.export());
  fs.writeFileSync(dbPath, binary);
}

function fetchRows(sql, params = []) {
  if (!db) return [];
  const statement = db.prepare(sql);
  const rows = [];

  if (params.length) {
    statement.bind(params);
  }

  while (statement.step()) {
    rows.push(statement.getAsObject());
  }

  statement.free();
  return rows;
}

function rowToFood(row) {
  return {
    id: row.id,
    foodName: row.foodName,
    productType: row.productType,
    phMin: Number(row.phMin),
    phMax: Number(row.phMax),
    humidityRange: JSON.parse(row.humidityRange || '[0, 0]'),
    fragility: Number(row.fragility),
    respiration: Number(row.respiration),
    temperatureSensitivity: Number(row.temperatureSensitivity),
    handlingShock: Number(row.handlingShock),
    moistureSensitivity: Number(row.moistureSensitivity),
    bulkDensity: Number(row.bulkDensity)
  };
}

function rowToMaterial(row) {
  return {
    id: row.id,
    name: row.name,
    color: row.color,
    details: row.details,
    features: JSON.parse(row.features || '{}')
  };
}

function readSeedJson(fileName) {
  const fullPath = path.join(dataDir, fileName);
  if (!fs.existsSync(fullPath)) {
    return [];
  }

  const content = fs.readFileSync(fullPath, 'utf8');
  return JSON.parse(content);
}

async function initializeDatabase() {
  sqlModule = await initSqlJs({
    locateFile: (file) => require.resolve(`sql.js/dist/${file}`)
  });

  const fileData = fs.existsSync(dbPath) ? fs.readFileSync(dbPath) : null;
  db = new sqlModule.Database(fileData || undefined);

  db.run(`
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
    );

    CREATE TABLE IF NOT EXISTS materials (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      color TEXT,
      details TEXT,
      features TEXT NOT NULL,
      createdAt TEXT DEFAULT CURRENT_TIMESTAMP
    );
  `);

  const foodCount = db.exec('SELECT COUNT(*) AS count FROM food_profiles')[0]?.values[0][0] || 0;
  if (Number(foodCount) === 0) {
    const seedFoods = readSeedJson('food_profiles.json');
    for (const item of seedFoods) {
      db.run(
        `INSERT INTO food_profiles (foodName, productType, phMin, phMax, humidityRange, fragility, respiration, temperatureSensitivity, handlingShock, moistureSensitivity, bulkDensity)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          item.foodName,
          item.productType,
          item.phMin,
          item.phMax,
          JSON.stringify(item.humidityRange || [0, 0]),
          item.fragility,
          item.respiration,
          item.temperatureSensitivity,
          item.handlingShock,
          item.moistureSensitivity,
          item.bulkDensity
        ]
      );
    }
  }

  const materialCount = db.exec('SELECT COUNT(*) AS count FROM materials')[0]?.values[0][0] || 0;
  if (Number(materialCount) === 0) {
    const seedMaterials = readSeedJson('material_catalog.json');
    for (const item of seedMaterials) {
      db.run(
        `INSERT INTO materials (name, color, details, features)
         VALUES (?, ?, ?, ?)`,
        [item.name, item.color || '#67b66d', item.details, JSON.stringify(item.features || {})]
      );
    }
  }

  saveDatabase();
}

app.use(express.json());
app.use(express.static(rootDir));

app.get('/api/health', (req, res) => {
  res.json({ ok: true, database: 'sqlite' });
});

app.get('/api/food-profiles', (req, res) => {
  const rows = fetchRows('SELECT * FROM food_profiles ORDER BY id');
  res.json(rows.map(rowToFood));
});

app.get('/api/materials', (req, res) => {
  const rows = fetchRows('SELECT * FROM materials ORDER BY id');
  res.json(rows.map(rowToMaterial));
});

app.post('/api/food-profiles', (req, res) => {
  const { foodName, productType, ph, humidity } = req.body || {};

  if (!foodName || !productType) {
    return res.status(400).json({ error: 'Food name and product type are required.' });
  }

  const phValue = Number(ph || 0);
  const humidityValue = Number(humidity || 0);

  const profile = {
    foodName: String(foodName).trim(),
    productType: String(productType).trim(),
    phMin: Math.min(3.5, Math.max(0, phValue - 0.5)),
    phMax: Math.max(7.5, phValue + 0.5),
    humidityRange: JSON.stringify([Math.max(10, humidityValue - 8), Math.min(100, humidityValue + 8)]),
    fragility: 6,
    respiration: 12,
    temperatureSensitivity: 6,
    handlingShock: 5,
    moistureSensitivity: 7,
    bulkDensity: 6
  };

  db.run(
    `INSERT INTO food_profiles (foodName, productType, phMin, phMax, humidityRange, fragility, respiration, temperatureSensitivity, handlingShock, moistureSensitivity, bulkDensity)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      profile.foodName,
      profile.productType,
      profile.phMin,
      profile.phMax,
      profile.humidityRange,
      profile.fragility,
      profile.respiration,
      profile.temperatureSensitivity,
      profile.handlingShock,
      profile.moistureSensitivity,
      profile.bulkDensity
    ]
  );

  saveDatabase();

  const id = db.exec('SELECT last_insert_rowid() AS id')[0].values[0][0];
  const saved = fetchRows('SELECT * FROM food_profiles WHERE id = ?', [id]).shift();
  return res.status(201).json(rowToFood(saved));
});

app.post('/api/materials', (req, res) => {
  const { materialName, details, color } = req.body || {};

  if (!materialName || !details) {
    return res.status(400).json({ error: 'Material name and details are required.' });
  }

  const features = {
    'Product fragility': 80,
    'Product dimensions': 78,
    'Required cushioning': 74,
    'Packaging material': 82,
    'Box strength required': 72,
    'Transportation risk': 74,
    'Moisture sensitivity': 79,
    'Temperature sensitivity': 76,
    'Expected handling/shock': 75,
    'Packaging cost': 70,
    'Sustainability/recyclability': 73,
    'Estimated damage risk': 75,
    'Packaging dimensions': 81
  };

  db.run(
    `INSERT INTO materials (name, color, details, features)
     VALUES (?, ?, ?, ?)`,
    [String(materialName).trim(), color || '#67b66d', String(details).trim(), JSON.stringify(features)]
  );

  saveDatabase();

  const id = db.exec('SELECT last_insert_rowid() AS id')[0].values[0][0];
  const saved = fetchRows('SELECT * FROM materials WHERE id = ?', [id]).shift();
  return res.status(201).json(rowToMaterial(saved));
});

app.post('/api/save-record', (req, res) => {
  const { foodName, productType, ph, humidity, materialName, materialDetails, color, features } = req.body || {};

  if (!foodName || !productType || !materialName) {
    return res.status(400).json({ error: 'Food name, product type and material name are required.' });
  }

  const foodRows = fetchRows('SELECT * FROM food_profiles WHERE foodName = ? AND productType = ?', [String(foodName).trim(), String(productType).trim()]);
  const phValue = Number(ph || 0);
  const humidityValue = Number(humidity || 0);
  const profileValues = [
    String(foodName).trim(),
    String(productType).trim(),
    Math.min(3.5, Math.max(0, phValue - 0.5)),
    Math.max(7.5, phValue + 0.5),
    JSON.stringify([Math.max(10, humidityValue - 8), Math.min(100, humidityValue + 8)]),
    6,
    12,
    6,
    5,
    7,
    6
  ];

  if (foodRows.length) {
    db.run(
      `UPDATE food_profiles SET phMin = ?, phMax = ?, humidityRange = ?, fragility = ?, respiration = ?, temperatureSensitivity = ?, handlingShock = ?, moistureSensitivity = ?, bulkDensity = ? WHERE foodName = ? AND productType = ?`,
      [
        Math.min(3.5, Math.max(0, phValue - 0.5)),
        Math.max(7.5, phValue + 0.5),
        JSON.stringify([Math.max(10, humidityValue - 8), Math.min(100, humidityValue + 8)]),
        6,
        12,
        6,
        5,
        7,
        6,
        String(foodName).trim(),
        String(productType).trim()
      ]
    );
  } else {
    db.run(
      `INSERT INTO food_profiles (foodName, productType, phMin, phMax, humidityRange, fragility, respiration, temperatureSensitivity, handlingShock, moistureSensitivity, bulkDensity)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      profileValues
    );
  }

  const materialRows = fetchRows('SELECT * FROM materials WHERE name = ?', [String(materialName).trim()]);
  const materialFeatures = features || {
    'Product fragility': 80,
    'Product dimensions': 78,
    'Required cushioning': 74,
    'Packaging material': 82,
    'Box strength required': 72,
    'Transportation risk': 74,
    'Moisture sensitivity': 79,
    'Temperature sensitivity': 76,
    'Expected handling/shock': 75,
    'Packaging cost': 70,
    'Sustainability/recyclability': 73,
    'Estimated damage risk': 75,
    'Packaging dimensions': 81
  };

  if (materialRows.length) {
    db.run(
      `UPDATE materials SET color = ?, details = ?, features = ? WHERE name = ?`,
      [color || '#67b66d', String(materialDetails || '').trim(), JSON.stringify(materialFeatures), String(materialName).trim()]
    );
  } else {
    db.run(
      `INSERT INTO materials (name, color, details, features) VALUES (?, ?, ?, ?)`,
      [String(materialName).trim(), color || '#67b66d', String(materialDetails || '').trim(), JSON.stringify(materialFeatures)]
    );
  }

  saveDatabase();

  return res.status(201).json({
    ok: true,
    foodName: String(foodName).trim(),
    productType: String(productType).trim(),
    materialName: String(materialName).trim()
  });
});

app.get('/', (req, res) => {
  res.sendFile(path.join(rootDir, 'index.html'));
});

initializeDatabase()
  .then(() => {
    app.listen(port, () => {
      console.log(`OptiPAck SQLite server running at http://localhost:${port}`);
    });
  })
  .catch((error) => {
    console.error('Failed to initialize SQLite database:', error);
    process.exit(1);
  });
