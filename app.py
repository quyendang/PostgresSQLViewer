from __future__ import annotations

"""
sqltool.py — Simple Postgres Web SQL client using FastAPI + Bootstrap

Chạy local:
    uvicorn app:app --reload --port 8000
Hoặc:
    python -m uvicorn app:app --host 0.0.0.0 --port 8000
"""

import html
from typing import Any, List, Tuple
from urllib.parse import urlparse, parse_qs

import asyncpg
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse


app = FastAPI(title="Postgres SQL Tool")


async def _connect(db_url: str, sslmode: str | None = None) -> asyncpg.Connection:
    """
    Tạo kết nối asyncpg từ db_url.
    Hỗ trợ sslmode=require (hoặc sslmode trong chính URL).
    """
    parsed = urlparse(db_url)
    qs = parse_qs(parsed.query or "")

    # sslmode ưu tiên từ form, nếu không thì lấy từ query string
    sslmode_form = (sslmode or "").strip()
    sslmode_qs = (qs.get("sslmode", [""])[0] or "").strip()
    sslmode_effective = sslmode_form or sslmode_qs or "disable"

    ssl_required = sslmode_effective.lower() in {"require", "verify-full", "verify-ca"}

    # Bỏ phần query khỏi DSN để tránh asyncpg không hiểu sslmode
    dsn = db_url.split("?", 1)[0]

    conn = await asyncpg.connect(dsn=dsn, ssl=ssl_required)
    return conn


async def _get_tables(conn: asyncpg.Connection) -> List[Tuple[str, str]]:
    """
    Lấy danh sách (schema, table_name) cho các bảng thường.
    """
    rows = await conn.fetch(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name
        """
    )
    return [(r["table_schema"], r["table_name"]) for r in rows]


async def _run_select(conn: asyncpg.Connection, sql: str) -> Tuple[List[str], List[List[Any]]]:
    rows = await conn.fetch(sql)
    if not rows:
        return [], []
    columns = list(rows[0].keys())
    data_rows: List[List[Any]] = []
    for r in rows:
        data_rows.append([r[c] for c in columns])
    return columns, data_rows


async def _run_statement(conn: asyncpg.Connection, sql: str) -> str:
    status = await conn.execute(sql)
    return status


def _render_page(
    request: Request,
    db_url: str = "",
    sslmode: str = "require",
    tables: List[Tuple[str, str]] | None = None,
    selected_table: str | None = None,
    columns: List[str] | None = None,
    rows: List[List[Any]] | None = None,
    sql_text: str = "",
    message: str = "",
    error: str = "",
) -> HTMLResponse:
    tables = tables or []
    columns = columns or []
    rows = rows or []

    # Escape an toàn
    esc = html.escape

    table_options_html = "\n".join(
        f'<option value="{esc(schema + "." + name)}"{ " selected" if selected_table == f"{schema}.{name}" else ""}>'
        f"{esc(schema)}.{esc(name)}</option>"
        for schema, name in tables
    )

    # Render kết quả query
    result_html = ""
    if error:
        result_html = f"""
        <div class="alert alert-danger" role="alert">
          <strong>Error:</strong> {esc(error)}
        </div>
        """
    elif message:
        result_html = f"""
        <div class="alert alert-info" role="alert">
          {esc(message)}
        </div>
        """

    if columns and rows:
        header_html = "".join(f"<th>{esc(str(col))}</th>" for col in columns)
        body_rows_html = ""
        for r in rows:
            tds = "".join(f"<td>{esc(str(v))}</td>" for v in r)
            body_rows_html += f"<tr>{tds}</tr>\n"
        result_html += f"""
        <div class="table-responsive mt-3">
          <table class="table table-sm table-hover table-bordered">
            <thead class="table-light">
              <tr>{header_html}</tr>
            </thead>
            <tbody>
              {body_rows_html}
            </tbody>
          </table>
        </div>
        """

    page_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Postgres SQL Tool</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link
    href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
    rel="stylesheet"
    integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH"
    crossorigin="anonymous"
  />
  <style>
    body {{
      background-color: #f5f7fb;
    }}
    .navbar-brand {{
      font-weight: 600;
      letter-spacing: .03em;
    }}
    .card {{
      border-radius: 16px;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
      border: 1px solid #e2e8f0;
    }}
    textarea.sql-box {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      min-height: 140px;
    }}
    .badge-schema {{
      font-size: 0.75rem;
    }}
  </style>
</head>
<body>
  <nav class="navbar navbar-expand-lg navbar-light bg-white border-bottom mb-3">
    <div class="container-fluid">
      <span class="navbar-brand">Postgres SQL Tool</span>
    </div>
  </nav>

  <div class="container pb-4">
    <div class="row g-3">
      <!-- LEFT: Connection & Tables -->
      <div class="col-lg-4">
        <div class="card mb-3">
          <div class="card-body">
            <h6 class="card-title mb-3">Connection</h6>
            <form method="post" action="/" class="row g-2">
              <div class="col-12">
                <label class="form-label small text-muted">Postgres URL (DSN)</label>
                <input type="text" name="db_url" class="form-control form-control-sm"
                       placeholder="postgres://user:pass@host:port/dbname"
                       value="{esc(db_url)}" required />
              </div>
              <div class="col-6">
                <label class="form-label small text-muted">SSL mode</label>
                <select name="sslmode" class="form-select form-select-sm">
                  <option value="disable"{" selected" if sslmode == "disable" else ""}>disable</option>
                  <option value="require"{" selected" if sslmode == "require" else ""}>require</option>
                </select>
              </div>
              <div class="col-6 d-flex align-items-end justify-content-end">
                <button type="submit" name="action" value="connect" class="btn btn-primary btn-sm">
                  Connect & Load Tables
                </button>
              </div>
            </form>
          </div>
        </div>

        <div class="card">
          <div class="card-body">
            <h6 class="card-title mb-3">Tables</h6>
            <form method="post" action="/">
              <input type="hidden" name="db_url" value="{esc(db_url)}" />
              <input type="hidden" name="sslmode" value="{esc(sslmode)}" />
              <div class="mb-2">
                <select name="table_name" class="form-select form-select-sm" size="10">
                  {table_options_html}
                </select>
              </div>
              <button type="submit" name="action" value="view_table" class="btn btn-outline-secondary btn-sm w-100">
                View Table (LIMIT 200)
              </button>
            </form>
          </div>
        </div>
      </div>

      <!-- RIGHT: SQL Console & Results -->
      <div class="col-lg-8">
        <div class="card mb-3">
          <div class="card-body">
            <h6 class="card-title mb-3">SQL Console</h6>
            <form method="post" action="/">
              <input type="hidden" name="db_url" value="{esc(db_url)}" />
              <input type="hidden" name="sslmode" value="{esc(sslmode)}" />
              <div class="mb-2">
                <textarea name="sql_text" class="form-control form-control-sm sql-box"
                          placeholder="SELECT * FROM your_table LIMIT 50;">{esc(sql_text)}</textarea>
              </div>
              <div class="d-flex justify-content-between align-items-center">
                <div class="small text-muted">
                  Tip: dùng <code>SELECT</code> để xem dữ liệu, các lệnh khác sẽ trả về status (INSERT 0 1, UPDATE ...).
                </div>
                <button type="submit" name="action" value="run_sql" class="btn btn-success btn-sm">
                  Run SQL
                </button>
              </div>
            </form>
          </div>
        </div>

        <div class="card">
          <div class="card-body">
            <h6 class="card-title mb-2">Results</h6>
            {result_html}
          </div>
        </div>
      </div>
    </div>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"
          integrity="sha384-YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz"
          crossorigin="anonymous"></script>
</body>
</html>
    """
    return HTMLResponse(content=page_html)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """
    Trang chính: hiển thị form nhập DB URL + SSL, list tables (nếu có), và SQL console.
    Khi GET lần đầu chưa kết nối db, chỉ render form trống.
    """
    return _render_page(request)


@app.post("/", response_class=HTMLResponse)
async def post_handler(
    request: Request,
    db_url: str = Form(...),
    sslmode: str = Form("require"),
    action: str = Form("connect"),
    table_name: str | None = Form(None),
    sql_text: str = Form(""),
) -> HTMLResponse:
    """
    Xử lý:
      - action=connect      → chỉ kết nối và load danh sách bảng
      - action=view_table   → SELECT * FROM table LIMIT 200
      - action=run_sql      → chạy câu SQL tự do
    """
    tables: List[Tuple[str, str]] = []
    selected_table: str | None = None
    columns: List[str] = []
    rows: List[List[Any]] = []
    message = ""
    error = ""

    try:
        conn = await _connect(db_url, sslmode=sslmode)
    except Exception as ex:
        error = f"Cannot connect to database: {ex}"
        return _render_page(
            request,
            db_url=db_url,
            sslmode=sslmode,
            tables=[],
            selected_table=None,
            columns=[],
            rows=[],
            sql_text=sql_text,
            message="",
            error=error,
        )

    try:
        # Luôn lấy danh sách bảng nếu kết nối thành công
        tables = await _get_tables(conn)

        if action == "view_table" and table_name:
            # table_name dạng "schema.table"
            selected_table = table_name
            if "." in table_name:
                schema, name = table_name.split(".", 1)
            else:
                schema, name = "public", table_name

            # Chỉ cho phép truy cập các bảng nằm trong danh sách đã load
            if (schema, name) not in tables:
                error = f"Table {schema}.{name} not found or not allowed."
            else:
                # Dùng identifier an toàn bằng cách quote
                ident = f'"{schema.replace("\"", "\"\"")}"."{name.replace("\"", "\"\"")}"'
                sql = f"SELECT * FROM {ident} LIMIT 200;"
                columns, rows = await _run_select(conn, sql)
                message = f"Showing first {len(rows)} rows from {schema}.{name}"

        elif action == "run_sql" and sql_text.strip():
            sql = sql_text.strip()
            first_word = sql.split(None, 1)[0].lower() if sql.split() else ""

            if first_word == "select" or first_word.startswith("with"):
                columns, rows = await _run_select(conn, sql)
                message = f"Query OK, {len(rows)} rows returned."
            else:
                status = await _run_statement(conn, sql)
                message = f"Statement OK: {status}"
        else:
            # Chỉ connect & load tables
            message = "Connected. Tables loaded."

    except Exception as ex:
        error = str(ex)
    finally:
        await conn.close()

    return _render_page(
        request,
        db_url=db_url,
        sslmode=sslmode,
        tables=tables,
        selected_table=selected_table,
        columns=columns,
        rows=rows,
        sql_text=sql_text,
        message=message,
        error=error,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


