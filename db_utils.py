# db_utils.py
import mysql.connector
import pandas as pd
from typing import Tuple, Optional, Dict, Any

def connect_mysql(host: str, port: int, user: str, password: str, database: str):
    """Return a mysql.connector connection or raise error."""
    conn = mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        autocommit=False,
        charset='utf8mb4'
    )
    return conn

def get_mysql_schema(conn) -> Dict[str, list]:
    """Return dict {table: [{name,type}, ...]}"""
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    schema = {}
    for (table,) in tables:
        cursor.execute(f"DESCRIBE `{table}`")
        cols = cursor.fetchall()
        schema[table] = [{"name": col[0], "type": col[1]} for col in cols]
    cursor.close()
    return schema

def execute_mysql_query(conn, query: str) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Execute query on MySQL. Returns (DataFrame or None, error message or None)."""
    try:
        cursor = conn.cursor()
        q = query.strip().rstrip(';')
        if q.lower().startswith("select"):
            df = pd.read_sql(q, conn)
            return df, None
        else:
            cursor.execute(q)
            conn.commit()
            return pd.DataFrame({"affected_rows": [cursor.rowcount]}), None
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return None, str(e)
