# Handoff to ML Team

## Scope

This repository prepares data only. It does not train models or run predictions.

## Main File

Use:

```text
data/processed/driver_session_base.csv
```

Optional parquet version:

```text
data/processed/driver_session_base.parquet
```

## Grain

One row represents one driver in one session.

Primary key:

```text
session_key + driver_number
```

## Recommended Usage

Use this file as the starting table for training or prediction feature engineering.

Do not start from raw files unless you need to debug source data.

## Important Columns

| Column | Meaning |
|---|---|
| `session_key` | OpenF1 session identifier |
| `driver_number` | Driver racing number |
| `year` | Season year |
| `session_type` | Race, Sprint, Qualifying, etc. |
| `circuit_key` | Circuit identifier |
| `grid_position` | First observed position from position stream |
| `final_position` | Last observed position from position stream |
| `target_win` | 1 if final position is 1 |
| `target_podium` | 1 if final position is between 1 and 3 |
| `target_top10` | 1 if final position is between 1 and 10 |

## Caveats

- `grid_position` and `final_position` are derived from OpenF1 position data when dedicated result files are unavailable.
- Missing values are intentionally reported rather than silently over-imputed.
- Telemetry raw data is not joined into this table because it is large and high-frequency.
- Always inspect `reports/data_quality/validation_report.md` before training.

## Data Quality Reports

Before modeling, check:

```text
reports/data_quality/cleaning_summary.md
reports/data_quality/validation_report.md
reports/data_quality/base_dataset_report.md
```
