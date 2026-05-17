# Data Dictionary

## Main Handoff Table

| File | Grain | Primary Key | Purpose |
|---|---|---|---|
| `data/processed/driver_session_base.csv` | driver-session | `session_key + driver_number` | Main ML handoff table |

## Quality Reports

| File | Purpose |
|---|---|
| `reports/data_quality/cleaning_summary.md` | Rows read, rows kept, rows dropped by cleaning step |
| `reports/data_quality/validation_report.md` | Schema, key and range validation issues |
| `reports/data_quality/base_dataset_report.md` | Final base dataset shape summary |

## Key Columns

| Column | Description |
|---|---|
| `session_key` | OpenF1 session identifier |
| `driver_number` | Driver racing number |
| `year` | Season year |
| `session_type` | Session type such as Race or Qualifying |
| `circuit_key` | Circuit identifier |
| `grid_position` | First observed position for the session-driver pair |
| `final_position` | Last observed position for the session-driver pair |
| `target_win` | Helper label: final position equals 1 |
| `target_podium` | Helper label: final position between 1 and 3 |
| `target_top10` | Helper label: final position between 1 and 10 |
| `avg_lap_duration` | Mean lap duration for driver-session |
| `best_lap_duration` | Best lap duration for driver-session |
| `air_temperature_mean` | Mean air temperature for the session |
| `track_temperature_mean` | Mean track temperature for the session |
| `rainfall_max` | Maximum rainfall indicator for the session |
