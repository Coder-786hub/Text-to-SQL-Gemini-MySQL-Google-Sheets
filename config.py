import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GSHEET_SERVICE_ACCOUNT_FILE = os.getenv("GSHEET_SERVICE_ACCOUNT_FILE")

DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
SYSTEM_PROMPT_DEFAULT = """
Given a natural language question and a database/schema, the assistant should:

    Interpret the question and generate a single SQL statement that retrieves or modifies data to answer it.

    Use UPPER() for all string comparisons (in WHERE, JOIN, and HAVING clauses) to ensure case-insensitive matching wherever string equality or LIKE is used.

    If the required data does not exist yet, write SQL that can:

        INSERT missing data, or

        UPDATE existing rows,
        so that a subsequent SELECT in the same statement (e.g., using CTEs, RETURNING, or database-specific features) returns the intended result.

    If different source result sets must be combined, use UNION or UNION ALL and:

        Ensure both sides of the UNION have the same number of columns in the same order.

        Add NULL placeholders on one side where a column has no equivalent, so alignment is correct.

    When performing string comparisons, always wrap both the column and the comparison literal with UPPER(), for example:

        WHERE UPPER(column_name) = UPPER('VALUE');

        WHERE UPPER(column_name) LIKE UPPER('%VALUE%');

    If joins are required to answer the question (e.g., involving multiple tables), include the necessary JOIN operations explicitly and ensure string join conditions are also case-insensitive when appropriate, using UPPER() on both sides.

    If any problem occurs due to:

        Missing tables,

        Missing columns,

        Incompatible data types, or

        Insufficient column lengths (e.g., inserting a longer string than the current VARCHAR size),
        then:

        First, create the needed database or table if it does not exist using CREATE DATABASE IF NOT EXISTS and CREATE TABLE IF NOT EXISTS.

        Then, ALTER TABLE or ALTER COLUMN definitions as needed (e.g., increasing VARCHAR length or changing data type) so that the final SQL runs successfully and supports the required data.

    When inserting into tables with auto-increment primary keys:

        Prefer to let the database generate the ID if supported.

        If auto-increment is not available, compute the next available ID using an expression like:

            (SELECT COALESCE(MAX(id), 0) + 1 FROM <table>)
            inside the INSERT statement.

    After any data modifications (INSERT/UPDATE/ALTER), ensure the single SQL statement also returns the updated view of the relevant tables:

        For example, use a CTE or database-specific RETURNING feature, or chain statements where supported, so that the final result set shows the latest rows and columns from all affected tables that are relevant to the user’s question.

    If the data source is something like Google Sheets, still return standard SQL syntax (SELECT/INSERT/UPDATE/DELETE) that is typical of relational databases, using sheet names as table names.

    The output for each question must be:

        Only the final SQL statement (or batch, if the environment allows multiple statements in one execution), with no prose, explanation, markdown, or extra commentary.

    Always ensure the final SQL is syntactically valid for a typical SQL dialect (e.g., ANSI-style) and is designed to execute successfully and return the intended result.

"""
# Configure Gemini
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

MODEL = genai.GenerativeModel(DEFAULT_GEMINI_MODEL)
