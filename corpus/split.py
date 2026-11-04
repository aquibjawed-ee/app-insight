"""Corpus split (design 7.2, 7.5): held-out by a fixed hash of the repository URL, decided before labelling.

A repository is held out when the SHA-256 of its normalised URL (lower case, no trailing `.git` or `/`) is odd.
A held-out repository that was inspected to make a fix moves to tuning, and the manifest records why.
Usage: python3 corpus/split.py corpus/corpus-v1.csv   (prints each row's hash split; --check fails on a mismatch)
"""
import csv
import hashlib
import sys


def normalise(url):
    u = url.strip().lower()
    u = u[:-1] if u.endswith("/") else u
    return u[:-4] if u.endswith(".git") else u


def by_hash(url):
    return "held-out" if int(hashlib.sha256(normalise(url).encode()).hexdigest(), 16) % 2 else "tuning"


def check(path):
    bad = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            want = by_hash(row["url"])
            if row["split"] != want and not (row["split"] == "tuning" and row["moved_to_tuning"].strip()):
                bad.append("%s: split %s, hash says %s, no reason recorded" % (row["url"], row["split"], want))
    return bad


if __name__ == "__main__":
    bad = check(sys.argv[-1])
    for b in bad:
        print(b)
    sys.exit(1 if bad and "--check" in sys.argv else 0)
