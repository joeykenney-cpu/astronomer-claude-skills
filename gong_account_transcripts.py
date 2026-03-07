#!/usr/bin/env python3
"""
Gong Account Transcript Fetcher

Two-tier cache architecture:
1. Global call index: Slim records (id, title, date, crm_account_name, external_emails).
   Built once, then incremental updates take seconds. ~10x smaller than full API response.
2. Per-account transcripts: Fetched on-demand for matched calls, cached per account.

Usage:
    python gong_account_transcripts.py "Third Point" --stdout
    python gong_account_transcripts.py "Pretto" --months 6 --stdout
    python gong_account_transcripts.py "" --list-accounts
    python gong_account_transcripts.py --sync              # Incremental update only
    python gong_account_transcripts.py "Acme" --no-cache --stdout
    python gong_account_transcripts.py "Acme" --refresh-cache --stdout
"""

import os
import sys
import json
import argparse
import time
from datetime import datetime, timedelta, timezone
from base64 import b64encode
from pathlib import Path
from typing import Optional

import requests

# --- Config ---
ACCESS_KEY = os.environ.get("GONG_ACCESS_KEY", "")
SECRET_KEY = os.environ.get("GONG_SECRET_KEY", "")
BASE_URL = "https://api.gong.io/v2"
OUTPUT_DIR = Path(os.environ.get("GONG_OUTPUT_DIR", os.path.expanduser("~/claude-work")))
DEFAULT_CACHE_DIR = Path(os.path.expanduser("~/claude-work/gong-cache"))
DEFAULT_ACCOUNTS_OUTPUT_DIR = Path(os.path.expanduser("~/claude-work/research-assistant/outputs/accounts"))
RATE_LIMIT_DELAY = 0.35  # ~3 req/sec
CACHE_VERSION = 3
ALL_TIME_START = "2015-01-01T00:00:00Z"

if not ACCESS_KEY or not SECRET_KEY:
    print("Error: GONG_ACCESS_KEY and GONG_SECRET_KEY env vars required.")
    sys.exit(1)

auth_string = b64encode(f"{ACCESS_KEY}:{SECRET_KEY}".encode()).decode()
HEADERS = {
    "Authorization": f"Basic {auth_string}",
    "Content-Type": "application/json",
}


# --- API helpers ---

def api_post(endpoint: str, body: dict) -> dict:
    """POST request with rate limiting."""
    time.sleep(RATE_LIMIT_DELAY)
    resp = requests.post(f"{BASE_URL}{endpoint}", headers=HEADERS, json=body)
    resp.raise_for_status()
    return resp.json()


def api_get(endpoint: str, params: dict = None) -> dict:
    """GET request with rate limiting."""
    time.sleep(RATE_LIMIT_DELAY)
    resp = requests.get(f"{BASE_URL}{endpoint}", headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()


def slim_call_record(call: dict) -> dict:
    """Extract the minimal fields needed for account matching from a full API call object."""
    meta = call.get("metaData", {})
    crm_name = _get_crm_account_name_from_context(call)
    external_emails = [
        p["emailAddress"]
        for p in call.get("parties", [])
        if (p.get("affiliation") or "").lower() == "external" and p.get("emailAddress")
    ]
    return {
        "id": meta.get("id"),
        "started": meta.get("started"),
        "title": meta.get("title"),
        "url": meta.get("url"),
        "duration": meta.get("duration"),
        "crm_account_name": crm_name,
        "external_emails": external_emails,
    }


def fetch_calls_extensive(from_date: str, to_date: str, quiet: bool = False) -> list:
    """Fetch all calls with CRM context + parties, returning slim index records."""
    slim_calls = []
    cursor = None
    page = 0

    while True:
        body = {
            "filter": {
                "fromDateTime": from_date,
                "toDateTime": to_date,
            },
            "contentSelector": {
                "context": "Extended",
                "exposedFields": {
                    "parties": True,
                    "content": {
                        "structure": False,
                        "topics": False,
                        "trackers": False,
                    },
                },
            },
        }
        if cursor:
            body["cursor"] = cursor

        data = api_post("/calls/extensive", body)
        calls = data.get("calls", [])
        slim_calls.extend(slim_call_record(c) for c in calls)

        cursor = data.get("records", {}).get("cursor")
        page += 1
        if not quiet:
            print(f"  Page {page}: fetched {len(calls)} calls (total: {len(slim_calls)})")

        if not cursor:
            break

    return slim_calls


def fetch_call_details(call_ids: list) -> list:
    """Fetch full call objects (parties + CRM context) for a specific set of call IDs."""
    all_calls = []
    batch_size = 50

    for i in range(0, len(call_ids), batch_size):
        batch = call_ids[i:i + batch_size]
        data = api_post("/calls/extensive", {
            "filter": {"callIds": batch},
            "contentSelector": {
                "context": "Extended",
                "exposedFields": {
                    "parties": True,
                    "content": {"structure": False, "topics": False, "trackers": False},
                },
            },
        })
        all_calls.extend(data.get("calls", []))

    return all_calls


# --- Global call index cache ---

def get_cache_dir(args) -> Path:
    return Path(args.cache_dir) if args.cache_dir else DEFAULT_CACHE_DIR


def load_global_index(cache_dir: Path) -> tuple:
    """Load the global call index. Returns (metadata, calls) or (None, None)."""
    meta_path = cache_dir / "all_calls" / "metadata.json"
    calls_path = cache_dir / "all_calls" / "calls.json"

    if not meta_path.exists() or not calls_path.exists():
        return None, None

    with open(meta_path) as f:
        metadata = json.load(f)

    if metadata.get("cache_version") != CACHE_VERSION:
        print("  Global cache version mismatch, will rebuild.")
        return None, None

    with open(calls_path) as f:
        calls = json.load(f)

    return metadata, calls


def save_global_index(cache_dir: Path, calls: list, from_date: str, to_date: str):
    """Save the global call index."""
    index_dir = cache_dir / "all_calls"
    index_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "last_fetched": datetime.now(timezone.utc).isoformat(),
        "from_date": from_date,
        "to_date": to_date,
        "total_calls": len(calls),
        "cache_version": CACHE_VERSION,
    }

    with open(index_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    with open(index_dir / "calls.json", "w") as f:
        json.dump(calls, f, default=str)

    print(f"  Saved global index: {len(calls)} calls.")


GITHUB_REPO = "joeykenney-cpu/Gong-transcript-search-skill"
GITHUB_RELEASE_TAG = "v1.0.0"


def download_seed_cache(cache_dir: Path) -> bool:
    """Download pre-built global cache from GitHub release. Returns True on success."""
    import gzip
    import shutil

    index_dir = cache_dir / "all_calls"
    if (index_dir / "calls.json").exists():
        return False

    print("  No local cache found. Downloading pre-built cache from GitHub release...")
    base_url = f"https://github.com/{GITHUB_REPO}/releases/download/{GITHUB_RELEASE_TAG}"

    try:
        index_dir.mkdir(parents=True, exist_ok=True)

        for filename in ["gong-cache-calls.json.gz", "gong-cache-metadata.json.gz"]:
            url = f"{base_url}/{filename}"
            print(f"  Downloading {filename}...")
            resp = requests.get(url, stream=True, timeout=120)
            resp.raise_for_status()

            gz_path = index_dir / filename
            with open(gz_path, "wb") as f:
                shutil.copyfileobj(resp.raw, f)

            # Decompress
            out_name = filename.replace("gong-cache-", "").replace(".gz", "")
            with gzip.open(gz_path, "rb") as f_in, open(index_dir / out_name, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

            gz_path.unlink()

        print(f"  Cache downloaded and extracted to {index_dir}")
        return True

    except Exception as e:
        print(f"  Failed to download cache: {e}")
        print("  Will build from API instead (this takes ~40 min).")
        return False


def get_or_build_global_index(cache_dir: Path, no_cache: bool = False, refresh: bool = False, quiet: bool = False) -> list:
    """Get global call index, building or updating as needed."""
    if no_cache:
        print("Fetching all calls (no cache)...")
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return fetch_calls_extensive(ALL_TIME_START, now_str, quiet=quiet)

    # Try downloading seed cache if no local cache exists
    download_seed_cache(cache_dir)

    metadata, cached_calls = load_global_index(cache_dir)

    if metadata and cached_calls is not None and not refresh:
        print(f"  Global index: {metadata['total_calls']} calls (last updated: {metadata['last_fetched'][:16]})")

        # Incremental update: fetch calls since last_fetched with 1-day overlap
        last_dt = datetime.fromisoformat(metadata["last_fetched"].replace("Z", "+00:00"))
        overlap_dt = last_dt - timedelta(days=1)
        incremental_from = overlap_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        print(f"  Checking for new calls since {incremental_from[:10]}...")
        new_calls = fetch_calls_extensive(incremental_from, now_str, quiet=quiet)

        if new_calls:
            # Dedup by call ID
            existing_ids = {c.get("id") for c in cached_calls}
            truly_new = [c for c in new_calls if c.get("id") not in existing_ids]

            if truly_new:
                print(f"  Found {len(truly_new)} new calls.")
                cached_calls.extend(truly_new)
            else:
                print(f"  No new calls.")

        save_global_index(cache_dir, cached_calls, ALL_TIME_START, now_str)
        return cached_calls

    # Full build
    print("Building global call index (first time — this takes a while)...")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    all_calls = fetch_calls_extensive(ALL_TIME_START, now_str, quiet=quiet)
    save_global_index(cache_dir, all_calls, ALL_TIME_START, now_str)
    return all_calls


# --- Email fetching ---

def fetch_account_emails(external_emails: list, from_date: str, to_date: str) -> tuple:
    """
    Fetch email history for an account from Gong's email API.
    Returns (emails, status_message).
    Gracefully handles 404 (integration not configured) and other errors.
    """
    if not external_emails:
        return [], "No external email addresses to filter by."

    # Gong email API: POST /v2/emails with filter
    body = {
        "filter": {
            "fromDateTime": from_date,
            "toDateTime": to_date,
            "emailAddresses": external_emails[:20],  # cap to avoid overly broad queries
        }
    }

    try:
        time.sleep(RATE_LIMIT_DELAY)
        resp = requests.post(f"{BASE_URL}/emails", headers=HEADERS, json=body)

        if resp.status_code == 404:
            return [], "Email integration not available (endpoint not found — likely not configured in this Gong workspace)."
        if resp.status_code == 403:
            return [], "Email integration not accessible (insufficient API permissions)."
        if resp.status_code == 400:
            return [], f"Email API returned bad request: {resp.text[:200]}"

        resp.raise_for_status()
        data = resp.json()
        emails = data.get("emails", data.get("emailMessages", []))
        return emails, f"Found {len(emails)} emails."

    except requests.exceptions.HTTPError as e:
        return [], f"Email API unavailable: HTTP {e.response.status_code}"
    except Exception as e:
        return [], f"Email fetch skipped: {e}"


def format_email(email: dict) -> str:
    """Format a single email record as readable text."""
    lines = []
    date = (email.get("sentAt") or email.get("date") or email.get("time") or "")[:16]
    direction = email.get("direction", "")
    subject = email.get("subject") or email.get("emailSubject") or "(no subject)"
    from_addr = email.get("fromAddress") or email.get("from") or ""
    to_addrs = email.get("toAddresses") or email.get("to") or []
    if isinstance(to_addrs, str):
        to_addrs = [to_addrs]
    body_text = email.get("body") or email.get("bodyText") or email.get("snippet") or ""

    lines.append(f"**Date**: {date}  **Direction**: {direction}")
    lines.append(f"**Subject**: {subject}")
    if from_addr:
        lines.append(f"**From**: {from_addr}")
    if to_addrs:
        lines.append(f"**To**: {', '.join(to_addrs)}")
    if body_text:
        lines.append(f"\n{body_text.strip()[:1000]}")
    return "\n".join(lines)


# --- Per-account transcript cache ---

def account_slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace(".", "").replace(",", "").replace("/", "_")


def get_account_gong_dir(slug: str) -> Path:
    """Returns the per-account Gong cache dir inside the account's output folder."""
    return DEFAULT_ACCOUNTS_OUTPUT_DIR / slug / "gong"


def load_account_transcripts(cache_dir: Path, slug: str) -> tuple:
    """Load cached transcripts for an account. Returns (metadata, transcripts) or (None, None)."""
    acct_dir = get_account_gong_dir(slug)
    meta_path = acct_dir / "metadata.json"
    trans_path = acct_dir / "transcripts.json"

    if not meta_path.exists() or not trans_path.exists():
        return None, None

    with open(meta_path) as f:
        metadata = json.load(f)

    with open(trans_path) as f:
        transcripts = json.load(f)

    return metadata, transcripts


def save_account_transcripts(cache_dir: Path, slug: str, account_name: str,
                              call_ids: list, transcripts: list,
                              emails: list = None, email_status: str = ""):
    """Save transcripts (and optionally emails) for an account."""
    acct_dir = get_account_gong_dir(slug)
    acct_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "account_name": account_name,
        "last_fetched": datetime.now(timezone.utc).isoformat(),
        "call_count": len(call_ids),
        "call_ids": call_ids,
        "email_count": len(emails) if emails else 0,
        "email_status": email_status,
        "cache_version": CACHE_VERSION,
    }

    with open(acct_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    with open(acct_dir / "transcripts.json", "w") as f:
        json.dump(transcripts, f, default=str)

    if emails is not None:
        with open(acct_dir / "emails.json", "w") as f:
            json.dump(emails, f, default=str)

    print(f"  Cached {len(transcripts)} transcripts for '{account_name}'."
          + (f" {len(emails)} emails." if emails else ""))


def load_account_call_details(cache_dir: Path, slug: str) -> Optional[dict]:
    """Load cached call details for an account. Returns {call_id: detail} or None."""
    details_path = get_account_gong_dir(slug) / "call_details.json"
    if not details_path.exists():
        return None
    with open(details_path) as f:
        return json.load(f)


def save_account_call_details(cache_dir: Path, slug: str, call_details_by_id: dict):
    """Save call details cache for an account."""
    acct_dir = get_account_gong_dir(slug)
    acct_dir.mkdir(parents=True, exist_ok=True)
    with open(acct_dir / "call_details.json", "w") as f:
        json.dump(call_details_by_id, f, default=str)


def load_account_emails(cache_dir: Path, slug: str) -> tuple:
    """Load cached emails for an account. Returns (emails, status) or (None, None)."""
    emails_path = get_account_gong_dir(slug) / "emails.json"
    meta_path = get_account_gong_dir(slug) / "metadata.json"

    if not emails_path.exists():
        return None, None

    with open(emails_path) as f:
        emails = json.load(f)

    status = ""
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)
        status = meta.get("email_status", "")

    return emails, status


# --- Call matching (operates on slim index records) ---

def filter_calls_by_account(calls: list, account_name: str, domain: str = None) -> list:
    matched = []
    account_lower = account_name.lower()

    for call in calls:
        # Primary: pre-extracted CRM account name
        crm_name = call.get("crm_account_name") or ""
        if crm_name and account_lower in crm_name.lower():
            matched.append(call)
            continue

        # Fallback 1: call title
        title = (call.get("title") or "").lower()
        if account_lower in title:
            matched.append(call)
            continue

        # Fallback 2: external email domain
        if domain:
            domain_lower = domain.lower()
            for email in call.get("external_emails", []):
                if domain_lower in email.lower():
                    matched.append(call)
                    break

    return matched


# --- CRM context helpers (operate on full call detail objects) ---

def _get_crm_account_name_from_context(call: dict) -> Optional[str]:
    for ctx in call.get("context", []):
        for obj in ctx.get("objects", []):
            if obj.get("objectType") == "Account":
                for field in obj.get("fields", []):
                    if field.get("name") == "Name":
                        return field.get("value")
    return None


def get_crm_account_info(call: dict) -> dict:
    info = {}
    for ctx in call.get("context", []):
        for obj in ctx.get("objects", []):
            if obj.get("objectType") == "Account":
                info["salesforce_id"] = obj.get("objectId")
                for field in obj.get("fields", []):
                    info[field.get("name", "")] = field.get("value")
            elif obj.get("objectType") == "Opportunity":
                if "opportunities" not in info:
                    info["opportunities"] = []
                opp = {"salesforce_id": obj.get("objectId")}
                for field in obj.get("fields", []):
                    opp[field.get("name", "")] = field.get("value")
                info["opportunities"].append(opp)
    return info


# --- Transcript fetching ---

def get_transcripts(call_ids: list) -> list:
    all_transcripts = []
    batch_size = 20

    for i in range(0, len(call_ids), batch_size):
        batch = call_ids[i : i + batch_size]
        print(f"  Fetching transcripts batch {i // batch_size + 1} ({len(batch)} calls)...")
        data = api_post("/calls/transcript", {"filter": {"callIds": batch}})
        all_transcripts.extend(data.get("callTranscripts", []))

    return all_transcripts


# --- Output formatting ---

def build_speaker_map(call_details: list) -> dict:
    """Build speakerId -> info map from full call detail objects."""
    speaker_map = {}
    for call in call_details:
        for party in call.get("parties", []):
            sid = party.get("speakerId")
            if sid:
                speaker_map[sid] = {
                    "name": party.get("name", "Unknown"),
                    "email": party.get("emailAddress", ""),
                    "title": party.get("title", ""),
                    "affiliation": party.get("affiliation", ""),
                }
    return speaker_map


def format_transcript(transcript: dict, speaker_map: dict) -> str:
    lines = []
    for segment in transcript.get("transcript", []):
        speaker_id = segment.get("speakerId")
        speaker_info = speaker_map.get(speaker_id, {})
        speaker_name = speaker_info.get("name", f"Speaker {speaker_id}")
        topic = segment.get("topic")

        if topic:
            lines.append(f"\n--- {topic} ---\n")

        for sentence in segment.get("sentences", []):
            lines.append(f"[{speaker_name}]: {sentence.get('text', '')}")

    return "\n".join(lines)


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Fetch Gong call transcripts for an account")
    parser.add_argument("account_name", nargs="?", default="", help="Account/company name to search for")
    parser.add_argument("--domain", help="Email domain fallback filter (e.g., 'acme.com')")
    parser.add_argument("--months", type=int, help="Limit to last N months of calls")
    parser.add_argument("--from-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to-date", help="End date (YYYY-MM-DD)")
    parser.add_argument("--no-cache", action="store_true", help="Bypass all caches, fetch fresh from API")
    parser.add_argument("--refresh-cache", action="store_true", help="Force full rebuild of global call index")
    parser.add_argument("--cache-dir", help=f"Override cache directory (default: {DEFAULT_CACHE_DIR})")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--format", choices=["json", "text", "both"], default="both", help="Output format")
    parser.add_argument("--stdout", action="store_true", help="Print markdown to stdout instead of saving files")
    parser.add_argument("--list-accounts", action="store_true", help="List all unique CRM account names and exit")
    parser.add_argument("--sync", action="store_true", help="Just sync the global call index (no account query)")

    args = parser.parse_args()

    cache_dir = get_cache_dir(args)

    # --- Get or build global call index (slim records) ---
    print("Loading global call index...")
    all_calls = get_or_build_global_index(
        cache_dir,
        no_cache=args.no_cache,
        refresh=args.refresh_cache,
    )
    print(f"  Total calls in index: {len(all_calls)}\n")

    # Sync-only mode
    if args.sync:
        print("Sync complete.")
        return

    # List accounts mode
    if args.list_accounts:
        account_names = set()
        for call in all_calls:
            name = call.get("crm_account_name")
            if name:
                account_names.add(name)
        print(f"Found {len(account_names)} unique CRM accounts:\n")
        for name in sorted(account_names):
            print(f"  {name}")
        return

    if not args.account_name:
        print("Error: account name required (or use --list-accounts / --sync).")
        sys.exit(1)

    # --- Filter by account (slim records) ---
    print(f"Filtering for '{args.account_name}'...")
    account_calls = filter_calls_by_account(all_calls, args.account_name, args.domain)

    # Apply date filter if specified
    if args.from_date or args.months or args.to_date:
        to_date = args.to_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if args.from_date:
            from_date = args.from_date
        elif args.months:
            from_dt = datetime.now(timezone.utc) - timedelta(days=args.months * 30)
            from_date = from_dt.strftime("%Y-%m-%d")
        else:
            from_date = "2015-01-01"

        from_iso = f"{from_date}T00:00:00Z"
        to_iso = f"{to_date}T23:59:59Z"

        pre = len(account_calls)
        account_calls = [
            c for c in account_calls
            if from_iso <= (c.get("started") or "") <= to_iso
        ]
        if len(account_calls) != pre:
            print(f"  Date filter ({from_date} to {to_date}): {len(account_calls)} of {pre} calls")

    print(f"  Matched calls: {len(account_calls)}\n")

    if not account_calls:
        print("No calls found for this account.")
        print("\nTip: Run with --list-accounts to see all CRM account names:")
        print(f"  python {sys.argv[0]} --list-accounts")
        sys.exit(0)

    # Print matched calls
    print("Matched calls:")
    for call in sorted(account_calls, key=lambda c: c.get("started") or ""):
        crm_name = call.get("crm_account_name") or ""
        match_source = "CRM" if crm_name and args.account_name.lower() in crm_name.lower() else "title/email"
        print(f"  [{(call.get('started') or '?')[:10]}] {call.get('title', 'Untitled')} (matched via {match_source})")
    print()

    # --- Fetch full call details for matched calls (parties + CRM context) ---
    call_ids = [c["id"] for c in account_calls if c.get("id")]
    slug = account_slug(args.account_name)

    call_details_by_id = {}
    if not args.no_cache:
        cached_details = load_account_call_details(cache_dir, slug)
        if cached_details:
            call_details_by_id = cached_details
            new_ids = [cid for cid in call_ids if cid not in call_details_by_id]
            if new_ids:
                print(f"  Fetching details for {len(new_ids)} new calls...")
                new_details = fetch_call_details(new_ids)
                for d in new_details:
                    cid = d.get("metaData", {}).get("id")
                    if cid:
                        call_details_by_id[cid] = d
                save_account_call_details(cache_dir, slug, call_details_by_id)
            else:
                print(f"  Using cached call details ({len(call_details_by_id)} calls).")

    if not call_details_by_id:
        print(f"Fetching full details for {len(call_ids)} matched calls...")
        raw_details = fetch_call_details(call_ids)
        call_details_by_id = {d.get("metaData", {}).get("id"): d for d in raw_details}
        if not args.no_cache:
            save_account_call_details(cache_dir, slug, call_details_by_id)
    print()

    call_details = list(call_details_by_id.values())

    # Build speaker map from full details
    speaker_map = build_speaker_map(call_details)

    # --- Get transcripts (per-account cache) ---
    transcripts = None

    if not args.no_cache:
        acct_meta, cached_transcripts = load_account_transcripts(cache_dir, slug)
        if acct_meta and cached_transcripts is not None:
            cached_ids = set(acct_meta.get("call_ids", []))
            new_ids = [cid for cid in call_ids if cid not in cached_ids]

            if new_ids:
                print(f"  {len(new_ids)} new calls need transcripts...")
                new_transcripts = get_transcripts(new_ids)
                transcripts = cached_transcripts + new_transcripts
                save_account_transcripts(cache_dir, slug, args.account_name, call_ids, transcripts)
            else:
                print(f"  Using cached transcripts ({len(cached_transcripts)} transcripts).")
                transcripts = cached_transcripts

    if transcripts is None:
        print("Fetching transcripts...")
        transcripts = get_transcripts(call_ids)
        print(f"  Retrieved {len(transcripts)} transcripts\n")

        if not args.no_cache:
            save_account_transcripts(cache_dir, slug, args.account_name, call_ids, transcripts)

    # --- Fetch email history ---
    emails = None
    email_status = ""

    if not args.no_cache:
        cached_emails, cached_email_status = load_account_emails(cache_dir, slug)
        if cached_emails is not None:
            emails = cached_emails
            email_status = cached_email_status
            print(f"  Using cached emails ({len(emails)} emails). Status: {email_status}")

    if emails is None:
        # Collect all external email addresses seen across matched calls
        all_external_emails = list({
            p.get("emailAddress")
            for detail in call_details
            for p in detail.get("parties", [])
            if (p.get("affiliation") or "").lower() == "external" and p.get("emailAddress")
        })

        # Determine date range to search emails
        started_dates = [c.get("started") for c in account_calls if c.get("started")]
        email_from = min(started_dates)[:10] + "T00:00:00Z" if started_dates else ALL_TIME_START
        email_to = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        print(f"Fetching email history ({len(all_external_emails)} external addresses)...")
        emails, email_status = fetch_account_emails(all_external_emails, email_from, email_to)
        print(f"  {email_status}")

        if not args.no_cache:
            # Save emails alongside existing cached transcripts (update metadata)
            acct_meta, _ = load_account_transcripts(cache_dir, slug)
            if acct_meta:
                save_account_transcripts(
                    cache_dir, slug, args.account_name, call_ids, transcripts,
                    emails=emails, email_status=email_status
                )

    # Build output
    first_detail = call_details_by_id.get(call_ids[0]) if call_ids else None
    crm_info = get_crm_account_info(first_detail) if first_detail else {}

    output_data = {
        "account_name": args.account_name,
        "crm_account_name": account_calls[0].get("crm_account_name") if account_calls else None,
        "crm_account_info": crm_info,
        "domain": args.domain,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_calls": len(account_calls),
        "calls": [],
        "emails": emails or [],
        "email_status": email_status,
    }

    for call in sorted(account_calls, key=lambda c: c.get("started") or ""):
        call_id = call.get("id")
        transcript = next((t for t in transcripts if t.get("callId") == call_id), None)
        detail = call_details_by_id.get(call_id, {})

        external_parties = [
            {"name": p.get("name"), "email": p.get("emailAddress"), "title": p.get("title")}
            for p in detail.get("parties", [])
            if (p.get("affiliation") or "").lower() == "external"
        ]

        internal_parties = [
            {"name": p.get("name"), "email": p.get("emailAddress"), "title": p.get("title")}
            for p in detail.get("parties", [])
            if (p.get("affiliation") or "").lower() == "internal"
        ]

        call_entry = {
            "call_id": call_id,
            "title": call.get("title"),
            "date": call.get("started"),
            "duration_seconds": call.get("duration"),
            "url": call.get("url"),
            "crm_account_name": call.get("crm_account_name"),
            "crm_context": get_crm_account_info(detail),
            "external_parties": external_parties,
            "internal_parties": internal_parties,
            "transcript_raw": transcript.get("transcript", []) if transcript else [],
            "transcript_formatted": format_transcript(transcript, speaker_map) if transcript else "",
        }
        output_data["calls"].append(call_entry)

    # Output
    def write_markdown(f):
        f.write(f"# Gong Transcripts: {crm_info.get('Name', args.account_name)}\n\n")
        f.write(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"**Total Calls**: {len(account_calls)}\n")
        f.write(f"**Emails**: {len(output_data['emails'])} captured"
                + (f" — _{email_status}_" if email_status and not output_data['emails'] else "") + "\n")

        if crm_info:
            f.write(f"\n### CRM Account Info\n")
            for key in ["Name", "Website", "Industry", "Subscription_ARR__c", "business_size__c",
                        "Engagement_Model__c", "Renewal_Touchpoint__c", "Customer_Health_Notes__c",
                        "Account_Next_Steps__c", "sales_team__c"]:
                val = crm_info.get(key)
                if val:
                    label = key.replace("__c", "").replace("_", " ")
                    f.write(f"- **{label}**: {val}\n")

            opps = crm_info.get("opportunities", [])
            if opps:
                f.write(f"\n### Active Opportunities\n")
                for opp in opps:
                    f.write(f"- **{opp.get('Name', 'Unknown')}** — Stage: {opp.get('StageName', '?')}, "
                            f"Amount: ${opp.get('Amount', 0):,.0f}, "
                            f"Close: {opp.get('CloseDate', '?')}\n")

        # Email history section
        f.write("\n---\n\n")
        f.write("## Email History\n\n")
        acct_emails = output_data.get("emails", [])
        if acct_emails:
            f.write(f"_{len(acct_emails)} emails captured via Gong email integration._\n\n")
            for i, email in enumerate(sorted(acct_emails,
                                             key=lambda e: e.get("sentAt") or e.get("date") or ""),
                                       1):
                f.write(f"### Email {i}\n\n")
                f.write(format_email(email))
                f.write("\n\n---\n\n")
        else:
            f.write(f"_{email_status or 'No emails found.'}_\n\n")
            f.write("---\n\n")

        for call_entry in output_data["calls"]:
            f.write(f"## {call_entry['title'] or 'Untitled'}\n\n")
            f.write(f"**Date**: {(call_entry['date'] or '')[:16]}\n")
            dur = call_entry.get("duration_seconds")
            if dur:
                f.write(f"**Duration**: {dur // 60}m {dur % 60}s\n")
            f.write(f"**Gong URL**: {call_entry.get('url', 'N/A')}\n\n")

            ext = call_entry.get("external_parties", [])
            if ext:
                f.write("**External Participants**:\n")
                for p in ext:
                    name = p.get("name") or "Unknown"
                    title = f" ({p['title']})" if p.get("title") else ""
                    f.write(f"- {name}{title}\n")
                f.write("\n")

            internal = call_entry.get("internal_parties", [])
            if internal:
                f.write("**Internal Participants**:\n")
                for p in internal:
                    name = p.get("name") or "Unknown"
                    title = f" ({p['title']})" if p.get("title") else ""
                    f.write(f"- {name}{title}\n")
                f.write("\n")

            f.write("### Transcript\n\n")
            f.write(call_entry.get("transcript_formatted") or "*No transcript available*")
            f.write("\n\n---\n\n")

    if args.stdout:
        write_markdown(sys.stdout)
    else:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")

        if args.format in ("json", "both"):
            json_path = args.output or str(OUTPUT_DIR / f"gong_{slug}_{date_str}.json")
            with open(json_path, "w") as f:
                json.dump(output_data, f, indent=2, default=str)
            print(f"Saved JSON: {json_path}")

        if args.format in ("text", "both"):
            text_path = str(OUTPUT_DIR / f"gong_{slug}_{date_str}.md")
            with open(text_path, "w") as f:
                write_markdown(f)
            print(f"Saved Markdown: {text_path}")

        print(f"\nDone! {len(account_calls)} calls processed for {args.account_name}.")


if __name__ == "__main__":
    main()
