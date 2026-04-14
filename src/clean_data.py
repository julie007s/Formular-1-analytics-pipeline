import os
import sys
import numpy as np
import pandas as pd

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR       = os.path.join(os.path.dirname(__file__), "..")
RAW_DATA_DIR   = os.path.join(BASE_DIR, "data", "raw")
CLEAN_DATA_DIR = os.path.join(BASE_DIR, "data", "cleaned")


def clean_sessions(df: pd.DataFrame) -> pd.DataFrame:
    df.dropna(how="all", inplace=True)

    if "session_type" in df.columns:
        df = df[df["session_type"] == "Race"].copy()

    for col in ["date_start", "date_end"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    for col in ["year", "session_key", "circuit_key"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "circuit_short_name" in df.columns:
        if df["circuit_short_name"].isna().all():
            df.drop(columns=["circuit_short_name"], inplace=True)
        else:
            df["circuit_short_name"] = df["circuit_short_name"].fillna("Unknown")

    for col in ["location", "country_name", "gmt_offset"]:
        if col in df.columns:
            df[col] = df[col].fillna("Unknown")

    df.drop_duplicates(subset=["session_key"], keep="first", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def clean_drivers(df: pd.DataFrame) -> pd.DataFrame:
    df.dropna(how="all", inplace=True)

    for col in ["driver_number", "session_key"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["full_name", "name_acronym", "team_name", "country_code"]:
        if col in df.columns:
            df[col] = df[col].fillna("Unknown")
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({"nan": "Unknown", "": "Unknown"})

    if "headshot_url" in df.columns:
        default = "https://media.formula1.com/d_driver_fallback_image.png"
        df["headshot_url"] = df["headshot_url"].fillna(default).replace({"": default})

    df.drop_duplicates(subset=["driver_number", "session_key"], keep="first", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def clean_session_results(df: pd.DataFrame) -> pd.DataFrame:
    df.dropna(how="all", inplace=True)

    for col in ["session_key", "driver_number"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "position" in df.columns:
        df["position"] = pd.to_numeric(df["position"], errors="coerce")
        df = df[df["position"].between(1, 25) | df["position"].isna()].copy()

    if "status" in df.columns:
        df["status"] = df["status"].astype(str).str.strip().replace({"nan": "Unknown", "": "Unknown"})

    df.dropna(subset=["session_key", "driver_number"], inplace=True)
    df.drop_duplicates(subset=["session_key", "driver_number"], keep="first", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def clean_laps(df: pd.DataFrame) -> pd.DataFrame:
    df.dropna(how="all", inplace=True)

    for col in ["session_key", "driver_number", "lap_number"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "lap_duration" in df.columns:
        df["lap_duration"] = pd.to_numeric(df["lap_duration"], errors="coerce")
        df = df[df["lap_duration"].between(60, 600) | df["lap_duration"].isna()].copy()

    for col in ["i1_speed", "i2_speed", "st_speed"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df.loc[~df[col].between(0, 400), col] = np.nan
            df[col] = df[col].fillna(df[col].median())

    for col in ["duration_sector_1", "duration_sector_2", "duration_sector_3"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df[col] = df[col].fillna(df[col].median())

    for col in ["segments_sector_1", "segments_sector_2", "segments_sector_3"]:
        if col in df.columns:
            df[col] = df[col].fillna("")

    if "date_start" in df.columns:
        df["date_start"] = pd.to_datetime(df["date_start"], errors="coerce", utc=True)

    if "is_pit_out_lap" in df.columns:
        df["is_pit_out_lap"] = df["is_pit_out_lap"].astype(str).str.lower().map(
            {"true": True, "false": False, "1": True, "0": False}
        )

    df.dropna(subset=["session_key", "driver_number", "lap_number"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def clean_weather(df: pd.DataFrame) -> pd.DataFrame:
    df.dropna(how="all", inplace=True)

    if "session_key" in df.columns:
        df["session_key"] = pd.to_numeric(df["session_key"], errors="coerce")

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True)
        df.dropna(subset=["date"], inplace=True)

    numeric_bounds = {
        "air_temperature":   (-30, 60),
        "track_temperature": (-10, 80),
        "humidity":          (0, 100),
        "pressure":          (800, 1100),
        "wind_speed":        (0, 200),
        "wind_direction":    (0, 360),
        "rainfall":          (0, 1),
    }
    for col, (lo, hi) in numeric_bounds.items():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df.loc[~df[col].between(lo, hi), col] = np.nan
            df[col] = df[col].fillna(df[col].median())

    df.dropna(subset=["session_key"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def clean_stints(df: pd.DataFrame) -> pd.DataFrame:
    df.dropna(how="all", inplace=True)

    for col in ["session_key", "driver_number", "stint_number", "lap_start", "lap_end", "tyre_age_at_start"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "lap_start" in df.columns and "lap_end" in df.columns:
        df = df[df["lap_end"] >= df["lap_start"]].copy()

    if "compound" in df.columns:
        valid = {"SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET", "UNKNOWN"}
        df["compound"] = df["compound"].astype(str).str.strip().str.upper()
        df["compound"] = df["compound"].apply(lambda x: x if x in valid else "UNKNOWN")

    df.dropna(subset=["session_key", "driver_number", "stint_number"], inplace=True)
    df.drop_duplicates(subset=["session_key", "driver_number", "stint_number"], keep="first", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def clean_starting_grid(df: pd.DataFrame) -> pd.DataFrame:
    df.dropna(how="all", inplace=True)

    for col in ["session_key", "driver_number", "position"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "position" in df.columns:
        df = df[df["position"].between(1, 25) | df["position"].isna()].copy()

    df.dropna(subset=["session_key", "driver_number"], inplace=True)
    df.drop_duplicates(subset=["session_key", "driver_number"], keep="first", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def clean_intervals(df: pd.DataFrame) -> pd.DataFrame:
    df.dropna(how="all", inplace=True)

    for col in ["session_key", "driver_number"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True)
        df.dropna(subset=["date"], inplace=True)

    for col in ["gap_to_leader", "interval"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace({"nan": np.nan, "": np.nan})
            lap_mask = df[col].str.contains("LAP", case=False, na=False)
            df[col + "_lapped"] = lap_mask
            df.loc[lap_mask, col] = np.nan
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df.loc[df[col] > 300, col] = np.nan

    df.dropna(subset=["session_key", "driver_number"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


CLEAN_FUNCTIONS = {
    "sessions.csv":        clean_sessions,
    "drivers.csv":         clean_drivers,
    "session_results.csv": clean_session_results,
    "laps.csv":            clean_laps,
    "weather.csv":         clean_weather,
    "stints.csv":          clean_stints,
    "starting_grid.csv":   clean_starting_grid,
    "intervals.csv":       clean_intervals,
}


def clean_all():
    print("=" * 60)
    print("   F1 DATA CLEANING  (clean_data.py)")
    print("   Raw -> data/raw/  |  Clean -> data/cleaned/")
    print("=" * 60)

    os.makedirs(CLEAN_DATA_DIR, exist_ok=True)
    summary = []

    for filename, clean_fn in CLEAN_FUNCTIONS.items():
        raw_path = os.path.join(RAW_DATA_DIR, filename)
        if not os.path.exists(raw_path):
            print(f"\n[SKIP] {filename}")
            summary.append({"file": filename, "raw_rows": "-", "clean_rows": "-", "status": "skipped"})
            continue

        print(f"\n[→] {filename}")
        df_raw   = pd.read_csv(raw_path, low_memory=False)
        raw_rows = len(df_raw)
        print(f"    Read: {raw_rows:,} rows, {len(df_raw.columns)} cols")

        df_clean   = clean_fn(df_raw)
        clean_rows = len(df_clean)
        out_path   = os.path.join(CLEAN_DATA_DIR, filename)
        df_clean.to_csv(out_path, index=False)

        dropped = raw_rows - clean_rows
        print(f"    ✓ {raw_rows:,} → {clean_rows:,} rows (dropped {dropped:,})")
        summary.append({"file": filename, "raw_rows": raw_rows, "clean_rows": clean_rows, "dropped": dropped, "status": "ok"})

    print("\n" + "=" * 60)
    print(f"{'File':<25} {'Raw':>10} {'Cleaned':>10} {'Dropped':>10}  Status")
    print("-" * 60)
    for s in summary:
        print(
            f"{s['file']:<25} "
            f"{str(s.get('raw_rows', '-')):>10} "
            f"{str(s.get('clean_rows', '-')):>10} "
            f"{str(s.get('dropped', '-')):>10}  "
            f"{s['status']}"
        )
    print("=" * 60)


if __name__ == "__main__":
    clean_all()
