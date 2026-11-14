# OptiPAck

OptiPAck recommends packaging materials for food products using product and
handling conditions. It also provides material details and saves recommendation
records for traceability.

## Features

- Rank packaging materials using food type, temperature, pH, and humidity.
- Browse packaging material details, performance, and sustainability information.
- Save recommendations and view their traceability records.
- Generate QR codes for recommendation records.

## Technology

- **Web app and API:** Node.js, Express, and SQLite (`sql.js`)
- **User interface:** HTML, CSS, and JavaScript
- **Optional recommendation API:** Python, FastAPI, and Uvicorn

The main web application uses the Node.js backend. The Python API is a separate,
optional service and is not required by the web UI.

## Run locally

### Requirements

- Node.js 18 or later
- npm

### Start the web application

From the repository root, run:

```bash
npm install
npm start
```

Open [http://localhost:3000](http://localhost:3000). The server also exposes a
health check at [http://localhost:3000/api/health](http://localhost:3000/api/health).

The SQLite database is initialized automatically from the JSON seed files in
`data/`. The runtime database file is generated locally and is not committed to
Git.

### Start the optional Python API

In a separate terminal, install the Python requirements and start the API:

```bash
python -m pip install -r requirements.txt
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

The API health check is available at [http://localhost:8000/health](http://localhost:8000/health).

## Deploy from GitHub with Render

The Node.js app serves both the frontend and its API, so deploy it as a
**Node.js web service** (for example, on Render):

1. Push this repository to GitHub.
2. In Render, create a **New Web Service** and connect the repository.
3. Use the repository root as the service root directory.
4. Set the build command to `npm install`.
5. Set the start command to `npm start`.
6. Deploy, then verify the service's `/api/health` endpoint returns
   `{"ok":true,"database":"sqlite"}`.

The server listens on the `PORT` environment variable provided by the hosting
platform. No additional environment variables are required.

### Deployment notes

- **GitHub Pages is not sufficient** for this application: it only hosts static
  files, while OptiPAck requires its Node.js API and database.
- The app stores its SQLite database in `data/packwise.db`. On hosts with an
  ephemeral filesystem, saved traceability records may be lost when the service
  restarts or is redeployed. The catalog and food profiles are initialized from
  the JSON seed files on a fresh database.
- For durable production records, use a host with persistent storage or migrate
  the runtime database to a managed database before deployment.
