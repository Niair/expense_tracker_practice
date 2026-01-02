from fastmcp import FastMCP
import os
import aiosqlite  # ← CHANGED: Using aiosqlite instead of sqlite3
import sqlite3
import json

DB_PATH = os.path.join(os.path.dirname(__file__), "expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

mcp = FastMCP("ExpenseTracker")

# ← CHANGED: Made init_db async and added WAL mode for better concurrency
def init_db():
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

# ← CHANGED: Call async init_db at startup
init_db()

# ==================== ORIGINAL FUNCTIONS (NOW ASYNC) ====================

@mcp.tool()
async def add_expense(date, amount, category, subcategory="", note=""):  # ← CHANGED: Added async
    '''Add a new expense entry to the database.'''
    async with aiosqlite.connect(DB_PATH) as c:  # ← CHANGED: async with aiosqlite
        cur = await c.execute(  # ← CHANGED: Added await
            "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
            (date, amount, category, subcategory, note)
        )
        await c.commit()  # ← CHANGED: Added explicit commit
        return {"status": "ok", "id": cur.lastrowid}
    
@mcp.tool()
async def list_expenses(start_date, end_date):  # ← CHANGED: Added async
    '''List expense entries within an inclusive date range.'''
    async with aiosqlite.connect(DB_PATH) as c:  # ← CHANGED: async with aiosqlite
        cur = await c.execute(  # ← CHANGED: Added await
            """
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            WHERE date BETWEEN ? AND ?
            ORDER BY id ASC
            """,
            (start_date, end_date)
        )
        rows = await cur.fetchall()  # ← CHANGED: Added await
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]

@mcp.tool()
async def summarize(start_date, end_date, category=None):  # ← CHANGED: Added async
    '''Summarize expenses by category within an inclusive date range.'''
    async with aiosqlite.connect(DB_PATH) as c:  # ← CHANGED: async with aiosqlite
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
        cur = await c.execute(query, params)  # ← CHANGED: Added await
        rows = await cur.fetchall()  # ← CHANGED: Added await
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]

# ==================== PHASE 1: CRUD OPERATIONS (NOW ASYNC) ====================

@mcp.tool()
async def get_expense(expense_id: int):  # ← CHANGED: Added async
    '''Retrieve a single expense by its ID.'''
    async with aiosqlite.connect(DB_PATH) as c:  # ← CHANGED: async with aiosqlite
        cur = await c.execute(  # ← CHANGED: Added await
            "SELECT id, date, amount, category, subcategory, note FROM expenses WHERE id = ?",
            (expense_id,)
        )
        row = await cur.fetchone()  # ← CHANGED: Added await
        if row:
            cols = [d[0] for d in cur.description]
            return {"status": "ok", "expense": dict(zip(cols, row))}
        else:
            return {"status": "error", "message": f"Expense ID {expense_id} not found"}

@mcp.tool()
async def edit_expense(expense_id: int, date=None, amount=None, category=None, subcategory=None, note=None):  # ← CHANGED: Added async
    '''Update an existing expense. Only provided fields will be updated.'''
    async with aiosqlite.connect(DB_PATH) as c:  # ← CHANGED: async with aiosqlite
        cur = await c.execute("SELECT id FROM expenses WHERE id = ?", (expense_id,))  # ← CHANGED: Added await
        if not await cur.fetchone():  # ← CHANGED: Added await
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
        await c.execute(query, params)  # ← CHANGED: Added await
        await c.commit()  # ← CHANGED: Added explicit commit
        
        return {"status": "ok", "message": f"Expense ID {expense_id} updated successfully"}

@mcp.tool()
async def delete_expense(expense_id: int):  # ← CHANGED: Added async
    '''Delete a single expense by its ID.'''
    async with aiosqlite.connect(DB_PATH) as c:  # ← CHANGED: async with aiosqlite
        cur = await c.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))  # ← CHANGED: Added await
        await c.commit()  # ← CHANGED: Added explicit commit
        if cur.rowcount > 0:
            return {"status": "ok", "message": f"Expense ID {expense_id} deleted successfully"}
        else:
            return {"status": "error", "message": f"Expense ID {expense_id} not found"}

@mcp.tool()
async def bulk_delete_expenses(expense_ids: list):  # ← CHANGED: Added async
    '''Delete multiple expenses at once. Provide a list of expense IDs.'''
    if not expense_ids:
        return {"status": "error", "message": "No expense IDs provided"}
    
    async with aiosqlite.connect(DB_PATH) as c:  # ← CHANGED: async with aiosqlite
        placeholders = ','.join('?' * len(expense_ids))
        cur = await c.execute(f"DELETE FROM expenses WHERE id IN ({placeholders})", expense_ids)  # ← CHANGED: Added await
        await c.commit()  # ← CHANGED: Added explicit commit
        deleted_count = cur.rowcount
        
        return {
            "status": "ok",
            "deleted_count": deleted_count,
            "message": f"Successfully deleted {deleted_count} expense(s)"
        }

# ==================== PHASE 2: INCOME TRACKING (NOW ASYNC) ====================

@mcp.tool()
async def add_income(date, amount, source, note=""):  # ← CHANGED: Added async
    '''Add a new income entry (salary, freelance, investments, etc).'''
    async with aiosqlite.connect(DB_PATH) as c:  # ← CHANGED: async with aiosqlite
        cur = await c.execute(  # ← CHANGED: Added await
            "INSERT INTO income(date, amount, source, note) VALUES (?,?,?,?)",
            (date, amount, source, note)
        )
        await c.commit()  # ← CHANGED: Added explicit commit
        return {"status": "ok", "id": cur.lastrowid}

@mcp.tool()
async def list_income(start_date, end_date):  # ← CHANGED: Added async
    '''List income entries within an inclusive date range.'''
    async with aiosqlite.connect(DB_PATH) as c:  # ← CHANGED: async with aiosqlite
        cur = await c.execute(  # ← CHANGED: Added await
            """
            SELECT id, date, amount, source, note
            FROM income
            WHERE date BETWEEN ? AND ?
            ORDER BY id ASC
            """,
            (start_date, end_date)
        )
        rows = await cur.fetchall()  # ← CHANGED: Added await
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]

@mcp.tool()
async def get_income(income_id: int):  # ← CHANGED: Added async
    '''Retrieve a single income entry by its ID.'''
    async with aiosqlite.connect(DB_PATH) as c:  # ← CHANGED: async with aiosqlite
        cur = await c.execute(  # ← CHANGED: Added await
            "SELECT id, date, amount, source, note FROM income WHERE id = ?",
            (income_id,)
        )
        row = await cur.fetchone()  # ← CHANGED: Added await
        if row:
            cols = [d[0] for d in cur.description]
            return {"status": "ok", "income": dict(zip(cols, row))}
        else:
            return {"status": "error", "message": f"Income ID {income_id} not found"}

@mcp.tool()
async def edit_income(income_id: int, date=None, amount=None, source=None, note=None):  # ← CHANGED: Added async
    '''Update an existing income entry. Only provided fields will be updated.'''
    async with aiosqlite.connect(DB_PATH) as c:  # ← CHANGED: async with aiosqlite
        cur = await c.execute("SELECT id FROM income WHERE id = ?", (income_id,))  # ← CHANGED: Added await
        if not await cur.fetchone():  # ← CHANGED: Added await
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
        await c.execute(query, params)  # ← CHANGED: Added await
        await c.commit()  # ← CHANGED: Added explicit commit
        
        return {"status": "ok", "message": f"Income ID {income_id} updated successfully"}

@mcp.tool()
async def delete_income(income_id: int):  # ← CHANGED: Added async
    '''Delete a single income entry by its ID.'''
    async with aiosqlite.connect(DB_PATH) as c:  # ← CHANGED: async with aiosqlite
        cur = await c.execute("DELETE FROM income WHERE id = ?", (income_id,))  # ← CHANGED: Added await
        await c.commit()  # ← CHANGED: Added explicit commit
        if cur.rowcount > 0:
            return {"status": "ok", "message": f"Income ID {income_id} deleted successfully"}
        else:
            return {"status": "error", "message": f"Income ID {income_id} not found"}

@mcp.tool()
async def net_cashflow(start_date, end_date):  # ← CHANGED: Added async
    '''Calculate net cashflow (income minus expenses) for a date range.'''
    async with aiosqlite.connect(DB_PATH) as c:  # ← CHANGED: async with aiosqlite
        cur = await c.execute(  # ← CHANGED: Added await
            "SELECT COALESCE(SUM(amount), 0) FROM income WHERE date BETWEEN ? AND ?",
            (start_date, end_date)
        )
        row = await cur.fetchone()  # ← CHANGED: Added await
        total_income = row[0]
        
        cur = await c.execute(  # ← CHANGED: Added await
            "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE date BETWEEN ? AND ?",
            (start_date, end_date)
        )
        row = await cur.fetchone()  # ← CHANGED: Added await
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
async def summarize_income(start_date, end_date, source=None):  # ← CHANGED: Added async
    '''Summarize income by source within an inclusive date range.'''
    async with aiosqlite.connect(DB_PATH) as c:  # ← CHANGED: async with aiosqlite
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
        cur = await c.execute(query, params)  # ← CHANGED: Added await
        rows = await cur.fetchall()  # ← CHANGED: Added await
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]

# ==================== RESOURCES ====================

@mcp.resource("expense://categories", mime_type="application/json")
def categories():  # ← NOTE: Resources don't need to be async
    # Read fresh each time so you can edit the file without restarting
    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        return f.read()

@mcp.resource("info://server")
def server_info() -> str:  # ← NOTE: Resources don't need to be async
    """
    Get information about this expense tracker server
    """
    info = {
        "name" : "Expense Tracker Server",
        "version" : "1.0.0",
        "description" : "Personal finance MCP server for tracking expenses and income",
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
    mcp.run(transport = "http", host = "0.0.0.0", port = 8000)