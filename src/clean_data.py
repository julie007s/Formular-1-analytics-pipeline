import os
import sys
import logging
import numpy as np
import pandas as pd

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

logger = logging.getLogger(__name__)

BASE_DIR       = os.path.join(os.path.dirname(__file__), "..")
RAW_DATA_DIR   = os.path.join(BASE_DIR, "data", "raw")
CLEAN_DATA_DIR = os.path.join(BASE_DIR, "data", "cleaned")


# Tất cả các session type hợp lệ (đồng bộ với pipeline_config.yaml)
VALID_SESSION_TYPES = {"Race", "Sprint", "Qualifying", "Sprint Shootout", "Sprint Qualifying"}


def clean_sessions(df: pd.DataFrame) -> pd.DataFrame:
    df.dropna(how="all", inplace=True)

    if "session_type" in df.columns:
        df = df[df["session_type"].isin(VALID_SESSION_TYPES)].copy()

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
def clean_laps(df: pd.DataFrame) -> pd.DataFrame:
    df.dropna(how="all", inplace=True)

    for col in ["session_key", "driver_number", "lap_number"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # =========================================================
    # BƯỚC 1: XÁC ĐỊNH & LOẠI BỎ DNF (Did Not Finish)
    # Nguyên tắc: KHÔNG BAO GIỜ điền lap_duration bằng median.
    # Nếu lap_duration là NaN → xe không hoàn thành vòng đua →
    # điền số giả vào sẽ khiến AI tưởng xe vẫn đang chạy bình thường.
    # =========================================================
    if "lap_duration" in df.columns:
        df["lap_duration"] = pd.to_numeric(df["lap_duration"], errors="coerce")

        # 1a. Loại bỏ hoàn toàn các vòng không hoàn thành (DNF/SC/lap bị hủy)
        dnf_count = df["lap_duration"].isna().sum()
        df = df.dropna(subset=["lap_duration"]).copy()
        if dnf_count:
            logger.info(f"  Removed {dnf_count} incomplete laps (lap_duration=NaN → likely DNF/SC)")

        # 1b. Lọc hard bound: giá trị ngoài [30s, 600s] là lỗi sensor, không phải DNF
        out_of_range = (~df["lap_duration"].between(30, 600)).sum()
        df = df[df["lap_duration"].between(30, 600)].copy()
        if out_of_range:
            logger.info(f"  Removed {out_of_range} laps with sensor-error duration (outside 30-600s)")

        # 1c. Z-score flagging trên CÁC VÒNG ĐÃ HOÀN THÀNH
        # Vòng |Z| > 3 không bị xóa — gắn nhãn để AI phân biệt "vòng sự cố chiến thuật"
        if {"session_key", "driver_number"}.issubset(df.columns):
            grp = df.groupby(["session_key", "driver_number"])["lap_duration"]
            mean = grp.transform("mean")
            std  = grp.transform("std").replace(0, np.nan)
            df["lap_zscore"] = ((df["lap_duration"] - mean) / std).abs()
            df["is_outlier_lap"] = df["lap_zscore"] > 3
            df.drop(columns=["lap_zscore"], inplace=True)
            logger.info(f"  Flagged {df['is_outlier_lap'].sum()} statistical outlier laps (|Z|>3, kept for AI context)")

    # =========================================================
    # BƯỚC 2: CHỈ SAU KHI ĐÃ XÁC NHẬN VÒNG HOÀN THÀNH
    # mới impute các cột cảm biến phụ (tốc độ, sector time...)
    # Lý do: đây là "lỗi cảm biến" trên vòng đua thực sự tồn tại,
    # không phải dữ liệu của vòng không hoàn thành.
    # =========================================================
    for col in ["i1_speed", "i2_speed", "st_speed"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df.loc[~df[col].between(0, 400), col] = np.nan
            if {"session_key", "driver_number"}.issubset(df.columns):
                driver_median = df.groupby(["session_key", "driver_number"])[col].transform("median")
                global_median = df[col].median()
                df[col] = df[col].fillna(driver_median).fillna(global_median)
            else:
                df[col] = df[col].fillna(df[col].median())

    for col in ["duration_sector_1", "duration_sector_2", "duration_sector_3"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            if {"session_key", "driver_number"}.issubset(df.columns):
                driver_median = df.groupby(["session_key", "driver_number"])[col].transform("median")
                global_median = df[col].median()
                df[col] = df[col].fillna(driver_median).fillna(global_median)
            else:
                df[col] = df[col].fillna(df[col].median())

    for col in ["segments_sector_1", "segments_sector_2", "segments_sector_3"]:
        if col in df.columns:
            df[col] = df[col].fillna("")

    if "date_start" in df.columns:
        df["date_start"] = pd.to_datetime(df["date_start"], errors="coerce", utc=True)
        # CHỐNG LỖI MERGE_ASOF: Loại bỏ laps không có mốc thời gian ngay từ tầng Silver
        initial_laps = len(df)
        df = df.dropna(subset=["date_start"]).copy()
        dropped = initial_laps - len(df)
        if dropped > 0:
            logger.warning(f"  clean_laps: Loại bỏ {dropped} laps bị lỗi date_start (NaT)")

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


def clean_position(df: pd.DataFrame) -> pd.DataFrame:
    """Clean position time-series data (nhiều dòng/driver/session theo thời gian thực)."""
    df.dropna(how="all", inplace=True)

    for col in ["session_key", "driver_number"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True)
        df.dropna(subset=["date"], inplace=True)

    if "position" in df.columns:
        df["position"] = pd.to_numeric(df["position"], errors="coerce")
        df = df[df["position"].between(1, 25) | df["position"].isna()].copy()

    df.dropna(subset=["session_key", "driver_number"], inplace=True)
    # Không drop_duplicates vì đây là time-series (nhiều dòng mỗi driver)
    df.reset_index(drop=True, inplace=True)
    return df


def clean_car_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean car telemetry data (Silver layer).
    NHIỆM VỤ: Lọc rác kỹ thuật, ép kiểu dữ liệu.
    GIỮ NGUYÊN: dữ liệu vẫn ở cấp độ mỏ-giây (không aggregate).
    """
    df.dropna(how="all", inplace=True)

    # Ép kiểu các cột quan trọng
    numeric_cols = ["Speed", "RPM", "Throttle", "Brake", "DRS", "nGear",
                    "X", "Y", "Z"]  # FastF1 column names
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Lọc các giá trị vật lý phi lý (lỗi cảm biến)
    if "Speed" in df.columns:
        out_of_range = (~df["Speed"].between(0, 400)).sum()
        df = df[df["Speed"].between(0, 400) | df["Speed"].isna()].copy()
        if out_of_range:
            logger.info(f"  car_data: removed {out_of_range} rows with Speed outside [0, 400] km/h")

    if "RPM" in df.columns:
        df.loc[~df["RPM"].between(0, 20000), "RPM"] = np.nan

    if "Throttle" in df.columns:
        df.loc[~df["Throttle"].between(0, 100), "Throttle"] = np.nan

    # Time column
    if "Time" in df.columns:
        df["Time"] = pd.to_timedelta(df["Time"], errors="coerce")
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)

    # Bắt buộc có driver_number
    if "driver_number" in df.columns:
        df["driver_number"] = pd.to_numeric(df["driver_number"], errors="coerce")
        df.dropna(subset=["driver_number"], inplace=True)

    df.reset_index(drop=True, inplace=True)
    return df


def clean_location(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean GPS location data (Silver layer).
    NHIỆM VỤ: Lọc tọa độ phi lý, ép kiểu dữ liệu.
    GIỮ NGUYÊN: dữ liệu vẫn ở cấp độ mỏ-giây.
    """
    df.dropna(how="all", inplace=True)

    for col in ["X", "Y", "Z"]:  # GPS coordinates
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
        df.dropna(subset=["Date"], inplace=True)

    if "driver_number" in df.columns:
        df["driver_number"] = pd.to_numeric(df["driver_number"], errors="coerce")
        df.dropna(subset=["driver_number"], inplace=True)

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
    "position.csv":        clean_position,
    # Telemetry — Silver: lọc rác, giữ nguyên độ phân giải mỏ-giây
    "car_data.parquet":    clean_car_data,
    "location.parquet":    clean_location,
}


def clean_all(dry_run: bool = False):
    print("=" * 60)
    print("   F1 DATA CLEANING  (clean_data.py)")
    if dry_run:
        print("   !!! DRY RUN MODE - No files will be saved !!!")
    print("   Raw -> data/raw/  |  Clean -> data/cleaned/")
    print("=" * 60)

    from pathlib import Path
    import glob

    raw_dir_path = Path(RAW_DATA_DIR)
    clean_dir_path = Path(CLEAN_DATA_DIR)
    clean_dir_path.mkdir(parents=True, exist_ok=True)
    
    summary = []

    for filename, clean_fn in CLEAN_FUNCTIONS.items():
        # Hỗ trợ cả .csv và .parquet — lấy tên endpoint chính xác
        is_parquet_output = filename.endswith(".parquet")
        endpoint = filename.replace(".parquet", "").replace(".csv", "")
        endpoint_dir = raw_dir_path / endpoint
        
        # Find all session-based CSVs and Parquets
        all_files = list(endpoint_dir.glob("**/*.csv")) + list(endpoint_dir.glob("**/*.parquet"))
        
        # Check for old flat file
        old_flat_path = raw_dir_path / filename
        if old_flat_path.exists():
            all_files.append(old_flat_path)

        if not all_files:
            logger.info(f"Skipping {filename} - No raw data found")
            summary.append({"file": filename, "status": "skipped"})
            continue

        logger.info(f"Cleaning {endpoint} (combining {len(all_files)} files)")

        # --- Cải tiến B: Xử lý từng file riêng lẻ để tiết kiệm RAM ---
        # Thay vì nạp tất cả vào RAM rồi concat, ta clean từng file trước rồi mới ghép
        is_large_endpoint = endpoint in {"car_data", "location", "laps", "intervals", "position"}

        if is_large_endpoint:
            cleaned_parts = []
            raw_rows = 0
            for f in all_files:
                try:
                    df_part = pd.read_parquet(f) if f.suffix == ".parquet" else pd.read_csv(f, low_memory=False)
                    if not df_part.empty:
                        raw_rows += len(df_part)
                        df_part_cleaned = clean_fn(df_part)
                        if not df_part_cleaned.empty:
                            cleaned_parts.append(df_part_cleaned)
                except Exception as e:
                    logger.error(f"Failed to process {f}: {e}")
            df_cleaned = pd.concat(cleaned_parts, ignore_index=True) if cleaned_parts else pd.DataFrame()
        else:
            frames = []
            for f in all_files:
                try:
                    df = pd.read_parquet(f) if f.suffix == ".parquet" else pd.read_csv(f, low_memory=False)
                    if not df.empty:
                        frames.append(df)
                except Exception as e:
                    logger.error(f"Failed to read {f}: {e}")
            if not frames:
                continue
            df_combined = pd.concat(frames, ignore_index=True)
            raw_rows = len(df_combined)
            df_cleaned = clean_fn(df_combined)
        clean_rows = len(df_cleaned)
        
        if dry_run:
            logger.info(f"  [Dry Run] Would save {clean_rows} cleaned rows to {filename}")
        else:
            out_path = clean_dir_path / filename
            if is_parquet_output:
                # Telemetry — lưu dạng Parquet để tối ưu dung lượng và tốc độ đọc
                df_cleaned.to_parquet(out_path, index=False, compression="zstd")
            else:
                df_cleaned.to_csv(out_path, index=False)

        dropped = raw_rows - clean_rows
        logger.info(f"  {endpoint}: {raw_rows:,} -> {clean_rows:,} (dropped {dropped:,})")
        summary.append({
            "file": filename, 
            "raw_rows": raw_rows, 
            "clean_rows": clean_rows, 
            "dropped": dropped, 
            "status": "ok"
        })

    if not dry_run:
        summary_df = pd.DataFrame(summary)
        reports_dir = os.path.join(BASE_DIR, "reports", "data_quality")
        os.makedirs(reports_dir, exist_ok=True)
        summary_df.to_csv(os.path.join(reports_dir, "cleaning_summary.csv"), index=False)
        summary_df.to_markdown(os.path.join(reports_dir, "cleaning_summary.md"), index=False)

        # --- Cải tiến D: Ưu tiên starting_grid từ OpenF1, chỉ fallback về position.csv ---
        position_clean_path = os.path.join(CLEAN_DATA_DIR, "position.csv")
        starting_grid_clean_path = os.path.join(CLEAN_DATA_DIR, "starting_grid.csv")
        session_results_clean_path = os.path.join(CLEAN_DATA_DIR, "session_results.csv")

        # Chỉ derive starting_grid từ position nếu chưa có từ OpenF1 endpoint
        if os.path.exists(position_clean_path):
            pos = pd.read_csv(position_clean_path, low_memory=False)
            if "date" in pos.columns:
                pos = pos.sort_values("date")
            if {"session_key", "driver_number"}.issubset(pos.columns):
                # Luôn derive session_results từ dòng CUỐI cùng của position
                results = pos.groupby(["session_key", "driver_number"], as_index=False).last()
                if not os.path.exists(session_results_clean_path):
                    results.to_csv(session_results_clean_path, index=False)
                    logger.info("Derived session_results.csv from position.csv (last position)")

                # Chỉ derive starting_grid từ position nếu OpenF1 không cung cấp
                if not os.path.exists(starting_grid_clean_path):
                    grid = pos.groupby(["session_key", "driver_number"], as_index=False).first()
                    grid.to_csv(starting_grid_clean_path, index=False)
                    logger.warning(
                        "starting_grid.csv derived from position.csv (FALLBACK). "
                        "Dữ liệu GPS có thể chưa bắt đầu từ vạch xuất phát thực sự."
                    )
                else:
                    logger.info("starting_grid.csv đã tồn tại từ OpenF1 — bỏ qua fallback từ position.csv")

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
