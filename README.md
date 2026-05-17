# 🏎️ F1 WinRate Predictor — Trái tim Dữ liệu (Data Pipeline)

Chào mừng bạn đến với **F1 WinRate Predictor**. Đây không chỉ là một dự án cào dữ liệu thông thường, mà là một hệ thống **Kỹ thuật Dữ liệu Tự động (Automated Data Engineering Pipeline)** đạt chuẩn doanh nghiệp, được thiết kế chuyên biệt để dự đoán tỷ lệ chiến thắng trong giải đua xe Công thức 1 (F1).

Dự án này đảm nhiệm vai trò cực kỳ quan trọng: **Thu thập -> Làm sạch -> Chế biến** hàng triệu dòng dữ liệu thô thành những "viên kim cương" tính năng (Features) để các kỹ sư AI (Machine Learning) có thể trực tiếp huấn luyện mô hình dự đoán.

---

## 🏛️ Kiến trúc Dữ liệu 3 Lớp (Medallion Architecture)

Chúng tôi áp dụng mô hình chuẩn ngành Dữ liệu để đảm bảo chất lượng:

1. 🥉 **Tầng Bronze (Dữ liệu Thô - RAW):**
   * Tự động thu thập dữ liệu từ OpenF1 API và FastF1 (độ trễ mili-giây).
   * **Bao gồm:** Thời tiết, thời gian vòng đua, lịch sử thay lốp (stints), bộ đàm (team radio) và đặc biệt là Telemetry (Tốc độ, Chân ga, Phanh của từng xe).
   * *Nơi lưu trữ:* `data/raw/`

2. 🥈 **Tầng Silver (Dữ liệu Sạch - CLEANED):**
   * **"Máy lọc nước":** Loại bỏ các lỗi cảm biến, lọc bỏ các vòng đua không hợp lệ (xe hỏng, cờ đỏ), và tự động điền các thông tin bị thiếu bằng thuật toán thống kê.
   * Dữ liệu nhẹ và tốc độ đọc cực nhanh nhờ định dạng `.parquet`.
   * *Nơi lưu trữ:* `data/cleaned/`

3. 🥇 **Tầng Gold (Dữ liệu Sẵn sàng cho AI - PROCESSED):**
   * **"Phòng pha chế":** Từ dữ liệu sạch, chúng tôi tính toán ra 60 tính năng nâng cao vô giá:
     * *Độ mòn lốp (Tyre Cliff)*: AI tự học để biết khi nào lốp xe sắp "đổ đèo" mất độ bám.
     * *Áp lực cạnh tranh*: Tay đua đang đứng thứ mấy, vừa vượt bao nhiêu người?
     * *Bối cảnh thời tiết*: Nhiệt độ mặt đường đang nóng lên hay lạnh đi?
     * *Phong độ tức thời*: Tính toán trung bình động (Rolling Average) phong độ 3, 5, 10 vòng gần nhất.
   * *Nơi lưu trữ:* `data/processed/master_dataset.csv` (Dữ liệu từng vòng) và `driver_session_base.csv` (Dữ liệu toàn chặng).

---

## 🚀 Hướng dẫn Cài đặt & Sử dụng (Cho người mới bắt đầu)

### 1. Cài đặt môi trường
Bạn chỉ cần mở Terminal (Command Prompt / PowerShell) và gõ:
```bash
# Cài đặt toàn bộ thư viện cần thiết
pip install -r requirements.txt
```

### 2. Cách điều khiển Hệ thống
Bạn **không cần biết code** để điều khiển hệ thống này! Chúng tôi đã thiết kế một "Bảng điều khiển" thân thiện tại file: `configs/pipeline_config.yaml`.

Hãy mở file đó lên, bạn sẽ thấy mục `execution`:
```yaml
execution:
  steps_to_run:
    - crawl    # Tải dữ liệu từ mạng về
    - clean    # Làm sạch dữ liệu
    - base     # Gộp dữ liệu cơ bản
    - feature  # Chế biến tính năng cho AI
```
* **Mẹo:** Bạn đã tải xong dữ liệu và chỉ muốn làm sạch lại? Rất đơn giản, hãy thêm dấu `#` trước chữ `- crawl` để hệ thống tự động bỏ qua bước tải mạng (tiết kiệm hàng giờ đồng hồ!).

### 3. Khởi chạy
Sau khi cấu hình xong trong file `.yaml`, bạn chỉ cần gõ 1 lệnh duy nhất để hệ thống tự động làm mọi việc còn lại:
```bash
python run_e2e_pipeline.py
```
Hãy pha một tách cà phê, ngồi xem các dòng trạng thái hiển thị và chờ thông báo **`✅ PIPELINE HOÀN TẤT!`**.

---

## 🎯 Đầu ra dành cho Đội Machine Learning (Handoff Contract)

Sản phẩm cuối cùng mà AI sẽ học nằm tại:
👉 `data/processed/master_dataset.csv`

**Cấu trúc dữ liệu (Grain):**
* Mỗi dòng (row) = **1 vòng chạy** của **1 tay đua** trong **1 trận đấu**.
* Khóa chính (Primary Key): `session_key` + `driver_number` + `lap_number`

**Nhãn dự đoán (Targets):** Đã được hệ thống tự động gán nhãn sẵn ở cột cuối cùng:
* `target_win`: Bằng 1 nếu tay đua vô địch trận đó.
* `target_podium`: Bằng 1 nếu tay đua lọt Top 3.
* `target_top10`: Bằng 1 nếu tay đua có điểm.

Hệ thống xử lý cũng đã áp dụng kỹ thuật **Dịch chuyển dữ liệu (Data Shift)** cực kỳ khắt khe để đảm bảo AI không bao giờ bị "nhìn trộm" tương lai (Data Leakage), giúp mô hình dự đoán chính xác và thực tế nhất.

---
*Chúc bạn có những mô hình AI bứt phá tốc độ cùng F1 WinRate Predictor! 🏎️💨*
