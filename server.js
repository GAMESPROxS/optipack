const express = require('express');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { createHash, randomUUID } = require('crypto');
const initSqlJs = require('sql.js');
const QRCode = require('qrcode');

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

const scoreToFeature = {
  product_fragility_compatibility: 'Product fragility',
  product_dimensions_compatibility: 'Product dimensions',
  required_cushioning: 'Required cushioning',
  material_suitability: 'Packaging material',
  box_strength: 'Box strength required',
  transportation_risk_suitability: 'Transportation risk',
  moisture_resistance: 'Moisture sensitivity',
  temperature_resistance: 'Temperature sensitivity',
  handling_shock_resistance: 'Expected handling/shock',
  packaging_cost: 'Packaging cost',
  sustainability_recyclability: 'Sustainability/recyclability',
  damage_risk_performance: 'Estimated damage risk',
  packaging_dimensions_compatibility: 'Packaging dimensions',
  otr_barrier: 'Oxygen transmission rate (OTR)',
  wvtr_barrier: 'Water vapor transmission rate (WVTR)',
  heat_sealability: 'Heat sealability',
  biodegradability: 'Biodegradability'
};
const scoreKeys = Object.keys(scoreToFeature);
const materialColors = {
  'Conventional Plastics': '#4a8ca4',
  Paper: '#d7a44d',
  Paperboard: '#b78a5f',
  Metals: '#8f9196',
  Glass: '#7ca3d0',
  Bioplastics: '#67b66d',
  'Natural Polymers': '#82c7af',
  'Protein Materials': '#d89b5d',
  'Lipid Materials': '#a8b65d',
  'Composite Materials': '#8c6bb7',
  'Protective Materials': '#d7a263',
  'Edible Packaging': '#71b06a',
  'Active Packaging': '#8a7fd6',
  'Intelligent Packaging': '#9ba5d1',
  Legacy: '#7aa86c'
};

function scoresFromFeatures(features = {}) {
  return Object.fromEntries(scoreKeys.map((key) => [
    key,
    Number(features[scoreToFeature[key]] ?? 50)
  ]));
}

function featuresFromScores(scores = {}) {
  return Object.fromEntries(scoreKeys.map((key) => [
    scoreToFeature[key],
    Number(scores[key] ?? 50)
  ]));
}

function inferMaterialCategory(name) {
  const lowered = name.toLowerCase();
  if (['metalized', 'metalised', 'aluminium', 'aluminum', 'tinplate', 'steel', 'foil'].some((term) => lowered.includes(term))) return 'Metals';
  if (['paperboard', 'carton', 'corrugate', 'pulp tray', 'honeycomb'].some((term) => lowered.includes(term))) return 'Paperboard';
  if (lowered.includes('glass')) return 'Glass';
  if (['paper', 'kraft', 'glassine', 'parchment'].some((term) => lowered.includes(term))) return 'Paper';
  if (['foam', 'eps', 'epe', 'epp', 'polyurethane', 'eva'].some((term) => lowered.includes(term))) return 'Protective Materials';
  if (['laminate', 'composite', 'vacuum skin', 'modified atmosphere'].some((term) => lowered.includes(term))) return 'Composite Materials';
  if (['polyethylene', 'polypropylene', 'pet', 'pvc', 'polystyrene', 'nylon', 'evoh', 'pvdc', 'plastic', 'film', 'pouch', 'clamshell', 'tray'].some((term) => lowered.includes(term))) return 'Conventional Plastics';
  return 'Legacy';
}

function expandMaterialCatalog() {
  const legacyRows = readSeedJson('material_catalog.json');
  const additions = readSeedJson('material_catalog_additions.json');
  const rows = legacyRows.map((row, index) => ({
    material_id: `PKG-${String(index + 1).padStart(4, '0')}`,
    material_name: row.material_name || row.name,
    material_category: row.material_category || inferMaterialCategory(row.name),
    composition: row.composition || row.details || row.name,
    development_status: row.development_status || 'Commercial',
    scores: scoresFromFeatures(row.features || {}),
    measurements: row.measurements || {
      otr: null,
      otr_unit: 'cc/m2/day',
      wvtr: null,
      wvtr_unit: 'g/m2/day'
    },
    food_contact_status: row.food_contact_status || 'Requires verification',
    recyclability: row.recyclability || 'Depends on local facilities',
    source_references: row.source_references || [],
    color: row.color || materialColors[row.material_category || inferMaterialCategory(row.name)] || '#67b66d',
    details: row.details || row.composition || row.name
  }));
  const profiles = additions.score_profiles || {};
  const references = additions.references || {};
  const additionsScoreKeys = additions.score_keys || scoreKeys;

  for (const row of additions.materials || []) {
    let scores = profiles[row.score_profile] || {};
    if (Array.isArray(scores)) {
      scores = Object.fromEntries(additionsScoreKeys.map((key, index) => [key, scores[index]]));
    }
    const sourceReferences = row.source_references || (row.source_reference_ids || [])
      .flatMap((referenceId) => references[referenceId] || []);
    const resolvedScores = Object.fromEntries(scoreKeys.map((key) => [
      key,
      Number(row.score_overrides?.[key] ?? scores[key] ?? 50)
    ]));
    rows.push({
      ...row,
      material_category: row.material_category,
      scores: resolvedScores,
      measurements: row.measurements || {
        otr: null,
        otr_unit: 'cc/m2/day',
        wvtr: null,
        wvtr_unit: 'g/m2/day'
      },
      food_contact_status: row.food_contact_status || 'Requires verification',
      recyclability: row.recyclability || 'Depends on local facilities',
      source_references: sourceReferences,
      color: row.color || materialColors[row.material_category] || '#67b66d',
      details: row.details || row.composition
    });
  }

  const seen = new Set();
  return rows.filter((row) => {
    const key = row.material_name.trim().toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

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
  const scores = JSON.parse(row.scores || '{}');
  const features = featuresFromScores(scores);
  return {
    id: row.material_id,
    material_id: row.material_id,
    material_name: row.material_name,
    material_category: row.material_category,
    composition: row.composition,
    development_status: row.development_status,
    scores,
    measurements: JSON.parse(row.measurements || '{}'),
    food_contact_status: row.food_contact_status,
    recyclability: row.recyclability,
    source_references: JSON.parse(row.source_references || '[]'),
    name: row.material_name,
    color: materialColors[row.material_category] || '#67b66d',
    details: row.composition,
    features
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

function insertMaterialCatalogRecord(record) {
  db.run(
    `INSERT OR IGNORE INTO material_catalog (
       material_id, material_name, material_category, composition,
       development_status, scores, measurements, food_contact_status,
       recyclability, source_references
     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      record.material_id,
      record.material_name,
      record.material_category,
      record.composition,
      record.development_status,
      JSON.stringify(record.scores),
      JSON.stringify(record.measurements),
      record.food_contact_status,
      record.recyclability,
      JSON.stringify(record.source_references)
    ]
  );
  db.run(
    `UPDATE material_catalog SET
       material_name = ?, material_category = ?, composition = ?,
       development_status = ?, scores = ?, measurements = ?,
       food_contact_status = ?, recyclability = ?, source_references = ?
     WHERE material_id = ?`,
    [
      record.material_name,
      record.material_category,
      record.composition,
      record.development_status,
      JSON.stringify(record.scores),
      JSON.stringify(record.measurements),
      record.food_contact_status,
      record.recyclability,
      JSON.stringify(record.source_references),
      record.material_id
    ]
  );
}

function seedMaterialCatalog() {
  for (const record of expandMaterialCatalog()) {
    insertMaterialCatalogRecord(record);
    db.run(
      'UPDATE materials SET color = ?, details = ?, features = ? WHERE name = ?',
      [
        record.color,
        record.details,
        JSON.stringify(featuresFromScores(record.scores)),
        record.material_name
      ]
    );
  }
}

function migrateLegacyMaterials() {
  const legacyRows = fetchRows(`
    SELECT * FROM materials AS material
    WHERE id = (SELECT MIN(id) FROM materials WHERE name = material.name)
    ORDER BY id
  `);
  for (const row of legacyRows) {
    const features = JSON.parse(row.features || '{}');
    const scores = scoresFromFeatures(features);
    const existing = fetchRows(
      'SELECT material_id FROM material_catalog WHERE material_name = ?',
      [row.name]
    ).shift();
    if (existing) {
      db.run('UPDATE material_catalog SET scores = ? WHERE material_id = ?', [
        JSON.stringify(scores),
        existing.material_id
      ]);
      continue;
    }

    const materialId = `LEGACY-${createHash('sha1').update(row.name).digest('hex').slice(0, 12)}`;
    insertMaterialCatalogRecord({
      material_id: materialId,
      material_name: row.name,
      material_category: inferMaterialCategory(row.name),
      composition: row.details || row.name,
      development_status: 'Commercial',
      scores,
      measurements: {
        otr: null,
        otr_unit: 'cc/m2/day',
        wvtr: null,
        wvtr_unit: 'g/m2/day'
      },
      food_contact_status: 'Requires verification',
      recyclability: 'Depends on local facilities',
      source_references: []
    });
  }
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
    );

    CREATE TABLE IF NOT EXISTS traceability_records (
      id TEXT PRIMARY KEY,
      foodName TEXT NOT NULL,
      productType TEXT NOT NULL,
      temperature REAL NOT NULL,
      ph REAL NOT NULL,
      humidity INTEGER NOT NULL,
      materialName TEXT NOT NULL,
      recommendationScore REAL NOT NULL,
      materialFeatures TEXT NOT NULL,
      createdAt TEXT NOT NULL
    );
  `);

  seedMaterialCatalog();
  migrateLegacyMaterials();

  const traceabilityColumns = db.exec('PRAGMA table_info(traceability_records)')[0]?.values || [];
  if (!traceabilityColumns.some((column) => column[1] === 'topMaterials')) {
    db.run("ALTER TABLE traceability_records ADD COLUMN topMaterials TEXT NOT NULL DEFAULT '[]'");
  }

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

app.get('/api/app-url', (req, res) => {
  res.set('Access-Control-Allow-Origin', '*');

  const host = req.get('host') || `localhost:${port}`;
  const protocol = (req.get('x-forwarded-proto') || req.protocol).split(',')[0];
  let appHost = host;

  if (/^(localhost|127(?:\.\d{1,3}){3})(?::\d+)?$/i.test(host)) {
    const addresses = Object.values(os.networkInterfaces()).flat().filter((address) =>
      address && !address.internal && (address.family === 'IPv4' || address.family === 4)
    );
    const lanAddress = addresses.find(({ address }) =>
      /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(address)
    ) || addresses[0];

    if (lanAddress) appHost = `${lanAddress.address}:${port}`;
  }

  res.json({ url: `${protocol}://${appHost}` });
});

app.get('/api/health', (req, res) => {
  res.json({ ok: true, database: 'sqlite' });
});

app.get('/api/qr', async (req, res) => {
  if (typeof req.query.data !== 'string' || !req.query.data) {
    return res.status(400).json({ error: 'A URL is required to generate a QR code.' });
  }

  try {
    const image = await QRCode.toBuffer(req.query.data, { type: 'png', width: 280, margin: 1 });
    return res.type('png').send(image);
  } catch (error) {
    return res.status(400).json({ error: 'Unable to generate the QR code.' });
  }
});

app.get('/api/food-profiles', (req, res) => {
  const rows = fetchRows('SELECT * FROM food_profiles ORDER BY id');
  res.json(rows.map(rowToFood));
});

app.get('/api/materials', (req, res) => {
  const rows = fetchRows('SELECT * FROM material_catalog ORDER BY material_id');
  res.json(rows.map(rowToMaterial));
});

app.post('/api/traceability', (req, res) => {
  const { foodName, productType, temperature, ph, humidity, bestMaterial, topMaterials } = req.body || {};
  const temperatureValue = Number(temperature);
  const phValue = Number(ph);
  const humidityValue = Number(humidity);
  const scoreValue = Number(bestMaterial && bestMaterial.score);
  const validTopMaterials = Array.isArray(topMaterials) && topMaterials.length === 3 &&
    topMaterials.every((material) =>
      material && typeof material.name === 'string' && material.name.trim() &&
      typeof material.score === 'number' && Number.isFinite(material.score) &&
      material.score >= 0 && material.score <= 100 &&
      material.features && typeof material.features === 'object' && !Array.isArray(material.features) &&
      Object.values(material.features).every((score) =>
        typeof score === 'number' && Number.isFinite(score) && score >= 0 && score <= 100
      )
    );

  if (
    typeof foodName !== 'string' || !foodName.trim() ||
    typeof productType !== 'string' || !productType.trim() ||
    !bestMaterial || typeof bestMaterial.name !== 'string' || !bestMaterial.name.trim() ||
    typeof temperature !== 'number' ||
    !Number.isFinite(temperatureValue) || temperatureValue < -50 || temperatureValue > 100 ||
    typeof ph !== 'number' ||
    !Number.isFinite(phValue) || phValue < 0 || phValue > 14 ||
    typeof humidity !== 'number' ||
    !Number.isInteger(humidityValue) || humidityValue < 0 || humidityValue > 100 ||
    !Number.isFinite(scoreValue) || scoreValue < 0 || scoreValue > 100 ||
    !validTopMaterials
  ) {
    return res.status(400).json({ error: 'Valid product, storage conditions, and three material recommendations are required.' });
  }

  const rankedMaterials = topMaterials.map((material) => ({
    name: material.name.trim(),
    score: material.score,
    features: material.features
  }));
  const record = {
    id: randomUUID(),
    foodName: foodName.trim(),
    productType: productType.trim(),
    temperature: temperatureValue,
    ph: phValue,
    humidity: humidityValue,
    materialName: bestMaterial.name.trim(),
    recommendationScore: scoreValue,
    materialFeatures: JSON.stringify(bestMaterial.features || {}),
    topMaterials: JSON.stringify(rankedMaterials),
    createdAt: new Date().toISOString()
  };

  try {
    db.run(
      `INSERT INTO traceability_records
       (id, foodName, productType, temperature, ph, humidity, materialName, recommendationScore, materialFeatures, topMaterials, createdAt)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        record.id,
        record.foodName,
        record.productType,
        record.temperature,
        record.ph,
        record.humidity,
        record.materialName,
        record.recommendationScore,
        record.materialFeatures,
        record.topMaterials,
        record.createdAt
      ]
    );
    saveDatabase();
    return res.status(201).json({
      ...record,
      materialFeatures: JSON.parse(record.materialFeatures),
      topMaterials: JSON.parse(record.topMaterials)
    });
  } catch (error) {
    console.error('Failed to save traceability record:', error);
    return res.status(500).json({ error: 'Unable to save the traceability record.' });
  }
});

app.get('/api/traceability/:id', (req, res) => {
  const row = fetchRows('SELECT * FROM traceability_records WHERE id = ?', [req.params.id]).shift();
  if (!row) {
    return res.status(404).json({ error: 'Traceability record not found.' });
  }

  return res.json({
    id: row.id,
    foodName: row.foodName,
    productType: row.productType,
    temperature: Number(row.temperature),
    ph: Number(row.ph),
    humidity: Number(row.humidity),
    materialName: row.materialName,
    recommendationScore: Number(row.recommendationScore),
    materialFeatures: JSON.parse(row.materialFeatures || '{}'),
    topMaterials: JSON.parse(row.topMaterials || '[]'),
    createdAt: row.createdAt
  });
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

  const cleanName = String(materialName).trim();
  const cleanDetails = String(details).trim();
  if (!cleanName || !cleanDetails) {
    return res.status(400).json({ error: 'Material name and details are required.' });
  }
  if (fetchRows('SELECT material_id FROM material_catalog WHERE material_name = ?', [cleanName]).length) {
    return res.status(409).json({ error: 'A material with this name already exists.' });
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
    'Packaging dimensions': 81,
    'Oxygen transmission rate (OTR)': 74,
    'Water vapor transmission rate (WVTR)': 71,
    'Heat sealability': 77,
    'Biodegradability': 68
  };
  const record = {
    material_id: `PKG-CUSTOM-${randomUUID()}`,
    material_name: cleanName,
    material_category: 'Legacy',
    composition: cleanDetails,
    development_status: 'Commercial',
    scores: scoresFromFeatures(features),
    measurements: {
      otr: null,
      otr_unit: 'cc/m2/day',
      wvtr: null,
      wvtr_unit: 'g/m2/day'
    },
    food_contact_status: 'Requires verification',
    recyclability: 'Depends on local facilities',
    source_references: []
  };

  insertMaterialCatalogRecord(record);
  db.run(
    `INSERT INTO materials (name, color, details, features)
     VALUES (?, ?, ?, ?)`,
    [cleanName, color || '#67b66d', cleanDetails, JSON.stringify(features)]
  );

  saveDatabase();

  const saved = fetchRows('SELECT * FROM material_catalog WHERE material_id = ?', [record.material_id]).shift();
  return res.status(201).json(rowToMaterial(saved));
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
