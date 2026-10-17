"""
Logs every query/response pair to a CSV file.

This isn't just for debugging -- it's the raw data for your evaluation
chapter. After a test session (or after your volunteer students try the
system), open logs/chat_interactions.csv in Excel/pandas and you can
directly compute: intent-match rate, knowledge-base hit rate, average
response latency, and a breakdown of which queries went unanswered.

Each row carries the numeric user_id (not the name or email) so you can
tell different testers apart without storing who they are. If you collect
real student data, tell participants the queries are logged and get consent
as your ethics approval requires.
"""

import csv
import os
import time

from config import LOG_PATH


def log_interaction(
    user_id: int,
    query: str,
    intent: str,
    source: str,
    confidence: float,
    response_time_s: float,
) -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    is_new = not os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(
                ["timestamp", "user_id", "query", "intent", "source", "confidence", "response_time_s"]
            )
        writer.writerow(
            [
                time.strftime("%Y-%m-%d %H:%M:%S"),
                user_id,
                query,
                intent,
                source or "",
                round(confidence, 3),
                round(response_time_s, 3),
            ]
        )
