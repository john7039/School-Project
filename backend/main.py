from fastapi import FastAPI
import sqlite3

app = FastAPI()

def get_db():
    conn = sqlite3.connect("econ.db")
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/api/prices")
def list_prices():
    conn = get_db()
    rows = conn.execute("SELECT * FROM prices").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/indicators")
def list_indicators():
    conn = get_db()
    rows = conn.execute("SELECT * FROM indicators").fetchall()
    conn.close()
    return [dict(r) for r in rows]
