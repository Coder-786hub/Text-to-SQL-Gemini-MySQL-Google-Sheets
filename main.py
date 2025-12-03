# main.py
import re
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

from config import SYSTEM_PROMPT_DEFAULT, GSHEET_SERVICE_ACCOUNT_FILE
from db_utils import connect_mysql, get_mysql_schema
from gsheets_utils import connect_google_sheet, get_sheet_schema_from_df
from sql_generator import generate_sql
from query_executor import run_query

st.set_page_config("Text-to-SQL (Gemini) — MySQL + Google Sheets", layout="wide")
st.title("Text → SQL Agent (Gemini) • MySQL + Google Sheets")

# Helper to detect change in params
def params_changed(key_prefix: str, current_params: dict) -> bool:
    """Return True when any param value differs from stored value in session_state."""
    stored = st.session_state.get(key_prefix)
    return stored != current_params

# ---------------- Sidebar -----------------
with st.sidebar:
    source = st.selectbox("Data source", ["MySQL", "Google Sheets", "Both (MySQL+Sheets)"])
    temperature = st.slider("Generation temperature", 0.0, 1.0, 0.7, 0.05)
    system_prompt = st.text_area("System Prompt", value=SYSTEM_PROMPT_DEFAULT, height=220)

# ---------------- MySQL UI -----------------
mysql_conn = None
mysql_schema = {}
if source in ("MySQL", "Both (MySQL+Sheets)"):
    st.subheader("MySQL connection")
    col1, col2 = st.columns([1,2])
    with col1:
        mysql_host = st.text_input("Host", value=st.session_state.get("mysql_host", "localhost"), key="ui_mysql_host")
        mysql_port = st.number_input("Port", value=int(st.session_state.get("mysql_port", 3306)), key="ui_mysql_port")
    with col2:
        mysql_user = st.text_input("Username", value=st.session_state.get("mysql_user", "root"), key="ui_mysql_user")
        mysql_password = st.text_input("Password", type="password", value=st.session_state.get("mysql_password", ""), key="ui_mysql_password")
        mysql_db = st.text_input("Database name", value=st.session_state.get("mysql_db", ""), key="ui_mysql_db")

    mysql_params = {"host": mysql_host, "port": int(mysql_port), "user": mysql_user, "password": mysql_password, "db": mysql_db}

    # Connect once and store in session_state until params change
    if ("mysql_conn" not in st.session_state) or params_changed("mysql_conn_params", mysql_params):
        if st.button("Connect to MySQL"):
            try:
                conn = connect_mysql(mysql_host, int(mysql_port), mysql_user, mysql_password, mysql_db)
                st.session_state["mysql_conn"] = conn
                st.session_state["mysql_conn_params"] = mysql_params
                st.success("Connected to MySQL")
                # fetch schema and display
                mysql_schema = get_mysql_schema(conn)
                st.info(f"MySQL has {len(mysql_schema)} tables")
                st.write("Tables:", list(mysql_schema.keys()))
            except Exception as e:
                st.error(f"MySQL connection failed: {e}")
    else:
        # reuse existing
        mysql_conn = st.session_state.get("mysql_conn")
        try:
            mysql_schema = get_mysql_schema(mysql_conn)
            st.info(f"Using saved MySQL connection — {len(mysql_schema)} tables")
            st.write("Tables:", list(mysql_schema.keys()))
        except Exception:
            # if stored connection invalid, remove it
            st.warning("Saved MySQL connection failed; please reconnect.")
            st.session_state.pop("mysql_conn", None)
            st.session_state.pop("mysql_conn_params", None)

# ---------------- Google Sheets UI -----------------
df_map_sheets = {}
sheet_ws_map = {}
gs_df = None
worksheets = []

if source in ("Google Sheets", "Both (MySQL+Sheets)"):
    st.subheader("Google Sheets connection (Service Account)")
    gsheet_name = st.text_input("Google Sheet name", value=st.session_state.get("gsheet_name", ""), key="ui_gsheet_name")
    sa_path = st.text_input("Service account JSON path", value=st.session_state.get("gsheet_sa_path", GSHEET_SERVICE_ACCOUNT_FILE), key="ui_gsheet_sa")

    gs_params = {"sheet_name": gsheet_name, "sa_path": sa_path}

    if ("gs_sh" not in st.session_state) or params_changed("gs_params", gs_params):
        if st.button("Connect to Google Sheet"):
            try:
                sh, ws, df = connect_google_sheet(sa_path, gsheet_name)
                st.session_state["gs_sh"] = sh
                st.session_state["gs_ws"] = ws
                st.session_state["gs_df"] = df
                st.session_state["gsheet_name"] = gsheet_name
                st.session_state["gsheet_sa_path"] = sa_path
                st.session_state["gs_params"] = gs_params
                st.success("Connected to Google Sheet")
                worksheets = sh.worksheets()
                st.info(f"Total worksheets: {len(worksheets)}")
                st.write("Worksheet names:", [w.title for w in worksheets])
                st.dataframe(df.head(10))
            except Exception as e:
                st.error(f"Google Sheets connect failed: {e}")
    else:
        # reuse
        sh = st.session_state.get("gs_sh")
        ws = st.session_state.get("gs_ws")
        df = st.session_state.get("gs_df")
        if df is not None and not df.empty:
            st.info(f"Using saved Google Sheet connection — sheet: {st.session_state.get('gsheet_name')}")
            try:
                worksheets = sh.worksheets()
                st.info(f"Total worksheets: {len(worksheets)}")
                st.write("Worksheet names:", [w.title for w in worksheets])
                st.dataframe(df.head(10))
            except Exception:
                st.warning("Saved Google sheet connection seems invalid; please reconnect.")
                for k in ["gs_sh", "gs_ws", "gs_df", "gsheet_name", "gs_params", "gsheet_sa_path"]:
                    st.session_state.pop(k, None)

# Map df and ws for pandasql handlers (only if df loaded)
if "gs_df" in st.session_state and st.session_state["gs_df"] is not None:
    gs_df = st.session_state["gs_df"]
    sheet_name = st.session_state.get("gsheet_name", "Sheet1")
    safe_name = re.sub(r'\W|^(?=\d)', '_', sheet_name)
    df_map_sheets[safe_name] = gs_df.copy()
    df_map_sheets[sheet_name] = gs_df.copy()
    # prepare sheet_ws_map using worksheet object for pushing updates
    ws_obj = st.session_state.get("gs_ws")
    if ws_obj:
        sheet_ws_map[sheet_name] = ws_obj
        sheet_ws_map[safe_name] = ws_obj

# ---------------- Schema context -----------------
schema_context = ""
if mysql_schema:
    for t, cols in mysql_schema.items():
        schema_context += f"Table: {t}\n"
        for c in cols:
            schema_context += f"  - {c['name']} ({c['type']})\n"

if gs_df is not None:
    sheet_schema = get_sheet_schema_from_df(gs_df, st.session_state.get("gsheet_name", "Sheet1"))
    for t, cols in sheet_schema.items():
        schema_context += f"Table: {t}\n"
        for c in cols:
            schema_context += f"  - {c['name']} ({c['type']})\n"

# ---------------- Query & Run -----------------
st.subheader("Ask a question about your data")
user_question = st.text_area("Natural language question", height=120)

if st.button("Generate & Run"):
    if not user_question.strip():
        st.error("Please enter a question.")
    else:
        # generate SQL
        st.info("Generating SQL with Gemini...")
        sql = generate_sql(user_question, schema_context, system_prompt, temperature)
        st.code(sql, language="sql")

        # execute
        executed_df, exec_error = run_query(source, st.session_state.get("mysql_conn"), df_map_sheets, sheet_ws_map, sql)

        if exec_error:
            st.error(f"Execution error: {exec_error}")
        else:
            if executed_df is None:
                st.info("Query produced no tabular result.")
            else:
                st.subheader("Results")
                st.dataframe(executed_df)

                # If we changed sheets in-memory, already pushed in gsheets_utils; but update session_state df snapshot
                # Refresh session_state gs_df if sheet name is present
                current_sheet = st.session_state.get("gsheet_name")
                if current_sheet and current_sheet in df_map_sheets:
                    st.session_state["gs_df"] = df_map_sheets[current_sheet]

                # Ask Gemini for brief explanation (safe)
                try:
                    explanation = None
                    # Reuse generate_sql's model? Keep simple: small prompt to Gemini (but it might hit quota)
                    # Use generate_sql wrapper with low temperature; it returns error string if quota issue
                    explain_prompt = f"""You are a data analyst. The user ran this SQL:
{sql}

Here are up to first 10 rows (CSV):
{executed_df.head(10).to_csv(index=False)}

Provide a short (2-4 sentence) plain-English summary of what the results show. Return only the summary."""
                    explanation = generate_sql(explain_prompt, "", system_prompt, temperature=0.2)
                    if explanation.startswith("-- ERROR:"):
                        st.warning("Could not obtain explanation from Gemini: " + explanation)
                    else:
                        st.success("Explanation")
                        st.write(explanation)
                except Exception as e:
                    st.warning(f"Could not obtain explanation: {e}")

st.markdown("---")
st.markdown("**Notes & limitations**")
st.markdown("""
- Google Sheets write-back overwrites the sheet with current DataFrame contents. Use caution.
- INSERT/UPDATE/DELETE support for Sheets uses simple parsing and supports common simple cases.
- Gemini generation may be rate-limited by Google Cloud quotas; the app surfaces errors from the API instead of crashing.
""")
