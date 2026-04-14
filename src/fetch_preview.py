import requests
import time
import sys
import io
import os
from datetime import datetime, timezone
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL     = "https://api.openf1.org/v1"
PREVIEW_DIR  = os.path.join(os.path.dirname(__file__), "..", "data", "preview")
SLEEP        = 1.5
RETRY_WAIT   = 6.0
PREVIEW_ROWS = 10


def get_json(url: str) -> list | None:
    print(f"  GET {url}")
    wait = RETRY_WAIT
    for attempt in range(1, 6):
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            print("  [404] No data.")
            return None
        if r.status_code == 429:
            print(f"  [429] Rate limit (attempt {attempt}/5). Waiting {wait}s...")
            time.sleep(wait)
            wait *= 2
        else:
            r.raise_for_status()
    print(f"  [ERROR] Failed after 5 attempts: {url}")
    return None


def get_csv(url: str) -> pd.DataFrame | None:
    print(f"  GET {url}")
    wait = RETRY_WAIT
    for attempt in range(1, 6):
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            return pd.read_csv(io.StringIO(r.text))
        if r.status_code == 404:
            print("  [404] No data.")
            return None
        if r.status_code == 429:
            print(f"  [429] Rate limit (attempt {attempt}/5). Waiting {wait}s...")
            time.sleep(wait)
            wait *= 2
        else:
            r.raise_for_status()
    print(f"  [ERROR] Failed after 5 attempts: {url}")
    return None


def save_preview(df: pd.DataFrame, name: str):
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    path = os.path.join(PREVIEW_DIR, f"{name}_preview.csv")
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"  ✔ Saved {len(df):,} rows -> {path}")


def print_preview(df: pd.DataFrame, title: str):
    print(f"\n{'═'*70}")
    print(f"  PREVIEW: {title}  ({len(df):,} rows, showing {min(PREVIEW_ROWS, len(df))})")
    print(f"  Columns: {list(df.columns)}")
    print("─" * 70)
    with pd.option_context("display.max_columns", None, "display.width", 160, "display.max_colwidth", 30):
        print(df.head(PREVIEW_ROWS).to_string(index=False))
    print("─" * 70)


def get_past_race_sessions() -> pd.DataFrame:
    print("\n[Step 1] Fetching past Race sessions...")
    data = get_json(f"{BASE_URL}/sessions?session_type=Race")
    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    if df.empty or "session_key" not in df.columns:
        return pd.DataFrame()

    now_utc  = datetime.now(timezone.utc)
    sort_col = "date_end" if "date_end" in df.columns else "date_start"
    df[sort_col] = pd.to_datetime(df[sort_col], utc=True, errors="coerce")
    df = df[df[sort_col] <= now_utc].sort_values(sort_col, ascending=False).reset_index(drop=True)
    print(f"  → {len(df)} completed Race sessions found.")
    return df


def probe_session_has_data(session_key: int) -> bool:
    url = f"{BASE_URL}/race_control?session_key={session_key}"
    r = requests.get(url, timeout=15)
    if r.status_code != 200:
        return False
    try:
        return len(r.json()) > 0
    except Exception:
        return False


def find_latest_session_with_data(sessions_df: pd.DataFrame, max_check: int = 5) -> dict | None:
    for _, row in sessions_df.head(max_check).iterrows():
        sk   = int(row["session_key"])
        loc  = row.get("location", "?")
        year = row.get("year", "?")
        print(f"  Checking session {sk} ({loc} {year})...", end=" ")
        if probe_session_has_data(sk):
            print("✔ Has data!")
            session = row.to_dict()
            print("\n  ✔ Using session:")
            for key in ["session_key", "session_name", "location", "country_name", "year", "date_start", "date_end"]:
                if key in session:
                    print(f"     {key:20s}: {session[key]}")
            return session
        print("✗ No data yet, trying next...")
        time.sleep(SLEEP)
    print("  [ERROR] No session with data found in last 5 sessions.")
    return None


def _get_first_driver(session_key: int) -> int | None:
    drivers_data = get_json(f"{BASE_URL}/drivers?session_key={session_key}")
    time.sleep(SLEEP)
    if not drivers_data:
        return None
    numbers = [d["driver_number"] for d in drivers_data if "driver_number" in d]
    return numbers[0] if numbers else None


def fetch_car_data(session_key: int) -> pd.DataFrame | None:
    print(f"\n[Step 2] Fetching car_data (session_key={session_key})...")
    first_driver = _get_first_driver(session_key)
    if first_driver is None:
        print("  [WARN] No drivers found.")
        return None
    print(f"  → Driver #{first_driver} (sample preview)...")
    df = get_csv(f"{BASE_URL}/car_data?session_key={session_key}&driver_number={first_driver}&csv=true")
    time.sleep(SLEEP)
    if df is None or df.empty:
        print("  [WARN] No car_data.")
        return None
    return df


def fetch_location(session_key: int) -> pd.DataFrame | None:
    print(f"\n[Step 3] Fetching location (session_key={session_key})...")
    first_driver = _get_first_driver(session_key)
    if first_driver is None:
        print("  [WARN] No drivers found.")
        return None
    print(f"  → Driver #{first_driver} (sample preview)...")
    df = get_csv(f"{BASE_URL}/location?session_key={session_key}&driver_number={first_driver}&csv=true")
    time.sleep(SLEEP)
    if df is None or df.empty:
        print("  [WARN] No location data.")
        return None
    return df


def fetch_race_control(session_key: int) -> pd.DataFrame | None:
    print(f"\n[Step 4] Fetching race_control (session_key={session_key})...")
    df = get_csv(f"{BASE_URL}/race_control?session_key={session_key}&csv=true")
    time.sleep(SLEEP)
    if df is None or df.empty:
        print("  [WARN] No race_control data.")
        return None
    return df


if __name__ == "__main__":
    print("=" * 70)
    print("  F1 Preview Fetcher — car_data + location + race_control")
    print("=" * 70)

    sessions_df = get_past_race_sessions()
    if sessions_df.empty:
        print("\n[ERROR] Could not fetch sessions.")
        sys.exit(1)

    session = find_latest_session_with_data(sessions_df, max_check=5)
    if session is None:
        print("\n[ERROR] No session with data found.")
        sys.exit(1)

    sk = int(session["session_key"])

    for fetch_fn, label in [
        (fetch_car_data,    "car_data"),
        (fetch_location,    "location"),
        (fetch_race_control, "race_control"),
    ]:
        df = fetch_fn(sk)
        if df is not None:
            print_preview(df, f"{label} (session_key={sk})")
            save_preview(df, label)
        else:
            print(f"  No {label} to preview.")

    print("\n[Done] Preview files saved to data/preview/")
