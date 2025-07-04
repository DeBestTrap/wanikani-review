from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys
from typing import Iterable, List, Set

import requests
from dotenv import load_dotenv

WK_API_URL = "https://api.wanikani.com/v2"
CHUNK = 1000  # max IDs per `subjects` call

class ReviewEndpointDown(Exception):
    """Raised when the reviews endpoint is unavailable (HTTP 5xx or timeout)."""


def iso_now_minus(minutes: int) -> str:
    then = dt.datetime.utcnow() - dt.timedelta(minutes=minutes)
    return then.replace(microsecond=0).isoformat() + "Z"


def fetch_paginated(url: str, headers: dict) -> Iterable[dict]:
    while url:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code >= 500:
            raise ReviewEndpointDown(resp.text)
        resp.raise_for_status()
        payload = resp.json()
        yield from payload["data"]
        url = payload["pages"]["next_url"]


def chunked(seq: List[int], size: int = CHUNK) -> Iterable[List[int]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def gather_vocab_subjects(subject_ids: Set[int], headers: dict) -> List[str]:
    vocab: List[str] = []
    for batch in chunked(list(subject_ids)):
        ids_str = ",".join(map(str, batch))
        url = f"{WK_API_URL}/subjects?ids={ids_str}"
        for subj in fetch_paginated(url, headers):
            # vocab.append(subj["data"]["slug"])
            if subj["object"] == "vocabulary":
                vocab.append(subj["data"]["slug"])
    return sorted(set(vocab), key=str.lower)


def recent_subject_ids_via_reviews(since: str, headers: dict) -> Set[int]:
    url = f"{WK_API_URL}/reviews?updated_after={since}"
    return {rev["data"]["subject_id"] for rev in fetch_paginated(url, headers)}


def recent_subject_ids_via_assignments(since: str, headers: dict) -> Set[int]:
    url = f"{WK_API_URL}/assignments?updated_after={since}"
    ids: Set[int] = set()
    for asg in fetch_paginated(url, headers):
        # keep only assignments actually reviewed in the window (updated_at ≥ since)
        # if asg["data"]["updated_at"] >= since:
        ids.add(asg["data"]["subject_id"])
    return ids


def dump_list(words: List[str], path: str | None) -> None:
    if not path:
        print("\n".join(words))
        return
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        with open(path, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerows([[w] for w in ["vocabulary", *words]])
    else:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(words))
    print(f"Wrote {len(words)} vocab ⇒ {path}", file=sys.stderr)


def get_vocab(minutes: int = 30, api_token: str = "") -> List[str]:
    token: str | None = api_token or os.getenv("WANIKANI_API_TOKEN")
    if not token:
        print(
            "API token required via --api-token or WANIKANI_API_TOKEN env var",
            file=sys.stderr,
        )
        sys.exit(1)

    since = iso_now_minus(minutes)
    headers = {"Authorization": f"Bearer {token}"}

    # Get subject IDs from recent reviews
    try:
        ids = recent_subject_ids_via_assignments(since, headers)
    except ReviewEndpointDown as e:
        print("Reviews endpoint down", file=sys.stderr)
        raise ReviewEndpointDown(e)

    if not ids:
        print("No recent reviews found", file=sys.stderr)
        raise Exception("No recent reviews found")

    # Fetch vocab subjects for those IDs
    vocab = gather_vocab_subjects(ids, headers)
    if not vocab:
        print("No vocabulary among those reviews", file=sys.stderr)
        raise Exception("No vocabulary among those reviews")

    return vocab


def main() -> List[str] | None:
    p = argparse.ArgumentParser(
        description="Dump recently-reviewed vocab from WaniKani."
    )
    p.add_argument(
        "-k", "--api-token", help="WaniKani API token (or env WANIKANI_API_TOKEN)"
    )
    p.add_argument(
        "-m", "--minutes", type=int, default=30, help="Look back this many minutes"
    )
    p.add_argument("-o", "--out", help="Output file (.txt or .csv). Omit → stdout")
    args = p.parse_args()

    load_dotenv()
    token = args.token or os.getenv("WANIKANI_API_TOKEN")
    if not token:
        p.error("API token required via --api-token or WANIKANI_API_TOKEN env var")

    vocab = get_vocab(args.minutes, token)
    if vocab is not None:
        dump_list(vocab, args.out)


if __name__ == "__main__":
    main()
