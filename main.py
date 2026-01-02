from fastmcp import FastMCP
import os
import aiosqlite
import sqlite3
import json

# ==================== CRITICAL FIX ====================
# In FastMCP Cloud, the code directory is Read-Only.
# You must use /tmp for any files you need to write (like the DB).
DB_PATH = "/tmp/expenses.db" 
# ======================================================

CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

mcp = FastMCP("ExpenseTracker")

def init_db():
    """Initialize the database synchronously to ensure tables exist before server starts."""
    # Ensure the directory exists (though /tmp usually always exists)
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    with sqlite3.connect(DB_PATH) as c:
        # Enable WAL mode for better concurrent access
        c.execute("PRAGMA journal_mode=WAL")
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS expenses(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT DEFAULT '',
                note TEXT DEFAULT ''
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS income(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                source TEXT NOT NULL,
                note TEXT DEFAULT ''
            )
        """)
        c.commit()

# Initialize DB immediately on module load
try:
    init_db()
    print(f"Database initialized successfully at {DB_PATH}")
except Exception as e:
    print(f"Failed to initialize database: {e}")

# ==================== TOOLS ====================

@mcp.tool()
async def add_expense(date: str, amount: float, category: str, subcategory: str = "", note: str = ""):
    '''Add a new expense entry to the database.'''
    async with aiosqlite.connect(DB_PATH) as c:
        cur = await c.execute(
            "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
            (date, amount, category, subcategory, note)
        )
        await c.commit()
        return {"status": "ok", "id": cur.lastrowid}
    
@mcp.tool()
async def list_expenses(start_date: str, end_date: str):
    '''List expense entries within an inclusive date range.'''
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        cur = await c.execute(
            """
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            WHERE date BETWEEN ? AND ?
            ORDER BY id ASC
            """,
            (start_date, end_date)
        )
        rows = await cur.fetchall()
        return [dict(row) for row in rows]

@mcp.tool()
async def summarize(start_date: str, end_date: str, category: str = None):
    '''Summarize expenses by category within an inclusive date range.'''
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        query = (
            """
            SELECT category, SUM(amount) AS total_amount
            FROM expenses
            WHERE date BETWEEN ? AND ?
            """
        )
        params = [start_date, end_date]
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " GROUP BY category ORDER BY category ASC"
        cur = await c.execute(query, params)
        rows = await cur.fetchall()
        return [dict(row) for row in rows]

@mcp.tool()
async def get_expense(expense_id: int):
    '''Retrieve a single expense by its ID.'''
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        cur = await c.execute(
            "SELECT id, date, amount, category, subcategory, note FROM expenses WHERE id = ?",
            (expense_id,)
        )
        row = await cur.fetchone()
        if row:
            return {"status": "ok", "expense": dict(row)}
        else:
            return {"status": "error", "message": f"Expense ID {expense_id} not found"}

@mcp.tool()
async def edit_expense(expense_id: int, date: str = None, amount: float = None, category: str = None, subcategory: str = None, note: str = None):
    '''Update an existing expense. Only provided fields will be updated.'''
    async with aiosqlite.connect(DB_PATH) as c:
        cur = await c.execute("SELECT id FROM expenses WHERE id = ?", (expense_id,))
        if not await cur.fetchone():
            return {"status": "error", "message": f"Expense ID {expense_id} not found"}
        
        updates = []
        params = []
        
        if date is not None:
            updates.append("date = ?")
            params.append(date)
        if amount is not None:
            updates.append("amount = ?")
            params.append(amount)
        if category is not None:
            updates.append("category = ?")
            params.append(category)
        if subcategory is not None:
            updates.append("subcategory = ?")
            params.append(subcategory)
        if note is not None:
            updates.append("note = ?")
            params.append(note)
        
        if not updates:
            return {"status": "error", "message": "No fields to update"}
        
        params.append(expense_id)
        query = f"UPDATE expenses SET {', '.join(updates)} WHERE id = ?"
        await c.execute(query, params)
        await c.commit()
        
        return {"status": "ok", "message": f"Expense ID {expense_id} updated successfully"}

@mcp.tool()
async def delete_expense(expense_id: int):
    '''Delete a single expense by its ID.'''
    async with aiosqlite.connect(DB_PATH) as c:
        cur = await c.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        await c.commit()
        if cur.rowcount > 0:
            return {"status": "ok", "message": f"Expense ID {expense_id} deleted successfully"}
        else:
            return {"status": "error", "message": f"Expense ID {expense_id} not found"}

@mcp.tool()
async def bulk_delete_expenses(expense_ids: list[int]):
    '''Delete multiple expenses at once. Provide a list of expense IDs.'''
    if not expense_ids:
        return {"status": "error", "message": "No expense IDs provided"}
    
    async with aiosqlite.connect(DB_PATH) as c:
        placeholders = ','.join('?' * len(expense_ids))
        cur = await c.execute(f"DELETE FROM expenses WHERE id IN ({placeholders})", expense_ids)
        await c.commit()
        deleted_count = cur.rowcount
        
        return {
            "status": "ok",
            "deleted_count": deleted_count,
            "message": f"Successfully deleted {deleted_count} expense(s)"
        }

# ==================== INCOME TOOLS ====================

@mcp.tool()
async def add_income(date: str, amount: float, source: str, note: str = ""):
    '''Add a new income entry (salary, freelance, investments, etc).'''
    async with aiosqlite.connect(DB_PATH) as c:
        cur = await c.execute(
            "INSERT INTO income(date, amount, source, note) VALUES (?,?,?,?)",
            (date, amount, source, note)
        )
        await c.commit()
        return {"status": "ok", "id": cur.lastrowid}

@mcp.tool()
async def list_income(start_date: str, end_date: str):
    '''List income entries within an inclusive date range.'''
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        cur = await c.execute(
            """
            SELECT id, date, amount, source, note
            FROM income
            WHERE date BETWEEN ? AND ?
            ORDER BY id ASC
            """,
            (start_date, end_date)
        )
        rows = await cur.fetchall()
        return [dict(row) for row in rows]

@mcp.tool()
async def get_income(income_id: int):
    '''Retrieve a single income entry by its ID.'''
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        cur = await c.execute(
            "SELECT id, date, amount, source, note FROM income WHERE id = ?",
            (income_id,)
        )
        row = await cur.fetchone()
        if row:
            return {"status": "ok", "income": dict(row)}
        else:
            return {"status": "error", "message": f"Income ID {income_id} not found"}

@mcp.tool()
async def edit_income(income_id: int, date: str = None, amount: float = None, source: str = None, note: str = None):
    '''Update an existing income entry.'''
    async with aiosqlite.connect(DB_PATH) as c:
        cur = await c.execute("SELECT id FROM income WHERE id = ?", (income_id,))
        if not await cur.fetchone():
            return {"status": "error", "message": f"Income ID {income_id} not found"}
        
        updates = []
        params = []
        
        if date is not None:
            updates.append("date = ?")
            params.append(date)
        if amount is not None:
            updates.append("amount = ?")
            params.append(amount)
        if source is not None:
            updates.append("source = ?")
            params.append(source)
        if note is not None:
            updates.append("note = ?")
            params.append(note)
        
        if not updates:
            return {"status": "error", "message": "No fields to update"}
        
        params.append(income_id)
        query = f"UPDATE income SET {', '.join(updates)} WHERE id = ?"
        await c.execute(query, params)
        await c.commit()
        
        return {"status": "ok", "message": f"Income ID {income_id} updated successfully"}

@mcp.tool()
async def delete_income(income_id: int):
    '''Delete a single income entry by its ID.'''
    async with aiosqlite.connect(DB_PATH) as c:
        cur = await c.execute("DELETE FROM income WHERE id = ?", (income_id,))
        await c.commit()
        if cur.rowcount > 0:
            return {"status": "ok", "message": f"Income ID {income_id} deleted successfully"}
        else:
            return {"status": "error", "message": f"Income ID {income_id} not found"}

@mcp.tool()
async def net_cashflow(start_date: str, end_date: str):
    '''Calculate net cashflow (income minus expenses) for a date range.'''
    async with aiosqlite.connect(DB_PATH) as c:
        cur = await c.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM income WHERE date BETWEEN ? AND ?",
            (start_date, end_date)
        )
        row = await cur.fetchone()
        total_income = row[0]
        
        cur = await c.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE date BETWEEN ? AND ?",
            (start_date, end_date)
        )
        row = await cur.fetchone()
        total_expenses = row[0]
        
        net = total_income - total_expenses
        
        return {
            "start_date": start_date,
            "end_date": end_date,
            "total_income": round(total_income, 2),
            "total_expenses": round(total_expenses, 2),
            "net_cashflow": round(net, 2),
            "status": "positive" if net >= 0 else "negative"
        }

@mcp.tool()
async def summarize_income(start_date: str, end_date: str, source: str = None):
    '''Summarize income by source within an inclusive date range.'''
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        query = (
            """
            SELECT source, SUM(amount) AS total_amount
            FROM income
            WHERE date BETWEEN ? AND ?
            """
        )
        params = [start_date, end_date]
        if source:
            query += " AND source = ?"
            params.append(source)
        query += " GROUP BY source ORDER BY source ASC"
        cur = await c.execute(query, params)
        rows = await cur.fetchall()
        return [dict(row) for row in rows]

# ==================== RESOURCES ====================

@mcp.resource("expense://categories", mime_type="application/json")
def categories():
    # Only try to read if the file exists, otherwise return empty
    if os.path.exists(CATEGORIES_PATH):
        with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return json.dumps({"error": "Categories file not found"})

@mcp.resource("info://server")
def server_info() -> str:
    """Get information about this expense tracker server"""
    info = {
        "name" : "Expense Tracker Server",
        "version" : "1.0.0",
        "tools": [
            "add_expense", "list_expenses", "get_expense", "edit_expense", 
            "delete_expense", "bulk_delete_expenses", "summarize",
            "add_income", "list_income", "get_income", "edit_income",
            "delete_income", "net_cashflow", "summarize_income"
        ],
        "author" : "Nihal"
    }
    return json.dumps(info, indent = 2)

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)