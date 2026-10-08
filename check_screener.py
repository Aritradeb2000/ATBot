import sqlite3
import pandas as pd
conn = sqlite3.connect('atbot.db')
df = pd.read_sql_query("SELECT timestamp FROM analysis_scores ORDER BY timestamp DESC LIMIT 200", conn)
df['timestamp'] = pd.to_datetime(df['timestamp'])
today_rows = df[df['timestamp'].dt.date == pd.Timestamp.now().date()]
screener_rows = today_rows[today_rows['timestamp'].dt.hour == 9]
print("Rows generated at 3:15 PM (09 UTC):", len(screener_rows))
