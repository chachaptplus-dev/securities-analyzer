import duckdb, sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
from src.extractor import _infer_sentiment

con = duckdb.connect("data/securities.duckdb")
rows = con.execute(
    "SELECT id, thesis FROM reports "
    "WHERE rating_normalized = 'UNKNOWN' AND thesis IS NOT NULL AND length(thesis) >= 50"
).fetchall()
print(f"UNKNOWN rows with thesis: {len(rows)}")

counts = {"POSITIVE": 0, "NEUTRAL": 0, "NEGATIVE": 0, "UNKNOWN": 0}
for row_id, thesis in rows:
    sentiment = _infer_sentiment(thesis)
    counts[sentiment] += 1
    if sentiment != "UNKNOWN":
        con.execute("UPDATE reports SET rating_normalized = ? WHERE id = ?", [sentiment, row_id])

print(f"POSITIVE={counts['POSITIVE']}  NEUTRAL={counts['NEUTRAL']}  NEGATIVE={counts['NEGATIVE']}  still-UNKNOWN={counts['UNKNOWN']}")
print()
print("Final distribution:")
for r, c in con.execute("SELECT rating_normalized, COUNT(*) FROM reports GROUP BY 1 ORDER BY 2 DESC").fetchall():
    print(f"  {str(r):<12} {c}")
con.close()
