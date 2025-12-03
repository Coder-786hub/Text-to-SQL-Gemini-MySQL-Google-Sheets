# sql_generator.py
from config import GOOGLE_API_KEY, DEFAULT_GEMINI_MODEL, SYSTEM_PROMPT_DEFAULT
import google.generativeai as genai
from google.generativeai import types
import time

# configure if API key available
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

def generate_sql(question: str, schema_context: str, system_prompt: str = SYSTEM_PROMPT_DEFAULT, temperature: float = 0.7):
    """
    Call Gemini to generate SQL. Returns SQL string or raises/returns error message.
    Contains simple retry with backoff for transient quota errors.
    """
    if not GOOGLE_API_KEY:
        return "-- ERROR: GOOGLE_API_KEY not set in environment."

    MODEL = genai.GenerativeModel(DEFAULT_GEMINI_MODEL)

    full_prompt = f"""
Schema:
{schema_context}

System instructions:
{system_prompt}

Question:
{question}

Return only the SQL statement (no explanation). Make sure SQL is syntactically correct.
"""
    max_retries = 2
    backoff = 1.0
    for attempt in range(max_retries + 1):
        try:
            response = MODEL.generate_content(
                contents=full_prompt,
                generation_config=types.GenerationConfig(temperature=temperature, max_output_tokens=512)
            )
            sql = response.text.strip()
            sql = sql.replace("```sql", "").replace("```", "").strip()
            return sql
        except Exception as e:
            err_text = str(e)
            # If quota error, surface concise message rather than crash
            if "Quota" in err_text or "quota" in err_text or "429" in err_text or "ResourceExhausted" in err_text:
                # Do not retry aggressively on quota=0; just return a clear message
                return f"-- ERROR: Gemini quota or rate limit exceeded: {err_text}"
            # transient: retry
            if attempt < max_retries:
                time.sleep(backoff)
                backoff *= 2
                continue
            return f"-- ERROR: Could not generate SQL: {err_text}"
