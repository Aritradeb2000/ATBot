import sqlite3
import pandas as pd
conn = sqlite3.connect('atbot.db')
df = pd.read_sql_query("SELECT timestamp, symbol FROM analysis_scores ORDER BY timestamp DESC LIMIT 200", conn)
df['timestamp'] = pd.to_datetime(df['timestamp'])
today_rows = df[df['timestamp'].dt.date == pd.Timestamp.now().date()]
print(today_rows['timestamp'].dt.hour.value_counts())
print(today_rows['timestamp'].dt.minute.value_counts())
