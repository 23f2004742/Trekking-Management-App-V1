# Trekking Management App

A Flask and SQLite web application for managing treks, staff approvals, trek bookings, and trekking history.

## Run Locally

1. Install dependencies with `pip install -r requirements.txt`.
2. Start the app with `python app.py`.
3. Open the app in your browser.

## JSON API

- `GET /api/treks`
- `GET /api/treks/<id>`
- `GET, POST /api/bookings`
- `GET, DELETE /api/bookings/<id>`
- `PUT /api/treks/<id>`