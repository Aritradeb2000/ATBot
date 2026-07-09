import sqlite3

conn = sqlite3.connect("atbot.db")
c = conn.cursor()

outcomes = ["WIN", "LOSS"]
for day in [5, 10]:
    c.execute(
        "SELECT count(*) FROM signal_outcomes WHERE check_day=? AND outcome IN (?,?) AND technical_score IS NOT NULL",
        (day, "WIN", "LOSS")
    )
    print(f"Meta-learner eligible D{day}: {c.fetchone()[0]} rows")

print()
c.execute("SELECT meta_weight_technical, meta_weight_fundamental, meta_weight_sentiment, meta_sample_count FROM user_settings LIMIT 1")
row = c.fetchone()
print("Adaptive weights in DB:", row)

print()
c.execute("SELECT outcome, check_day, signal, symbol, technical_score, fundamental_score, sentiment_score FROM signal_outcomes WHERE outcome IN ('WIN','LOSS')")
rows = c.fetchall()
print("All WIN/LOSS rows:")
for r in rows:
    print(r)

conn.close()
