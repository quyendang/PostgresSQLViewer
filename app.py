from __future__ import annotations

"""
app.py — Simple Postgres Web SQL client using FastAPI + Bootstrap

Chạy local:
    uvicorn app:app --reload --port 8000
Hoặc:
    python -m uvicorn app:app --host 0.0.0.0 --port 8000
"""

import html
import json
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
    deletable_table: str | None = None,
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
    result_parts: List[str] = []

    if error:
        result_parts.append(
            f"""
            <div class="alert alert-danger alert-soft" role="alert">
              <div class="fw-bold mb-1">Error</div>
              <div class="small">{esc(error)}</div>
            </div>
            """
        )
    elif message:
        result_parts.append(
            f"""
            <div class="alert alert-info alert-soft" role="alert">
              <div class="small">{esc(message)}</div>
            </div>
            """
        )

    def _cell_html(v: Any) -> str:
        if v is None:
            return '<span class="cell-null">NULL</span>'
        return esc(str(v))

    if columns and rows:
        # Header
        header_html = "".join(f"<th>{esc(str(col))}</th>" for col in columns)
        if deletable_table:
            header_html += '<th class="col-actions">Actions</th>'

        # Body
        body_rows_html = ""
        for r in rows:
            tds = "".join(f"<td>{_cell_html(v)}</td>" for v in r)

            # Nếu có deletable_table, thêm nút delete cho mỗi row
            if deletable_table:
                row_dict: dict[str, str] = {}
                for col, val in zip(columns, r):
                    # Lưu dưới dạng text để so sánh bằng ::text
                    row_dict[str(col)] = "" if val is None else str(val)
                row_json = esc(json.dumps(row_dict, ensure_ascii=False))

                delete_btn_html = f"""
                <td class="text-center align-middle">
                  <form method="post" action="/" class="d-inline">
                    <input type="hidden" name="db_url" value="{esc(db_url)}" />
                    <input type="hidden" name="sslmode" value="{esc(sslmode)}" />
                    <input type="hidden" name="delete_table_name" value="{esc(deletable_table)}" />
                    <input type="hidden" name="row_json" value="{row_json}" />
                    <button type="submit" name="action" value="delete_row"
                            class="btn btn-outline-danger btn-sm btn-delete"
                            title="Delete row"
                            onclick="return confirm('Delete this row?');">
                      Delete
                    </button>
                  </form>
                </td>
                """
            else:
                delete_btn_html = ""

            body_rows_html += f"<tr>{tds}{delete_btn_html}</tr>\n"

        result_parts.append(
            f"""
            <div class="table-responsive mt-2">
              <table class="table table-sm table-hover w-100 result-table">
                <thead>
                  <tr>{header_html}</tr>
                </thead>
                <tbody>
                  {body_rows_html}
                </tbody>
              </table>
            </div>
            """
        )

    if not result_parts:
        result_parts.append(
            """
            <div class="empty-state">
              <div class="empty-title">No results yet</div>
              <div class="empty-sub">Connect, pick a table, or run a query to see output here.</div>
            </div>
            """
        )

    result_html = "\n".join(result_parts)

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
        :root {{
          --bg: #f6f8fc;
          --card: #ffffff;
          --text: #0f172a;
          --muted: #64748b;
          --border: #e5eaf3;
          --soft: #f1f5ff;
          --codebg: #f8fafc;

          --blue: #2563eb;
          --green: #16a34a;
          --red: #dc2626;

          --radius: 18px;
          --shadow2: 0 8px 20px rgba(15, 23, 42, 0.06);
          --shadow: 0 14px 40px rgba(15, 23, 42, 0.08);

          --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        }}

        * {{ box-sizing: border-box; }}

        body {{
          margin: 0;
          background:
            radial-gradient(1200px 600px at 20% 0%, #eaf2ff 0%, transparent 60%),
            radial-gradient(900px 500px at 100% 20%, #eef2ff 0%, transparent 55%),
            var(--bg);
          color: var(--text);
        }}

        .container {{ max-width: 1100px; }}

        /* Navbar (glass) */
        .navbar {{
          background: rgba(255,255,255,.82) !important;
          backdrop-filter: blur(10px);
          -webkit-backdrop-filter: blur(10px);
          border-bottom: 1px solid var(--border) !important;
        }}
        .navbar-brand {{
          font-weight: 900;
          letter-spacing: .02em;
          display: inline-flex;
          align-items: center;
          gap: 10px;
          color: var(--text);
        }}
        .brand-dot {{
          width: 10px;
          height: 10px;
          border-radius: 999px;
          background: var(--blue);
          box-shadow: 0 0 0 5px rgba(37, 99, 235, .12);
        }}

        /* Cards */
        .card {{
          border-radius: var(--radius);
          border: 1px solid var(--border);
          box-shadow: var(--shadow2);
          overflow: hidden;
        }}
        .card-body {{ padding: 16px; }}
        .card-title {{
          font-weight: 900;
          letter-spacing: .01em;
          color: var(--text);
        }}

        /* Labels / inputs */
        .form-label.small {{
          color: var(--muted) !important;
          font-weight: 800;
          letter-spacing: .01em;
        }}
        .form-control, .form-select {{
          border-radius: 12px;
          border: 1px solid var(--border);
          background: #fff;
          box-shadow: none !important;
        }}
        .form-control:focus, .form-select:focus {{
          border-color: rgba(37, 99, 235, .35);
          box-shadow: 0 0 0 .2rem rgba(37, 99, 235, .10) !important;
        }}

        textarea.sql-box {{
          font-family: var(--mono);
          min-height: 170px;
          background: var(--codebg);
          border-color: var(--border);
          line-height: 1.5;
        }}

        /* Buttons */
        .btn {{
          border-radius: 12px;
          font-weight: 800;
        }}
        .btn-primary {{
          box-shadow: 0 10px 18px rgba(37, 99, 235, .18);
        }}
        .btn-success {{
          box-shadow: 0 10px 18px rgba(22, 163, 74, .16);
        }}
        .btn-outline-secondary {{
          border-color: #d7deea;
        }}
        .btn-link {{
          color: var(--muted);
          font-weight: 800;
        }}
        .btn-link:hover {{ color: var(--text); }}

        /* Tips + code */
        code {{
          font-family: var(--mono);
          background: #eef2ff;
          border: 1px solid #e5e7ff;
          padding: 2px 6px;
          border-radius: 999px;
          color: #1e40af;
          font-size: 12px;
        }}
        .hint {{
          background: var(--soft);
          border: 1px solid rgba(37, 99, 235, .18);
          color: #1e40af;
          padding: 10px 12px;
          border-radius: 14px;
          font-size: 13px;
        }}

        /* Collapse arrow (no bootstrap icons needed) */
        .chev {{
          display:inline-block;
          width: 10px;
          height: 10px;
          border-right: 2px solid currentColor;
          border-bottom: 2px solid currentColor;
          transform: rotate(45deg);
          margin-left: 6px;
          opacity: .75;
        }}

        /* Results wrapper */
        .result-wrap {{
          border: 1px solid var(--border);
          border-radius: 14px;
          background: #fff;
          padding: 10px;
          overflow: auto;
        }}

        .alert-soft {{
          border-radius: 14px;
          border: 1px solid var(--border);
          background: #fff;
          margin-bottom: 10px;
        }}

        .empty-state {{
          padding: 18px 14px;
          border: 1px dashed #d7deea;
          border-radius: 14px;
          background: #fbfcff;
        }}
        .empty-title {{
          font-weight: 900;
          margin-bottom: 2px;
        }}
        .empty-sub {{
          color: var(--muted);
          font-size: 13px;
        }}

        .cell-null {{
          display: inline-block;
          padding: 2px 8px;
          border-radius: 999px;
          font-size: 12px;
          color: #0f172a;
          background: #f1f5f9;
          border: 1px solid #e2e8f0;
        }}

        /* Make results table cleaner */
        .result-table {{
          border-collapse: separate !important;
          border-spacing: 0 !important;
          border: 1px solid var(--border);
          border-radius: 14px;
          overflow: hidden;
          background: #fff;
          margin-bottom: 0;
        }}
        .result-table thead th {{
          position: sticky;
          top: 0;
          z-index: 1;
          background: #fbfcff !important;
          color: var(--muted) !important;
          font-weight: 900;
          font-size: 12px;
          white-space: nowrap;
          border-bottom: 1px solid var(--border) !important;
        }}
        .result-table tbody td {{
          border-bottom: 1px solid var(--border);
          vertical-align: top;
        }}
        .result-table tbody tr:hover td {{
          background: #f8fbff;
        }}
        .result-table tbody tr:last-child td {{
          border-bottom: none;
        }}

        .col-actions {{ width: 120px; text-align: center; }}
        .btn-delete {{ white-space: nowrap; }}

        @media (max-width: 720px) {{
          .card-body {{ padding: 14px; }}
          textarea.sql-box {{ min-height: 190px; }}
        }}
      </style>
    </head>
    <body>
      <nav class="navbar navbar-expand-lg mb-3">
        <div class="container-fluid">
          <span class="navbar-brand">
            <span class="brand-dot"></span>
            Postgres SQL Tool
          </span>
        </div>
      </nav>

      <div class="container pb-4">
        <div class="vstack gap-3">
          <!-- ConnectionView -->
          <div class="row g-3">
            <div class="col-12">
              <div class="card">
                <div class="card-body">
                  <h6 class="card-title mb-3">Connection</h6>
                  <form method="post" action="/" class="row g-2">
                    <div class="col-12">
                      <label class="form-label small">Postgres URL (DSN)</label>
                      <input type="text" id="dbUrlInput" name="db_url" class="form-control form-control-sm"
                             placeholder="postgres://user:pass@host:port/dbname"
                             list="dbUrlHistoryList"
                             value="{esc(db_url)}" required />
                      <datalist id="dbUrlHistoryList"></datalist>
                    </div>
                    <div class="col-6">
                      <label class="form-label small">SSL mode</label>
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
                  <div class="mt-3 hint">
                    Tip: DSN gần đây sẽ được lưu trong trình duyệt để chọn nhanh (autocomplete).
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- ExpandCollapse: TablesView -->
          <div class="row g-3">
            <div class="col-12">
              <div class="d-flex justify-content-between align-items-center mb-2">
                <h6 class="mb-0 text-muted" style="font-weight:900; letter-spacing:.01em;">Tables</h6>
                <button class="btn btn-link btn-sm text-decoration-none" type="button"
                        data-bs-toggle="collapse" data-bs-target="#tablesCollapse"
                        aria-expanded="false" aria-controls="tablesCollapse">
                  <span class="me-1">Show / Hide</span><span class="chev"></span>
                </button>
              </div>
              <div class="collapse show" id="tablesCollapse">
                <div class="card">
                  <div class="card-body">
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
            </div>
          </div>

          <!-- SQLConsoleView -->
          <div class="row g-3">
            <div class="col-12">
              <div class="card">
                <div class="card-body">
                  <h6 class="card-title mb-3">SQL Console</h6>
                  <form method="post" action="/">
                    <input type="hidden" name="db_url" value="{esc(db_url)}" />
                    <input type="hidden" name="sslmode" value="{esc(sslmode)}" />
                    <div class="mb-2">
                      <textarea name="sql_text" class="form-control form-control-sm sql-box"
                                placeholder="SELECT * FROM your_table LIMIT 50;">{esc(sql_text)}</textarea>
                    </div>
                    <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
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
            </div>
          </div>

          <!-- ResultsView -->
          <div class="row g-3">
            <div class="col-12">
              <div class="card">
                <div class="card-body">
                  <h6 class="card-title mb-2">Results</h6>
                  <div class="result-wrap">
                    {result_html}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"
              integrity="sha384-YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz"
              crossorigin="anonymous"></script>

      <script>
        // Simple localStorage-based DB URL history
        const STORAGE_KEY = "sqltool_db_urls";

        function loadUrlHistory() {{
          let raw = localStorage.getItem(STORAGE_KEY);
          let urls = [];
          try {{
            urls = raw ? JSON.parse(raw) : [];
          }} catch (e) {{
            urls = [];
          }}

          const dataList = document.getElementById("dbUrlHistoryList");
          if (!dataList) return;
          dataList.innerHTML = "";

          urls.forEach(u => {{
            const opt = document.createElement("option");
            opt.value = u;
            dataList.appendChild(opt);
          }});
        }}

        function saveCurrentUrl() {{
          const input = document.getElementById("dbUrlInput");
          if (!input) return;
          const url = input.value.trim();
          if (!url) return;

          let raw = localStorage.getItem(STORAGE_KEY);
          let urls = [];
          try {{
            urls = raw ? JSON.parse(raw) : [];
          }} catch (e) {{
            urls = [];
          }}

          // Đưa URL hiện tại lên đầu list, loại bỏ trùng lặp
          urls = [url, ...urls.filter(u => u !== url)];
          // Giữ tối đa 10 URL gần nhất
          urls = urls.slice(0, 10);

          localStorage.setItem(STORAGE_KEY, JSON.stringify(urls));
          loadUrlHistory();
        }}

        document.addEventListener("DOMContentLoaded", () => {{
          loadUrlHistory();

          // Lưu URL khi nhấn nút Connect
          const connectBtn = document.querySelector('button[name="action"][value="connect"]');
          if (connectBtn) {{
            connectBtn.addEventListener("click", () => {{
              saveCurrentUrl();
            }});
          }}
        }});
      </script>
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
    delete_table_name: str | None = Form(None),
    row_json: str | None = Form(None),
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
    deletable_table: str | None = None

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
                q = '"'
                ident = f'{q}{schema.replace(q, q+q)}{q}.{q}{name.replace(q, q+q)}{q}'
                sql = f"SELECT * FROM {ident} LIMIT 200;"
                columns, rows = await _run_select(conn, sql)
                message = f"Showing first {len(rows)} rows from {schema}.{name}"
                deletable_table = f"{schema}.{name}"

        elif action == "delete_row" and delete_table_name and row_json:
            # Xóa 1 row dựa trên dữ liệu từ kết quả view_table
            selected_table = delete_table_name
            if "." in delete_table_name:
                schema, name = delete_table_name.split(".", 1)
            else:
                schema, name = "public", delete_table_name

            if (schema, name) not in tables:
                error = f"Table {schema}.{name} not found or not allowed for delete."
            else:
                try:
                    row_data = json.loads(row_json)
                except Exception as ex:
                    error = f"Invalid row data: {ex}"
                    row_data = None

                if row_data:
                    # Build DELETE ... WHERE "col"::text = $1 AND ...
                    conditions = []
                    values: List[str] = []
                    idx = 1
                    for col, val in row_data.items():
                        safe_col = col.replace('"', '""')
                        conditions.append(f'"{safe_col}"::text = ${idx}')
                        values.append(str(val))
                        idx += 1

                    q = '"'
                    ident = f'{q}{schema.replace(q, q+q)}{q}.{q}{name.replace(q, q+q)}{q}'
                    where_clause = " AND ".join(conditions) if conditions else "TRUE"
                    delete_sql = f"DELETE FROM {ident} WHERE {where_clause} RETURNING *"

                    deleted_rows = await conn.fetch(delete_sql, *values)
                    deleted_count = len(deleted_rows)
                    message = f"Deleted {deleted_count} row(s) from {schema}.{name}"

                # Reload table after delete
                q = '"'
                ident = f'{q}{schema.replace(q, q+q)}{q}.{q}{name.replace(q, q+q)}{q}'
                sql = f"SELECT * FROM {ident} LIMIT 200;"
                columns, rows = await _run_select(conn, sql)
                deletable_table = f"{schema}.{name}"

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
        deletable_table=deletable_table,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
