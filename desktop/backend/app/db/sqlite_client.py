import sqlite3

from app.utils.storage_paths import database_path

def get_connection():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)
