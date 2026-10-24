"""Dump the operator feedback table as CSV on stdout. Usage: python export_feedback.py data/feedback.db > feedback.csv"""
import csv
import sqlite3
import sys


def main():
    con = sqlite3.connect(sys.argv[1])
    cur = con.execute("SELECT * FROM feedback ORDER BY id")
    w = csv.writer(sys.stdout)
    w.writerow([d[0] for d in cur.description])
    w.writerows(cur)


main()
