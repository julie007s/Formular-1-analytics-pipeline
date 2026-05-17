from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - handled at runtime with clear message
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "pipeline_config.yaml"


@dataclass(frozen=True)
class PipelineConfig:
    raw: dict[str, Any]
    path: Path

    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT

    @property
    def steps_to_run(self) -> list[str]:
        # Mặc định chạy tất cả nếu không có config
        exec_cfg = self.raw.get("execution", {})
        return list(exec_cfg.get("steps_to_run", ["crawl", "clean", "base", "feature"]))

    @property
    def start_year(self) -> int:
        return int(self.raw["data"]["start_year"])

    @property
    def end_year(self) -> int:
        return int(self.raw["data"]["end_year"])

    @property
    def base_url(self) -> str:
        return str(self.raw["api"]["base_url"]).rstrip("/")

    @property
    def session_types(self) -> list[str]:
        return list(self.raw["sessions"]["types"])

    @property
    def include_future_sessions(self) -> bool:
        return bool(self.raw["sessions"].get("include_future_sessions", True))

    @property
    def limit_sessions(self) -> int:
        return int(self.raw["sessions"].get("limit_sessions", 99))

    @property
    def per_year_endpoints(self) -> list[str]:
        return list(self.raw["raw_endpoints"].get("per_year", []))

    @property
    def per_session_endpoints(self) -> list[str]:
        return list(self.raw["raw_endpoints"]["per_session"])

    def data_path(self, key: str) -> Path:
        value = self.raw["data"][key]
        return self.project_root / value

    @property
    def raw_dir(self) -> Path:
        return self.data_path("raw_dir")

    @property
    def interim_dir(self) -> Path:
        return self.data_path("interim_dir")

    @property
    def cleaned_dir(self) -> Path:
        return self.data_path("cleaned_dir")

    @property
    def processed_dir(self) -> Path:
        return self.data_path("processed_dir")

    @property
    def preview_dir(self) -> Path:
        return self.data_path("preview_dir")

    @property
    def metadata_dir(self) -> Path:
        return self.data_path("metadata_dir")

    @property
    def reports_dir(self) -> Path:
        return self.data_path("reports_dir")

    @property
    def sleep_seconds(self) -> float:
        return float(self.raw["api"]["sleep_seconds"])

    @property
    def retry_wait_seconds(self) -> float:
        return float(self.raw["api"]["retry_wait_seconds"])

    @property
    def max_retries(self) -> int:
        return int(self.raw["api"]["max_retries"])

    @property
    def timeout_seconds(self) -> int:
        return int(self.raw["api"]["timeout_seconds"])

    @property
    def resample_interval(self) -> str | None:
        """Khoảng resample cho telemetry. None = không resample (giữ nguyên raw)."""
        value = self.raw.get("telemetry", {}).get("resample_interval")
        if value is None or str(value).strip().lower() in ("none", "null", "~", ""):
            return None
        return str(value)


def load_config(config_path: str | Path | None = None) -> PipelineConfig:
    if yaml is None:
        raise RuntimeError("PyYAML is required to load configs. Install it with: pip install pyyaml")

    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    return PipelineConfig(raw=raw, path=path)
