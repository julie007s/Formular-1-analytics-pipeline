from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from .config import load_config
from .utils import read_csv, setup_logging, write_csv, write_markdown


logger = logging.getLogger(__name__)


REQUIRED_FILES = {
    "sessions.csv":         ["session_key"],
    "drivers.csv":          ["session_key", "driver_number"],
    "laps.csv":             ["session_key", "driver_number", "lap_number"],
    "weather.csv":          ["session_key"],
    "stints.csv":           ["session_key", "driver_number"],
    "position.csv":         ["session_key", "driver_number"],
    "session_results.csv":  ["session_key", "driver_number"],  # Fix #12: bắt buộc kiểm tra
    "starting_grid.csv":    ["session_key", "driver_number"],  # Fix #12: bắt buộc kiểm tra
}


def check_required_columns(df: pd.DataFrame, filename: str, columns: list[str]) -> list[dict[str, Any]]:
    issues = []
    missing = [col for col in columns if col not in df.columns]
    if missing:
        issues.append({
            "file": filename,
            "severity": "error",
            "check": "required_columns",
            "message": f"Missing required columns: {missing}",
        })
    return issues


def check_duplicate_key(df: pd.DataFrame, filename: str, key: list[str]) -> list[dict[str, Any]]:
    if not all(col in df.columns for col in key):
        return []
    duplicates = int(df.duplicated(subset=key).sum())
    if duplicates:
        return [{
            "file": filename,
            "severity": "warning",
            "check": "duplicate_key",
            "message": f"Found {duplicates} duplicate rows for key={key}",
        }]
    return []


def check_range(df: pd.DataFrame, filename: str, column: str, lower: float, upper: float) -> list[dict[str, Any]]:
    if column not in df.columns:
        return []
    values = pd.to_numeric(df[column], errors="coerce")
    invalid = int((values.notna() & ~values.between(lower, upper)).sum())
    if invalid:
        return [{
            "file": filename,
            "severity": "warning",
            "check": "range",
            "message": f"Column {column} has {invalid} values outside [{lower}, {upper}]",
        }]
    return []


def validate_cleaned_data(config_path: str | None = None) -> pd.DataFrame:
    config = load_config(config_path)
    issues: list[dict[str, Any]] = []

    key_map = {
        "sessions.csv": ["session_key"],
        "drivers.csv": ["session_key", "driver_number"],
        "laps.csv": ["session_key", "driver_number", "lap_number"],
        "weather.csv": ["session_key"],
        "stints.csv": ["session_key", "driver_number", "stint_number"],
        "position.csv": ["session_key", "driver_number", "date"],
        "starting_grid.csv": ["session_key", "driver_number"],
        "session_results.csv": ["session_key", "driver_number"],
    }

    # 1. Basic checks (Existing)
    for filename, required_cols in REQUIRED_FILES.items():
        path = config.cleaned_dir / filename
        if not path.exists():
            issues.append({
                "file": filename, "severity": "warning", "check": "file_exists", "message": "File missing"
            })
            continue

        df = read_csv(path)
        issues.extend(check_required_columns(df, filename, required_cols))
        issues.extend(check_duplicate_key(df, filename, key_map.get(filename, required_cols)))

        # Range checks
        if filename in {"starting_grid.csv", "session_results.csv", "position.csv"}:
            issues.extend(check_range(df, filename, "position", 1, 25))
        if filename == "laps.csv":
            issues.extend(check_range(df, filename, "lap_duration", 30, 600))

        # 2. Missing Values Analysis
        null_counts = df.isnull().sum()
        for col, count in null_counts.items():
            if count > 0:
                pct = (count / len(df)) * 100
                severity = "error" if pct > 50 else "warning"
                issues.append({
                    "file": filename, "severity": severity, "check": "missing_values",
                    "message": f"Column {col} has {count} nulls ({pct:.1f}%)"
                })

    # 3. Cross-Table Consistency
    sessions_path = config.cleaned_dir / "sessions.csv"
    if sessions_path.exists():
        sessions_df = read_csv(sessions_path)
        valid_sessions = set(sessions_df["session_key"].unique())
        
        for filename in ["drivers.csv", "laps.csv", "weather.csv"]:
            path = config.cleaned_dir / filename
            if path.exists():
                df = read_csv(path)
                if "session_key" in df.columns:
                    orphans = df[~df["session_key"].isin(valid_sessions)]
                    if not orphans.empty:
                        count = orphans["session_key"].nunique()
                        issues.append({
                            "file": filename, "severity": "error", "check": "consistency",
                            "message": f"Found data for {count} session(s) not present in sessions.csv"
                        })

    report_df = pd.DataFrame(issues, columns=["file", "severity", "check", "message"])
    write_csv(report_df, config.reports_dir / "validation_report.csv")

    if report_df.empty:
        markdown = "# Validation Report\n\nNo validation issues found.\n"
    else:
        markdown = "# Validation Report\n\n" + report_df.to_markdown(index=False) + "\n"
    write_markdown(markdown, config.reports_dir / "validation_report.md")

    error_count = 0 if report_df.empty else int((report_df["severity"] == "error").sum())
    logger.info("Validation complete with %s issue(s), %s error(s)", len(report_df), error_count)
    return report_df


if __name__ == "__main__":
    setup_logging()
    validate_cleaned_data()
