"""MCP sqlite server (stdio) — used by test/test_mcp_sqlite.py.

Seeds an in-memory SQLite database with a small sales table and exposes
a single tool:
  - query_db(sql: str) → str   (read-only SELECT queries)
"""
import sqlite3

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("kegal-sqlite-server")

# --- seed database -----------------------------------------------------------

_DB = sqlite3.connect(":memory:", check_same_thread=False)
_DB.executescript("""
    CREATE TABLE sales (
        id      INTEGER PRIMARY KEY,
        product TEXT    NOT NULL,
        quarter TEXT    NOT NULL,
        revenue REAL    NOT NULL
    );
    INSERT INTO sales (product, quarter, revenue) VALUES
        ('Widget A', 'Q1', 12500.00),
        ('Widget B', 'Q1',  8300.00),
        ('Widget A', 'Q2', 15200.00),
        ('Widget B', 'Q2', 11400.00),
        ('Widget C', 'Q2',  4700.00),
        ('Widget A', 'Q3', 13800.00),
        ('Widget B', 'Q3',  9600.00),
        ('Widget C', 'Q3',  6200.00),
        ('Widget A', 'Q4', 17100.00),
        ('Widget B', 'Q4', 12000.00),
        ('Widget C', 'Q4',  8900.00);
""")
_DB.commit()

# --- tool --------------------------------------------------------------------

@mcp.tool()
def query_db(sql: str) -> str:
    """Execute a read-only SQL SELECT query against the sales database and return the results."""
    try:
        cursor = _DB.execute(sql)
        rows = cursor.fetchall()
        if not rows:
            return "No results."
        headers = [desc[0] for desc in cursor.description]
        lines = [", ".join(headers)]
        for row in rows:
            lines.append(", ".join(str(v) for v in row))
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
