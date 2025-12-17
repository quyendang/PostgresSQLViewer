# Postgres SQL Tool (FastAPI + Bootstrap)

PostgresSQLViewer: A lightweight web-based SQL client for PostgreSQL, built with **FastAPI**, **asyncpg**, and **Bootstrap 5**.  
It lets you connect to a Postgres database via URL (with optional SSL), browse tables, view data, and run arbitrary SQL queries directly in the browser.

---

## Features

- **Connect by URL (DSN)**  
  - Example: `postgres://user:password@host:5432/dbname`  
  - Optional SSL mode: `disable` or `require`

- **Table Browser**
  - Lists all base tables from non-system schemas  
  - Quickly view data: `SELECT * FROM schema.table LIMIT 200`

- **SQL Console**
  - Run `SELECT` queries and see results as an HTML table  
  - Run non-SELECT statements (INSERT / UPDATE / DDL) and see status (e.g. `INSERT 0 1`)  
  - Simple, flat UI using Bootstrap 5

---

## Requirements

Python 3.10+ is recommended.

Install dependencies:

```bash
pip install fastapi uvicorn[standard] asyncpg
```

If you already have a project `requirements.txt`, you can also add:

```txt
fastapi
uvicorn[standard]
asyncpg
```

---

## Running the App

From the project root (where `app.py` is inside the `templates` package):

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Then open your browser:

```text
http://localhost:8000
```

---

## Usage

1. **Connect to Postgres**
   - Enter your Postgres URL (DSN), e.g.  
     `postgres://user:password@my-host:5432/mydatabase`
   - Choose `SSL mode`:
     - `disable` – no SSL
     - `require` – connect with SSL (`ssl=True` in asyncpg)
   - Click **“Connect & Load Tables”**

2. **Browse Tables**
   - After connecting, the left panel shows available tables as `schema.table`  
   - Select a table and click **“View Table (LIMIT 200)”**  
   - First 200 rows are displayed in the right panel

3. **Run SQL Queries**
   - Use the **SQL Console** on the right  
   - Type any SQL in the textarea:
     - If the query starts with `SELECT` or `WITH`, results are shown in a table  
     - Otherwise, the execution status is shown (e.g. `UPDATE 3`)
   - Click **“Run SQL”** to execute

---

## SSL Notes

- The effective SSL mode is determined by:
  1. The `SSL mode` dropdown (form value), or  
  2. `sslmode` query parameter in the URL (if present),  
  3. Defaults to `disable` if not provided.
- When `sslmode=require` (or stronger), `asyncpg.connect` is called with `ssl=True`.

---

## Development

To run directly via Python:

```bash
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

You can customize layout / styles by editing `app.py` (HTML is embedded).

