"""
src/feature_engineering.py
Lap-level feature engineering for F1 real-time win rate prediction.
Input:  data/cleaned/*.csv
Output: data/processed/master_dataset.csv  (granularity: session_key + driver_number + lap_number)
"""
from __future__ import annotations
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from .config import load_config
from .utils import setup_logging, write_csv, write_json, utc_now_iso

logger = logging.getLogger(__name__)

# ── Domain-knowledge tyre cliff defaults (lap number within a stint) ──────────
TYRE_CLIFF_DEFAULTS = {
    "SOFT": 22, "MEDIUM": 33, "HARD": 45,
    "INTERMEDIATE": 20, "WET": 15, "UNKNOWN": 30,
}
ROLLING_WINDOWS = [3, 5, 10]
WINSOR_Q = (0.01, 0.99)  # Winsorize at 1 – 99 percentile


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path, low_memory=False)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tyre cliff learning (hybrid: data-learned + domain knowledge)
# ─────────────────────────────────────────────────────────────────────────────

def learn_tyre_cliffs(stints_df: pd.DataFrame, laps_df: pd.DataFrame) -> dict[str, int]:
    """
    Học tyre cliff từ dữ liệu thực tế.
    Cliff = lap trong stint mà lap_duration bắt đầu tăng liên tục > 1% per bin.
    Kết quả được blend 60% learned + 40% domain knowledge.
    """
    cliffs = dict(TYRE_CLIFF_DEFAULTS)
    needed_s = {"session_key", "driver_number", "lap_start", "lap_end", "compound", "tyre_age_at_start"}
    needed_l = {"session_key", "driver_number", "lap_number", "lap_duration"}
    if stints_df.empty or laps_df.empty:
        return cliffs
    if not needed_s.issubset(stints_df.columns) or not needed_l.issubset(laps_df.columns):
        return cliffs

    merged = laps_df[list(needed_l)].merge(stints_df[list(needed_s)], on=["session_key", "driver_number"], how="left")
    merged = merged[
        (merged["lap_number"] >= merged["lap_start"].fillna(-1)) &
        (merged["lap_number"] <= merged["lap_end"].fillna(9999))
    ].copy()
    merged["tyre_age"] = (merged["lap_number"] - merged["lap_start"] + merged["tyre_age_at_start"].fillna(0))

    for compound in merged["compound"].dropna().unique():
        cdf = merged[merged["compound"] == compound].copy()
        if len(cdf) < 50:
            continue
        try:
            cdf["age_bin"] = pd.cut(cdf["tyre_age"], bins=range(0, 62, 2))
            perf = cdf.groupby("age_bin", observed=True)["lap_duration"].median().dropna()
            if len(perf) < 5:
                continue
            cliff_bins = perf.pct_change()[perf.pct_change() > 0.01].index
            if len(cliff_bins) == 0:
                continue
            learned = int(str(cliff_bins[0]).split(",")[0].strip("([ "))
            domain = TYRE_CLIFF_DEFAULTS.get(compound.upper(), 30)
            blended = max(5, int(0.6 * learned + 0.4 * domain))
            cliffs[compound.upper()] = blended
            logger.info(f"  Tyre cliff [{compound}]: learned={learned} domain={domain} → blended={blended}")
        except Exception as exc:
            logger.warning(f"  Cliff learning failed for {compound}: {exc}")
    return cliffs


# ─────────────────────────────────────────────────────────────────────────────
# 2. Stint features per lap
# ─────────────────────────────────────────────────────────────────────────────

def add_stint_features(laps: pd.DataFrame, stints: pd.DataFrame, cliffs: dict) -> pd.DataFrame:
    """Merge stints → compound, tyre age, cliff features per lap."""
    if stints.empty:
        laps["compound"] = "UNKNOWN"
        laps["current_tyre_age"] = np.nan
        laps["stint_number"] = np.nan
        return laps

    needed = {"session_key", "driver_number", "stint_number", "lap_start", "lap_end", "compound", "tyre_age_at_start"}
    if not needed.issubset(stints.columns):
        return laps

    merged = laps.merge(stints[list(needed)], on=["session_key", "driver_number"], how="left")
    in_range = (
        (merged["lap_number"] >= merged["lap_start"].fillna(-1)) &
        (merged["lap_number"] <= merged["lap_end"].fillna(9999))
    )
    merged = merged[in_range].copy()
    merged = (merged.sort_values("stint_number")
              .groupby(["session_key", "driver_number", "lap_number"], as_index=False)
              .first())

    merged["current_tyre_age"] = (merged["lap_number"] - merged["lap_start"] +
                                   merged["tyre_age_at_start"].fillna(0)).clip(lower=0)

    compound_upper = merged["compound"].fillna("UNKNOWN").str.upper()
    merged["compound_cliff"] = compound_upper.map(cliffs).fillna(30)
    merged["laps_until_cliff"] = (merged["compound_cliff"] - merged["current_tyre_age"]).clip(lower=0)
    merged["is_past_cliff"] = (merged["current_tyre_age"] > merged["compound_cliff"]).astype("Int64")
    merged.drop(columns=["lap_start", "lap_end", "tyre_age_at_start"], inplace=True, errors="ignore")
    return merged


# ─────────────────────────────────────────────────────────────────────────────
# 3. Rolling window features (no future leak — shift(1) before rolling)
# ─────────────────────────────────────────────────────────────────────────────

def add_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["session_key", "driver_number", "lap_number"])
    grp = df.groupby(["session_key", "driver_number"])["lap_duration"]
    for w in ROLLING_WINDOWS:
        shifted = grp.transform(lambda x: x.shift(1))
        df[f"rolling_avg_lap_{w}"] = shifted.groupby(
            [df["session_key"], df["driver_number"]]
        ).transform(lambda x: x.rolling(w, min_periods=1).mean())
        df[f"rolling_std_lap_{w}"] = shifted.groupby(
            [df["session_key"], df["driver_number"]]
        ).transform(lambda x: x.rolling(w, min_periods=2).std())
        df[f"rolling_best_lap_{w}"] = shifted.groupby(
            [df["session_key"], df["driver_number"]]
        ).transform(lambda x: x.rolling(w, min_periods=1).min())

    df["lap_delta_prev"] = df.groupby(["session_key", "driver_number"])["lap_duration"].diff()
    total_laps = df.groupby(["session_key", "driver_number"])["lap_number"].transform("max")
    df["laps_to_go"] = (total_laps - df["lap_number"]).clip(lower=0)
    df["race_completion_pct"] = (df["lap_number"] / total_laps.replace(0, np.nan)).round(4)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 4. Weather features + Track Evolution
# ─────────────────────────────────────────────────────────────────────────────

def add_weather_features(df: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    if weather.empty or "date_start" not in df.columns or "date" not in weather.columns:
        return df

    df = df.copy()
    df["date_start"] = pd.to_datetime(df["date_start"], errors="coerce", utc=True)
    weather = weather.copy()
    weather["date"] = pd.to_datetime(weather["date"], errors="coerce", utc=True)

    w_cols = [c for c in ["session_key", "date", "air_temperature", "track_temperature",
                           "humidity", "rainfall", "wind_speed"] if c in weather.columns]
    weather_sub = weather[w_cols].dropna(subset=["date"]).sort_values("date")

    parts = []
    for sk, lap_grp in df.groupby("session_key"):
        wg = weather_sub[weather_sub["session_key"] == sk].copy()
        if wg.empty:
            parts.append(lap_grp)
            continue
        merged = pd.merge_asof(
            lap_grp.sort_values("date_start"),
            wg.drop(columns=["session_key"]),
            left_on="date_start", right_on="date", direction="nearest"
        ).drop(columns=["date"], errors="ignore")

        if "track_temperature" in merged.columns:
            base_temp = wg["track_temperature"].iloc[0]
            merged["track_temp_evolution"] = (merged["track_temperature"] - base_temp).round(2)
        parts.append(merged)

    return pd.concat(parts, ignore_index=True) if parts else df


# ─────────────────────────────────────────────────────────────────────────────
# 5. Position features per lap
# ─────────────────────────────────────────────────────────────────────────────

def add_position_features(df: pd.DataFrame, position: pd.DataFrame) -> pd.DataFrame:
    if position.empty or "date_start" not in df.columns:
        return df
    required = {"session_key", "driver_number", "date", "position"}
    if not required.issubset(position.columns):
        return df

    df = df.copy()
    df["date_start"] = pd.to_datetime(df["date_start"], errors="coerce", utc=True)
    position = position.copy()
    position["date"] = pd.to_datetime(position["date"], errors="coerce", utc=True)

    parts = []
    for (sk, dn), grp in df.groupby(["session_key", "driver_number"]):
        pg = position[(position["session_key"] == sk) & (position["driver_number"] == dn)][
            ["date", "position"]].dropna().sort_values("date")
        if pg.empty:
            parts.append(grp)
            continue
        merged = pd.merge_asof(
            grp.sort_values("date_start"), pg,
            left_on="date_start", right_on="date", direction="backward"
        ).drop(columns=["date"], errors="ignore").rename(columns={"position": "current_position"})
        parts.append(merged)

    if not parts:
        return df
    out = pd.concat(parts, ignore_index=True)
    if "current_position" in out.columns:
        cp = pd.to_numeric(out["current_position"], errors="coerce")
        out["is_leading"] = (cp == 1).astype("Int64")
        out["is_top3"] = cp.between(1, 3).astype("Int64")
        out["is_top10"] = cp.between(1, 10).astype("Int64")
        out["position_gain_lap"] = out.groupby(["session_key", "driver_number"])["current_position"].diff().mul(-1)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 6. ML Targets
# ─────────────────────────────────────────────────────────────────────────────

def add_targets(df: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        for col in ["final_position", "target_win", "target_podium", "target_top10"]:
            df[col] = pd.NA
        return df

    res_cols = [c for c in ["session_key", "driver_number", "position", "status"] if c in results.columns]
    res = results[res_cols].rename(columns={"position": "final_position"})
    df = df.merge(res, on=["session_key", "driver_number"], how="left")
    fp = pd.to_numeric(df["final_position"], errors="coerce")
    df["target_win"] = (fp == 1).astype("Int64")
    df["target_podium"] = fp.between(1, 3).astype("Int64")
    df["target_top10"] = fp.between(1, 10).astype("Int64")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 7. Winsorization
# ─────────────────────────────────────────────────────────────────────────────

def winsorize(df: pd.DataFrame) -> pd.DataFrame:
    skip = {"session_key", "driver_number", "lap_number", "circuit_key", "year",
            "stint_number", "compound_cliff"}
    flag_prefixes = ("target_", "is_", "rolling_", "laps_")
    for col in df.select_dtypes(include="number").columns:
        if col in skip or any(col.startswith(p) for p in flag_prefixes):
            continue
        lo, hi = df[col].quantile(WINSOR_Q[0]), df[col].quantile(WINSOR_Q[1])
        df[col] = df[col].clip(lower=lo, upper=hi)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 7. Telemetry Aggregation: Mili-giây → Cấp độ Vòng (Gold Layer)
# ─────────────────────────────────────────────────────────────────────────────

def aggregate_telemetry_to_lap(car_data: pd.DataFrame) -> pd.DataFrame:
    """
    Nén dữ liệu telemetry từ cấp độ mili-giây về cấp độ vòng chạy.

    Kỹ thuật "Nén đa chiều" — giữ lại hình dáng của chuỗi thời gian:
      - max(Speed): Tốc độ tối đa trên đoạn thẳng (sức mạnh động cơ / DRS)
      - min(Speed): Tốc độ vào cua (khả năng kiểm soát góc cua)
      - mean(Throttle): Tỷ lệ đạp ga trung bình
      - q90(Throttle): Giữ trạng thái gần lút ga trên đoạn thẳng
      - std(RPM): Độ nhất quán khi đi số (số gật cục = std cao)

    Chống Data Leakage:
      Vòng 10 chỉ được nhìn thấy telemetry của Vòng 9 (dung shift(1)).

    Args:
        car_data: DataFrame từ cleaned/car_data.parquet.

    Returns:
        DataFrame ở cấp độ (session_key, driver_number, lap_number)
        với các cột telemetry đã được dịch sang vòng trước (lag-1).
    """
    required = {"session_key", "driver_number", "lap_number"}
    if car_data.empty or not required.issubset(car_data.columns):
        return pd.DataFrame()

    group_keys = ["session_key", "driver_number", "lap_number"]

    # Xây dựng các hàm aggregation theo từng cột có trong data
    agg_spec = {}
    if "Speed" in car_data.columns:
        agg_spec["Speed"] = ["max", "min", "mean", "std"]
    if "Throttle" in car_data.columns:
        agg_spec["Throttle"] = ["mean", lambda x: x.quantile(0.9)]
    if "Brake" in car_data.columns:
        agg_spec["Brake"] = ["mean", "sum"]      # mean=tỷ lệ phanh, sum=tổng lần phanh
    if "RPM" in car_data.columns:
        agg_spec["RPM"] = ["mean", "std"]
    if "nGear" in car_data.columns:
        agg_spec["nGear"] = ["mean", "max"]
    if "DRS" in car_data.columns:
        agg_spec["DRS"] = ["sum"]               # tổng số điểm dữ liệu khi DRS bật

    if not agg_spec:
        return pd.DataFrame()

    agg = car_data.groupby(group_keys).agg(agg_spec)
    agg.columns = ["_".join([col, fn if not callable(fn) else "q90"]).strip()
                   for col, fn in agg.columns]
    agg = agg.reset_index()
    agg.columns = [c.lower() for c in agg.columns]   # Chuẩn hóa tên cột lowercase

    # ── Chống Data Leakage: shift(1) — Vòng N chỉ nhìn thấy dữ liệu Vòng N-1 ──
    agg = agg.sort_values(["session_key", "driver_number", "lap_number"])
    tele_feature_cols = [c for c in agg.columns if c not in group_keys]
    agg[tele_feature_cols] = agg.groupby(["session_key", "driver_number"])[tele_feature_cols].shift(1)

    # Đổi tên để rõ ràng là dữ liệu từ vòng trước (tele_prev_*)
    rename_map = {col: f"tele_prev_{col}" for col in tele_feature_cols}
    agg = agg.rename(columns=rename_map)

    logger.info(f"Telemetry aggregated: {len(agg):,} lap-level rows | {len(tele_feature_cols)} features (lag-1)")
    return agg


# ─────────────────────────────────────────────────────────────────────────────
# 8. Winsorization
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Main orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def build_feature_engineering(config_path=None, dry_run: bool = False) -> pd.DataFrame:
    """
    Build lap-level master dataset.
    Granularity: (session_key, driver_number, lap_number)
    """
    config = load_config(config_path)
    setup_logging()
    c = config.cleaned_dir

    laps = _read(c / "laps.csv")
    if laps.empty:
        raise RuntimeError("laps.csv missing — run clean_data first")

    sessions  = _read(c / "sessions.csv")
    drivers   = _read(c / "drivers.csv")
    stints    = _read(c / "stints.csv")
    weather   = _read(c / "weather.csv")
    position  = _read(c / "position.csv")
    results   = _read(c / "session_results.csv")
    car_data  = _read(c / "car_data.parquet")  # Telemetry — có thể rỗng nếu chưa crawl

    logger.info(f"Base laps: {len(laps):,} rows")

    # ── Join session metadata ──────────────────────────────────────────────
    if not sessions.empty:
        s_cols = [c for c in ["session_key", "year", "session_type", "circuit_key",
                               "circuit_short_name", "country_name", "date_start", "date_end"]
                  if c in sessions.columns]
        laps = laps.merge(sessions[s_cols].drop_duplicates("session_key"),
                          on="session_key", how="left", suffixes=("", "_sess"))

    # ── Join driver metadata ───────────────────────────────────────────────
    if not drivers.empty:
        d_cols = [c for c in ["session_key", "driver_number", "full_name", "name_acronym", "team_name"]
                  if c in drivers.columns]
        laps = laps.merge(drivers[d_cols].drop_duplicates(["session_key", "driver_number"]),
                          on=["session_key", "driver_number"], how="left")

    # ── Learn tyre cliffs ──────────────────────────────────────────────────
    cliffs = learn_tyre_cliffs(stints, laps)
    logger.info(f"Tyre cliffs: {cliffs}")

    # ── Feature steps ──────────────────────────────────────────────────────
    laps = add_stint_features(laps, stints, cliffs)
    logger.info("Stint features added")

    laps = add_rolling_features(laps)
    logger.info("Rolling features added")

    laps = add_weather_features(laps, weather)
    logger.info("Weather features added")

    laps = add_position_features(laps, position)
    logger.info("Position features added")

    laps = add_targets(laps, results)
    logger.info("Targets added")

    # ── Telemetry aggregation (Gold layer) — chỉ join nếu có dữ liệu đủ ──────
    if not car_data.empty:
        tele_agg = aggregate_telemetry_to_lap(car_data)
        if not tele_agg.empty:
            laps = laps.merge(tele_agg, on=["session_key", "driver_number", "lap_number"], how="left")
            tele_coverage = laps["tele_prev_speed_max"].notna().mean() if "tele_prev_speed_max" in laps.columns else 0
            logger.info(f"Telemetry joined | coverage: {tele_coverage:.1%} of laps")
            if tele_coverage < 0.3:
                logger.warning("Telemetry coverage < 30% — dữ liệu telemetry có thể quá ít. Kiểm tra data/raw/car_data/")
    else:
        logger.info("Telemetry (car_data) không có — bỏ qua aggregate. Chạy crawler để có dữ liệu.")

    laps = winsorize(laps)
    logger.info("Winsorization done")

    # ── Final cleanup ──────────────────────────────────────────────────────
    laps = laps.drop_duplicates(subset=["session_key", "driver_number", "lap_number"])
    laps = laps.reset_index(drop=True)

    logger.info(f"Master dataset: {len(laps):,} rows × {len(laps.columns)} cols")
    logger.info(f"Win rate: {laps['target_win'].mean():.3f} ({laps['target_win'].sum()} wins / {len(laps)} laps)")

    if dry_run:
        logger.info("[Dry Run] Skipping save")
        return laps

    write_csv(laps, config.processed_dir / "master_dataset.csv")
    try:
        laps.to_parquet(config.processed_dir / "master_dataset.parquet", index=False)
    except Exception as exc:
        logger.warning(f"Parquet save failed: {exc}")

    write_json({
        "built_at": utc_now_iso(),
        "rows": len(laps),
        "cols": len(laps.columns),
        "tyre_cliffs_used": cliffs,
        "win_rate": float(laps["target_win"].mean()) if "target_win" in laps.columns else None,
    }, config.metadata_dir / "feature_engineering_metadata.json")

    return laps


if __name__ == "__main__":
    setup_logging()
    build_feature_engineering()
