# Báo Cáo Chuyên Đề: Tiền Xử Lý Dữ Liệu và Trích Xuất Đặc Trưng Cho Mô Hình Phân Tích Giải Đua F1
*(Tài liệu chuẩn hóa dưới dạng Mini-Paper phục vụ báo cáo khoa học/luận văn)*

---

## Tóm tắt (Abstract)
Nghiên cứu này trình bày phương pháp tiếp cận toàn diện trong việc xây dựng hệ thống dữ liệu (Data Pipeline) nhằm dự đoán tỷ lệ chiến thắng (Win Rate) trong giải đua xe Công thức 1 (Formula 1). Hệ thống giải quyết các thách thức về giới hạn truy xuất API và khối lượng dữ liệu khổng lồ của Telemetry thông qua cơ chế thu thập đa luồng và định dạng lưu trữ nén cột (Parquet). Hơn nữa, nghiên cứu áp dụng kiến trúc lưu trữ Medallion để làm sạch dữ liệu và đề xuất các phương pháp trích xuất đặc trưng nâng cao như: Mô hình hóa tuổi thọ lốp (Tyre Cliff), biến thiên nhiệt độ, và dịch chuyển dữ liệu thời gian (Temporal Data Shift) nhằm ngăn chặn rò rỉ dữ liệu (Data Leakage). Kết quả đầu ra là một bộ dữ liệu (dataset) chất lượng cao ở cấp độ vòng đua (lap-level), tích hợp 60 đặc trưng sẵn sàng cho các mô hình Machine Learning.

---

## 1. Giới thiệu (Introduction)
Dự đoán kết quả giải đua F1 là một bài toán phức tạp do sự phụ thuộc vào nhiều yếu tố phi tuyến tính như kỹ năng tay đua, chiến thuật vào pit, và điều kiện môi trường. Tuy nhiên, rào cản lớn nhất đối với các mô hình Machine Learning trong lĩnh vực này là việc thiếu hụt một bộ dữ liệu chuẩn hóa, tích hợp đầy đủ thông tin từ nhiều nguồn khác nhau (thời tiết, vị trí, xe, và telemetry). Mục tiêu của nghiên cứu này là xây dựng một quy trình Tiền xử lý Dữ liệu End-to-End, từ khâu thu thập tự động đến việc định dạng lại dữ liệu phục vụ trực tiếp cho mô hình phân lớp đa mục tiêu (Multi-target Classification).

## 2. Phương pháp luận (Methodology)

### 2.1. Hệ thống Thu thập Dữ liệu Tự động (Automated Crawler)
Dữ liệu được khai thác từ OpenF1 API và thư viện FastF1. Để giải quyết giới hạn 30 requests/phút của API, hệ thống tích hợp thuật toán **Thread-safe Rate Limiter**. Quá trình tải dữ liệu được tối ưu hóa thông qua cơ chế **I/O Bound Multithreading** cho các endpoint độc lập. Riêng đối với dữ liệu Telemetry có độ phân giải mili-giây (khoảng 3.5 triệu dòng/chặng), hệ thống áp dụng định dạng lưu trữ **Parquet với chuẩn nén Zstandard (zstd)** để giảm tải I/O và tiết kiệm bộ nhớ.

### 2.2. Kiến trúc Dữ liệu Medallion (Medallion Data Architecture)
Quá trình xử lý dữ liệu tuân thủ nghiêm ngặt kiến trúc 3 phân tầng:
* **Tầng Bronze (Raw):** Lưu trữ dữ liệu thô nguyên bản từ các API, phân mảnh theo từng session và endpoint để dễ dàng quản lý vòng đời dữ liệu.
* **Tầng Silver (Cleaned):** Thực hiện chuẩn hóa kiểu dữ liệu. Các vòng đua không hoàn thành (DNF) được loại bỏ. Các lỗi cảm biến (Speed > 400 km/h) được nội suy (Imputation) bằng trung vị của tay đua (Driver-specific Median).
* **Tầng Gold (Processed):** Hợp nhất các bảng dữ liệu thành một cấu trúc phẳng (Flattened structure) dựa trên khóa chính (`session_key`, `driver_number`, `lap_number`).

### 2.3. Quy trình thực thi Luồng Dữ liệu (Data Pipeline Flow)
Hệ thống được thiết kế theo luồng xử lý 4 giai đoạn nối tiếp (Sequential Pipeline) được điều khiển tập trung thông qua tệp cấu hình (Config-driven):

1. **Giai đoạn Khai thác (Crawl Phase):** Hệ thống quét 18 endpoints độc lập. Dữ liệu bảng (tabular data) được gọi qua REST API của OpenF1 và lưu dưới dạng CSV. Dữ liệu Telemetry được gọi qua FastF1, nén thành định dạng Parquet. Hệ thống tự động bỏ qua (skip) các tệp đã tồn tại để tối ưu thời gian.
2. **Giai đoạn Làm sạch (Clean Phase):** Hệ thống nạp (load) từng phân mảnh dữ liệu của Tầng Bronze vào bộ nhớ. Áp dụng 11 hàm làm sạch chuyên biệt (vd: `clean_laps`, `clean_telemetry`). Lọc bỏ các vòng đua khuyết thiếu thời gian (`NaT`), giới hạn giá trị vật lý (Hard-bounds) và xuất báo cáo chất lượng (Data Quality Audit).
3. **Giai đoạn Xây dựng Dữ liệu Nền (Base Phase):** Hợp nhất các siêu dữ liệu (Metadata) như thông tin chặng đua (`sessions`), tay đua (`drivers`), và lưới xuất phát (`starting_grid`) để tạo ra khung dữ liệu chuẩn (`driver_session_base.csv`). Bước này thiết lập không gian mẫu (Sample space) cho toàn bộ mô hình.
4. **Giai đoạn Kỹ thuật Đặc trưng (Feature Phase):** Là giai đoạn phức tạp nhất, thực hiện nội suy không gian-thời gian (Spatio-temporal Merge_asof) để ráp nối dữ liệu thời tiết và lốp xe vào từng vòng đua. Xử lý logic chuỗi thời gian (Time-series shifting) và tổng hợp 60 đặc trưng đầu ra.

## 3. Trích xuất Đặc trưng (Feature Engineering)
Nhằm cung cấp khả năng tổng quát hóa cao cho mô hình Machine Learning, nghiên cứu đề xuất các phương pháp kỹ thuật dữ liệu sau:

### 3.1. Ngăn chặn rò rỉ dữ liệu (Temporal Data Shift)
Để đảm bảo tính thực tiễn (có thể dự đoán Live), tất cả các đặc trưng động (vị trí, thời tiết, trạng thái lốp) của vòng $N$ đều được thực hiện phép tịnh tiến thời gian (Shift). Mô hình dự đoán kết quả tại vòng $N+1$ hoàn toàn dựa trên bối cảnh đã biết từ vòng $N$, loại bỏ rủi ro Data Leakage.

### 3.2. Mô hình hóa hao mòn lốp (Tyre Degradation Modeling)
Độ mòn của lốp F1 mang tính phi tuyến (Tyre Cliff). Nghiên cứu tính toán giới hạn tuổi thọ của từng loại lốp (Compound) dựa trên thống kê thực nghiệm, từ đó trích xuất các đặc trưng chiến thuật như: `current_tyre_age`, `laps_until_cliff`, và cờ `is_past_cliff`.

### 3.3. Tổng hợp đa chiều (Multi-dimensional Aggregation)
* **Phong độ tức thời (Rolling Performance):** Áp dụng cửa sổ trượt (Rolling Windows 3, 5, 10 vòng) để tính toán trung bình động (Moving Average) và độ lệch chuẩn (Moving Std) của thời gian hoàn thành vòng đua.
* **Động lực học chặng đua (Race Dynamics):** Xây dựng các chỉ số đánh giá mức độ cạnh tranh như `position_gain_lap` (biến thiên vị trí trong 1 vòng) và `track_temp_evolution` (độ dốc thay đổi nhiệt độ mặt đường).

## 4. Kết quả (Results)
Hệ thống đã tự động xây dựng thành công bộ dữ liệu `master_dataset.csv`. Cấu trúc bộ dữ liệu có độ hạt (Grain) ở mức vòng đua (Lap-level). Mỗi quan sát (observation) bao gồm 60 đặc trưng thuộc 4 nhóm chính: Định danh, Viễn trắc học (Telemetry Aggregation), Chiến thuật, và Môi trường. Bộ dữ liệu tích hợp sẵn 3 nhãn phân lớp mục tiêu (Target variables): `target_win`, `target_podium`, và `target_top10`, sẵn sàng cho giai đoạn huấn luyện mô hình.

## 5. Kết luận (Conclusion)
Nghiên cứu đã giải quyết trọn vẹn bài toán Tiền xử lý dữ liệu cho giải đua F1. Hệ thống Data Pipeline không chỉ tự động hóa toàn bộ quy trình mà còn áp dụng các kỹ thuật xử lý dữ liệu phức tạp để trích xuất ra một tập đặc trưng giàu thông tin, đóng vai trò nền tảng quyết định độ chính xác cho các mô hình AI dự đoán Win Rate.
