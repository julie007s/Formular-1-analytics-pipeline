import logging
from pathlib import Path
from src.crawler import run_crawler
from src.clean_data import clean_all
from src.build_base_dataset import build_base_dataset
from src.feature_engineering import build_feature_engineering
from src.utils import setup_logging
from src.config import load_config

logger = logging.getLogger("E2E_Pipeline")

# ── Danh sách tất cả các bước theo thứ tự ────────────────────────────────────
ALL_STEPS = ["crawl", "clean", "base", "feature"]


def run_e2e_pipeline(
    steps: list[str] | None = None,
    start_from: str | None = None,
    dry_run: bool = False,
) -> None:
    """
    Chạy pipeline F1 — toàn bộ hoặc từng phần.

    Cách dùng:
      run_e2e_pipeline()                              # Chạy tất cả 4 bước
      run_e2e_pipeline(steps=["clean", "feature"])    # Chỉ chạy 2 bước này
      run_e2e_pipeline(start_from="base")             # Chạy từ bước 3 trở đi
      run_e2e_pipeline(steps=["feature"], dry_run=True)  # Thử lại bước 4

    Args:
        steps      : Danh sách các bước muốn chạy. None = chạy tất cả.
        start_from : Bắt đầu từ bước này trở đi (bỏ qua các bước trước).
        dry_run    : Nếu True, không lưu file nào ra đĩa.
    """
    setup_logging()
    config = load_config()

    # ── Xác định các bước cần chạy từ Config ──────────────────────────────────
    if steps:
        to_run = [s for s in ALL_STEPS if s in steps]
    elif start_from:
        idx = ALL_STEPS.index(start_from)
        to_run = ALL_STEPS[idx:]
    else:
        # Lấy từ file cấu hình yaml
        to_run = [s for s in ALL_STEPS if s in config.steps_to_run]

    print("\n" + "=" * 60)
    print("   F1 DATA PIPELINE")
    print(f"   Năm: {config.start_year} → {config.end_year}")
    print(f"   Bước chạy: {' → '.join(to_run)}")
    if dry_run:
        print("   ⚠️  DRY-RUN MODE")
    print("=" * 60)

    # ── STEP 1: CRAWL ─────────────────────────────────────────────────────────
    if "crawl" in to_run:
        print("\n[STEP 1] Crawling data (OpenF1 + FastF1)...")
        crawl_meta = run_crawler(dry_run=dry_run)
        print(f"  Tổng session đã crawl: {crawl_meta.get('total_sessions', 0)}")
    else:
        print("\n[STEP 1] Crawl — BỎ QUA")

    # ── STEP 2: CLEAN ─────────────────────────────────────────────────────────
    if "clean" in to_run:
        print("\n[STEP 2] Cleaning data (Bronze → Silver)...")
        clean_all(dry_run=dry_run)
    else:
        print("\n[STEP 2] Clean — BỎ QUA")

    # ── STEP 3: BUILD BASE DATASET ────────────────────────────────────────────
    if "base" in to_run:
        print("\n[STEP 3] Building session-level base dataset...")
        base = build_base_dataset(dry_run=dry_run)
        print(f"  Base dataset: {base.shape[0]:,} rows × {base.shape[1]} cols")
    else:
        print("\n[STEP 3] Base — BỎ QUA")

    # ── STEP 4: FEATURE ENGINEERING ───────────────────────────────────────────
    if "feature" in to_run:
        print("\n[STEP 4] Feature engineering (lap-level master)...")
        master = build_feature_engineering(dry_run=dry_run)
        print(f"  Master dataset: {master.shape[0]:,} rows × {master.shape[1]} cols")
    else:
        print("\n[STEP 4] Feature — BỎ QUA")

    # ── HOÀN TẤT ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("   ✅ PIPELINE HOÀN TẤT!")
    print("=" * 60)


if __name__ == "__main__":
    # ┌─────────────────────────────────────────────────────────┐
    # │  ĐIỀU KHIỂN PIPELINE QUA FILE CẤU HÌNH                │
    # │  Vào file: configs/pipeline_config.yaml                 │
    # │  Tìm mục: execution -> steps_to_run                     │
    # │  Thêm/Xóa các bước: crawl, clean, base, feature         │
    # └─────────────────────────────────────────────────────────┘

    # Không truyền argument, để hệ thống tự động đọc từ YAML
    run_e2e_pipeline()
