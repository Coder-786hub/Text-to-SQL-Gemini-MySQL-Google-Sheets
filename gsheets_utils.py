# gsheets_utils.py
import re
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from pandasql import sqldf
from typing import Tuple, Dict, Optional

def connect_google_sheet(sa_file: str, sheet_name: str) -> Tuple[gspread.Spreadsheet, gspread.Worksheet, pd.DataFrame]:
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(sa_file, scopes=scopes)
    client = gspread.authorize(creds)
    sh = client.open(sheet_name)
    ws = sh.sheet1
    df = pd.DataFrame(ws.get_all_records())
    return sh, ws, df

def get_sheet_schema_from_df(df: pd.DataFrame, sheet_name: str):
    return {sheet_name: [{"name": c, "type": str(df[c].dtype)} for c in df.columns]}

def push_df_to_sheet(ws: gspread.Worksheet, df: pd.DataFrame):
    """Push DataFrame to the worksheet (overwrite contents)."""
    if df is None:
        return
    if df.empty:
        ws.clear()
        return
    # gspread expects list of lists, first row = header
    values = [list(df.columns)]
    for _, row in df.fillna("").iterrows():
        values.append([str(x) for x in row.tolist()])
    ws.clear()
    ws.update(values)

def execute_sheet_sql_on_df(df_map: Dict[str, pd.DataFrame],
                            sql: str,
                            sheet_ws_map: Dict[str, gspread.Worksheet]) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    Execute SQL against pandas DataFrame(s) using pandasql.
    sheet_ws_map: mapping table_name -> gspread.Worksheet to push back changes.
    """
    q = sql.strip().rstrip(';')
    q_lower = q.lower()

    try:
        # SELECT
        if q_lower.startswith("select"):
            pysqldf = lambda qtext: sqldf(qtext, df_map)
            res = pysqldf(q)
            return res, None

        # INSERT INTO <table> (col, ...) VALUES (v, ...)
        if q_lower.startswith("insert into"):
            m = re.match(r"insert\s+into\s+[`\"]?([a-zA-Z0-9_\- ]+)[`\"]?\s*\(([^)]+)\)\s*values\s*\((.+)\)", q, flags=re.I)
            if not m:
                return None, "Unsupported INSERT format."
            table = m.group(1).strip()
            cols_raw = m.group(2)
            vals_raw = m.group(3)
            cols = [c.strip().strip("`\"'") for c in cols_raw.split(",")]
            vals = [v.strip().strip("'\"") for v in re.split(r',\s*(?![^()]*\))', vals_raw)]
            if table not in df_map:
                return None, f"Sheet/table '{table}' not found."
            df = df_map[table]
            if len(cols) != len(vals):
                return None, "Column count does not match value count."
            new_row = {col: None for col in df.columns}
            for c, v in zip(cols, vals):
                # preserve case as column names in df
                if c in new_row:
                    new_row[c] = v
                else:
                    new_row[c] = v
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            df_map[table] = df
            # push back
            if table in sheet_ws_map:
                try:
                    push_df_to_sheet(sheet_ws_map[table], df)
                except Exception as e:
                    return pd.DataFrame({"affected_rows": [1]}), f"Insert ok in-memory but failed to push to sheet: {e}"
            return pd.DataFrame({"affected_rows": [1]}), None

        # UPDATE (simple equality WHERE)
        if q_lower.startswith("update"):
            m = re.match(r"update\s+[`\"]?([a-zA-Z0-9_\- ]+)[`\"]?\s+set\s+(.+?)\s+where\s+(.+)", q, flags=re.I)
            if not m:
                return None, "Unsupported UPDATE format."
            table = m.group(1).strip()
            set_clause = m.group(2).strip()
            where_clause = m.group(3).strip()
            if table not in df_map:
                return None, f"Sheet/table '{table}' not found."
            df = df_map[table]
            assignments = {}
            for part in re.split(r',\s*(?![^()]*\))', set_clause):
                if '=' not in part:
                    return None, f"Invalid SET clause: {part}"
                k, v = part.split('=', 1)
                assignments[k.strip().strip("`\"'")] = v.strip().strip("'\"")
            m2 = re.match(r"([a-zA-Z0-9_`\" ]+)\s*=\s*('?\"?)(.+?)\2$", where_clause)
            if not m2:
                return None, "Unsupported WHERE clause for UPDATE (only simple equality supported)."
            where_col = m2.group(1).strip().strip("`\"'")
            where_val = m2.group(3)
            mask = df[where_col].astype(str) == where_val
            df.loc[mask, list(assignments.keys())] = pd.Series(assignments)
            df_map[table] = df
            if table in sheet_ws_map:
                try:
                    push_df_to_sheet(sheet_ws_map[table], df)
                except Exception as e:
                    return pd.DataFrame({"affected_rows": [mask.sum()]}), f"Update ok in-memory but failed to push: {e}"
            return pd.DataFrame({"affected_rows": [int(mask.sum())]}), None

        # DELETE FROM <table> WHERE col = value
        if q_lower.startswith("delete"):
            m = re.match(r"delete\s+from\s+[`\"]?([a-zA-Z0-9_\- ]+)[`\"]?\s+where\s+(.+)", q, flags=re.I)
            if not m:
                return None, "Unsupported DELETE format."
            table = m.group(1).strip()
            where_clause = m.group(2).strip()
            if table not in df_map:
                return None, f"Sheet/table '{table}' not found."
            df = df_map[table]
            m2 = re.match(r"([a-zA-Z0-9_`\" ]+)\s*=\s*('?\"?)(.+?)\2$", where_clause)
            if not m2:
                return None, "Unsupported WHERE clause for DELETE (only simple equality supported)."
            where_col = m2.group(1).strip().strip("`\"'")
            where_val = m2.group(3)
            mask = df[where_col].astype(str) == where_val
            removed = df[mask].copy()
            df_map[table] = df.loc[~mask].reset_index(drop=True)
            if table in sheet_ws_map:
                try:
                    push_df_to_sheet(sheet_ws_map[table], df_map[table])
                except Exception as e:
                    return pd.DataFrame({"affected_rows": [len(removed)]}), f"Delete ok in-memory but failed to push: {e}"
            return pd.DataFrame({"affected_rows": [len(removed)]}), None

        return None, "Unsupported SQL operation for Google Sheets handler."
    except Exception as e:
        return None, str(e)
