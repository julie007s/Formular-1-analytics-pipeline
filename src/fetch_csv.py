import requests
import time
import sys
import io
import os
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL     = "https://api.openf1.org/v1"
OUT_DIR      = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
START_YEAR   = 2024
CURRENT_YEAR = 2026
SLEEP        = 1.5
RETRY_WAIT   = 6.0

SESSION_TYPES = [
    "Race", "Sprint", "Practice 1", "Practice 2", "Practice 3",
    "Qualifying", "Sprint Shootout", "Sprint Qualifying",
]


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


def save_csv(df: pd.DataFrame, name: str):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{name}.csv")
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"[fetch_csv] Saved {len(df):,} rows -> {name}.csv")


def get_session_keys() -> list[int]:
    keys = []
    for year in range(START_YEAR, CURRENT_YEAR + 1):
        df = get_csv(f"{BASE_URL}/sessions?year={year}&session_type=Race&csv=true")
        time.sleep(SLEEP)
        if df is not None and "session_key" in df.columns:
            keys.extend(df["session_key"].dropna().astype(int).tolist())
            print(f"  Year {year}: {len(df)} sessions")
    return keys


def fetch_per_session(endpoint: str, session_keys: list[int]) -> pd.DataFrame:
    frames = []
    for sk in session_keys:
        df = get_csv(f"{BASE_URL}/{endpoint}?session_key={sk}&csv=true")
        if df is not None and not df.empty:
            frames.append(df)
        time.sleep(SLEEP)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_position_filtered(session_keys: list[int], mode: str) -> pd.DataFrame:
    frames = []
    for sk in session_keys:
        df = get_csv(f"{BASE_URL}/position?session_key={sk}&csv=true")
        if df is None or df.empty:
            time.sleep(SLEEP)
            continue
        if "date" in df.columns:
            df = df.sort_values("date")
        if mode == "first":
            df = df.groupby("driver_number", as_index=False).first()
        else:
            df = df.groupby("driver_number", as_index=False).last()
        frames.append(df)
        time.sleep(SLEEP)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


if __name__ == "__main__":
    print("[fetch_csv] Step 1: Fetching sessions metadata...")
    session_frames = []
    for year in range(START_YEAR, CURRENT_YEAR + 1):
        df = get_csv(f"{BASE_URL}/sessions?year={year}&csv=true")
        if df is not None:
            session_frames.append(df)
        time.sleep(SLEEP)

    sessions_df = pd.concat(session_frames, ignore_index=True) if session_frames else pd.DataFrame()
    save_csv(sessions_df, "sessions")

    if "session_key" in sessions_df.columns and "session_type" in sessions_df.columns:
        mask = sessions_df["session_type"].isin(SESSION_TYPES)
        session_keys = sessions_df.loc[mask, "session_key"].dropna().astype(int).tolist()
    else:
        session_keys = []
    print(f"[fetch_csv] Found {len(session_keys)} sessions to query.\n")

    for ep in ["drivers", "laps", "weather", "intervals", "stints"]:
        print(f"[fetch_csv] Fetching {ep}...")
        df = fetch_per_session(ep, session_keys)
        if not df.empty:
            if ep == "drivers":
                df = df.drop_duplicates(subset=["driver_number"])
            save_csv(df, ep)
        else:
            print(f"[fetch_csv] No data for {ep}.")
        print()

    print("[fetch_csv] Fetching starting_grid...")
    save_csv(fetch_position_filtered(session_keys, mode="first"), "starting_grid")

    print("\n[fetch_csv] Fetching session_results...")
    save_csv(fetch_position_filtered(session_keys, mode="last"), "session_results")

    print("\n[fetch_csv] Done! Files saved to data/raw/")
