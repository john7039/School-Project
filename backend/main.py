from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
