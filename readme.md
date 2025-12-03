# Text-to-SQL Agent (MySQL + Google Sheets + Gemini)

A Streamlit-based application that converts natural language text into SQL queries using **Google Gemini LLM**, and executes queries on **MySQL** or **Google Sheets**. Users can view, insert, update, or delete data interactively.

---

## Features

- Convert natural language questions into SQL queries using Gemini LLM.
- Connect and query **MySQL databases**.
- Connect and query **Google Sheets** as a database.
- Execute SELECT, INSERT, UPDATE, DELETE operations.
- Naive SQL handling for Google Sheets (via pandasql + in-memory DataFrame).
- Push updates back to Google Sheets automatically.
- Optionally get a **short summary of results** using Gemini.
- Single interface for both MySQL and Google Sheets queries.
- Easy configuration via environment variables or service account JSON.

---

## Screenshots

### Login / Connection
![Screenshot 1](sc1.png)

### MySQL Connection
![Screenshot 2](sc2.png)

### Google Sheets Connection
![Screenshot 3](sc3.png)

### Query Execution
![Screenshot 4](sc4.png)

---

## Video Demo

[![Project Demo](vd1.gif)](vd1.mp4)

> Click on the video thumbnail to watch the demo.

---

## Requirements

- Python 3.10+
- Packages:

```bash
pip install streamlit mysql-connector-python gspread google-auth google-auth-oauthlib google-auth-httplib2 google-generativeai pandas pandasql
