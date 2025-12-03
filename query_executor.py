# query_executor.py
from db_utils import execute_mysql_query
from gsheets_utils import execute_sheet_sql_on_df

def run_query(source, mysql_conn, df_map_sheets, sheet_ws_map, sql):
    """
    Run SQL against selected source. Returns (df, error)
    sheet_ws_map: mapping used when running against Sheets (to push updates)
    """
    if source == "MySQL":
        return execute_mysql_query(mysql_conn, sql)

    if source == "Google Sheets":
        return execute_sheet_sql_on_df(df_map_sheets, sql, sheet_ws_map)

    if source == "Both (MySQL+Sheets)":
        # try mysql first
        if mysql_conn:
            df, err = execute_mysql_query(mysql_conn, sql)
            if err is None:
                return df, None
            # else try sheets fallback
        return execute_sheet_sql_on_df(df_map_sheets, sql, sheet_ws_map)

    return None, "Invalid data source"
