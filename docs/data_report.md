# Báo cáo dữ liệu F1: Raw API và Telemetry

## 1. Mục tiêu dữ liệu

Project `F1_WinRate_Predictor` đang thu thập dữ liệu Formula 1 từ hai nguồn chính:

1. **OpenF1 API**
   - Lưu vào `data/raw/*.csv`.
   - Chứa dữ liệu ngữ cảnh cuộc đua: sessions, drivers, laps, weather, intervals, position,
     race control, stints, kết quả session, starting grid.

2. **FastF1 API / FastF1 cache**
   - Lưu vào dạng partitioned parquet dưới `data/year=.../event=.../session=.../data.parquet`.
   - Chứa dữ liệu telemetry xe và location đã resample về 1 giây.

Mục tiêu của pipeline hiện tại là tạo nền dữ liệu đủ để phân tích và xây dựng mô hình dự đoán F1,
trong đó `raw` giữ dữ liệu dạng bảng từ OpenF1, còn `telemetry` giữ tín hiệu vận hành xe theo thời gian.

---

## 2. Cấu hình thu thập dữ liệu

File cấu hình chính: [pipeline_config.yaml](file:///d:/F1_WinRate_Predictor/configs/pipeline_config.yaml)

Các thông số quan trọng:

| Nhóm | Giá trị | Ý nghĩa |
|---|---:|---|
| `data.start_year` | `2024` | Năm bắt đầu lấy dữ liệu |
| `data.end_year` | `2026` | Năm kết thúc lấy dữ liệu |
| `api.base_url` | `https://api.openf1.org/v1` | Nguồn OpenF1 API |
| `sessions.include_future_sessions` | `false` | Không lấy session tương lai/chưa diễn ra |
| `telemetry.resample_interval` | `1000ms` | Telemetry/location được gom về 1 giây |

Các loại session được lấy:

- `Race`
- `Sprint`
- `Qualifying`
- `Sprint Shootout`
- `Sprint Qualifying`

---

## 3. Dữ liệu raw từ OpenF1

Script chính: [fetch_raw.py](file:///d:/F1_WinRate_Predictor/src/fetch_raw.py)

### 3.1 Cách lấy dữ liệu

Quy trình trong `fetch_raw.py`:

1. Load config từ `configs/pipeline_config.yaml`.
2. Tạo `OpenF1Client`.
3. Fetch `sessions` theo từng năm từ `start_year` đến `end_year`.
4. Lọc bỏ future sessions nếu `include_future_sessions = false`.
5. Lấy `session_key` của các session type được cấu hình.
6. Fetch endpoint theo năm, ví dụ `meetings`.
7. Fetch endpoint theo từng session, ví dụ `laps`, `weather`, `intervals`, `position`.
8. Lưu từng endpoint thành CSV trong `data/raw`.
9. Ghi metadata vào `data/metadata/fetch_raw_metadata.json`.

### 3.2 Các endpoint raw hiện có

Thư mục: [data/raw](file:///d:/F1_WinRate_Predictor/data/raw)

| File | Số dòng | Nội dung chính |
|---|---:|---|
| `drivers.csv` | 2,662 | Thông tin driver theo session |
| `intervals.csv` | 1,327,334 | Gap/interval giữa các xe trong session |
| `laps.csv` | 79,629 | Thông tin từng lap và sector |
| `meetings.csv` | 76 | Thông tin race weekend / meeting |
| `position.csv` | 109,231 | Vị trí xếp hạng của driver theo thời gian |
| `race_control.csv` | 8,876 | Flag, message, race control event |
| `session_results.csv` | 1,220 | Kết quả cuối session |
| `sessions.csv` | 277 | Danh sách session |
| `starting_grid.csv` | 1,220 | Vị trí xuất phát |
| `stints.csv` | 8,731 | Thông tin stint và tyre compound |
| `weather.csv` | 14,125 | Điều kiện thời tiết theo thời gian |

### 3.3 Chi tiết từng nhóm dữ liệu raw

#### `sessions.csv`

Các cột chính:

- `session_key`: khóa session, dùng để join với nhiều bảng khác.
- `meeting_key`: khóa meeting/race weekend.
- `session_type`: loại session, ví dụ Race, Qualifying.
- `date_start`, `date_end`: thời gian bắt đầu/kết thúc.
- `year`, `location`, `circuit_short_name`, `country_name`.

Vai trò:

- Là bảng trung tâm để xác định session nào cần lấy.
- Dùng để lọc session theo thời gian và loại session.

#### `meetings.csv`

Các cột chính:

- `meeting_key`
- `circuit_key`
- `circuit_short_name`
- `meeting_name`
- `location`
- `country_name`
- `year`

Vai trò:

- Cung cấp metadata về chặng đua.
- Có thể join với `sessions.csv` bằng `meeting_key`.

#### `drivers.csv`

Các cột chính:

- `driver_number`
- `session_key`
- `meeting_key`
- `full_name`
- `name_acronym`
- `team_name`
- `team_colour`
- `country_code`

Vai trò:

- Mapping số xe sang tên driver/team.
- Dùng để giải thích telemetry hoặc kết quả theo driver.

#### `laps.csv`

Các cột chính:

- `session_key`, `meeting_key`, `driver_number`
- `lap_number`
- `lap_duration`
- `duration_sector_1`, `duration_sector_2`, `duration_sector_3`
- `i1_speed`, `i2_speed`, `st_speed`
- `is_pit_out_lap`

Vai trò:

- Dữ liệu theo từng lap.
- Phù hợp để tạo feature ở cấp lap/session.

#### `intervals.csv`

Các cột chính:

- `date`
- `session_key`
- `meeting_key`
- `driver_number`
- `gap_to_leader`
- `interval`

Vai trò:

- Mô tả khoảng cách với leader hoặc xe phía trước.
- Đây là **race timing / race context data**, không phải car telemetry.

#### `position.csv`

Các cột chính:

- `date`
- `session_key`
- `meeting_key`
- `driver_number`
- `position`

Vai trò:

- Thể hiện thứ hạng race/order của driver theo thời gian.
- Khác với `x/y/z` location; `position` là vị trí xếp hạng, không phải tọa độ trên track.

#### `weather.csv`

Các cột chính:

- `date`
- `session_key`
- `meeting_key`
- `air_temperature`
- `track_temperature`
- `humidity`
- `pressure`
- `rainfall`
- `wind_direction`
- `wind_speed`

Vai trò:

- Bổ sung điều kiện môi trường.
- Có thể join theo `session_key` và thời gian gần nhất.

#### `stints.csv`

Các cột chính:

- `session_key`, `meeting_key`, `driver_number`
- `stint_number`
- `compound`
- `lap_start`, `lap_end`
- `tyre_age_at_start`

Vai trò:

- Dữ liệu chiến thuật tyre/stint.
- Nên join theo driver + lap range, không join trực tiếp theo timestamp.

#### `race_control.csv`

Các cột chính:

- `date`
- `session_key`, `meeting_key`
- `category`
- `flag`
- `message`
- `lap_number`
- `sector`
- `scope`

Vai trò:

- Ghi nhận safety car, yellow flag, red flag, track limits, race control messages.
- Dùng để tạo feature trạng thái race nếu cần.

#### `starting_grid.csv` và `session_results.csv`

Các cột chính:

- `session_key`
- `meeting_key`
- `driver_number`
- `position`
- `date`

Vai trò:

- `starting_grid`: vị trí xuất phát.
- `session_results`: kết quả cuối session.
- Có thể dùng làm nhãn hoặc feature tùy bài toán.

---

## 4. Dữ liệu telemetry/location từ FastF1

Script chính: [fetch_telemetry.py](file:///d:/F1_WinRate_Predictor/src/fetch_telemetry.py)

### 4.1 Cách lấy dữ liệu

Quy trình trong `fetch_telemetry.py`:

1. Gọi OpenF1 `/sessions?year=...` để lấy danh sách session.
2. Lọc session theo `SESSION_TYPES` và chỉ giữ session đã hoàn thành.
3. Với từng session:
   - gọi `fastf1.get_session(year, event_name, session_type)`.
   - gọi `fastf1_session.load(laps=False, telemetry=True, weather=False, messages=False)`.
   - lấy danh sách driver.
4. Với từng driver:
   - lấy `fastf1_session.car_data[driver_number]`.
   - lấy `fastf1_session.pos_data[driver_number]`.
   - convert `Time` sang `date = fastf1_session.date + Time`.
   - rename cột FastF1 sang tên chuẩn lowercase.
   - merge car data và location theo `date`.
5. Resample từng driver về `1000ms` bằng mean numeric.
6. Thêm metadata session.
7. Lưu thành parquet partitioned theo:

```text
data/year=<year>/event=<event>/session=<session_type>/data.parquet
```

Ví dụ:

```text
data/year=2026/event=Melbourne/session=Race/data.parquet
```

### 4.2 Dữ liệu nào được lấy từ FastF1

Từ `car_data`:

| FastF1 column | Output column | Ý nghĩa |
|---|---|---|
| `Time` | dùng tạo `date` | offset thời gian trong session |
| `Speed` | `speed` | tốc độ xe |
| `Throttle` | `throttle` | mức ga |
| `Brake` | `brake` | trạng thái/mức phanh nếu nguồn có |
| `nGear` | `gear` | số hiện tại |
| `RPM` | `rpm` | vòng tua máy |

Từ `pos_data`:

| FastF1 column | Output column | Ý nghĩa |
|---|---|---|
| `Time` | dùng tạo `date` | offset thời gian trong session |
| `X` | `x` | tọa độ xe trên track |
| `Y` | `y` | tọa độ xe trên track |
| `Z` | `z` | tọa độ độ cao/không gian nếu có |

Metadata thêm vào:

| Column | Ý nghĩa |
|---|---|
| `driver_number` | Số xe / driver id |
| `circuit_id` | Circuit key từ OpenF1 session |
| `session_key` | Session key từ OpenF1 |
| `session_type` | Race, Qualifying, Sprint... |
| `event_name` | Tên event/circuit ngắn |
| `year` | Năm |

### 4.3 Trạng thái telemetry hiện tại

Sau lần refetch mới nhất:

| Chỉ số | Giá trị |
|---|---:|
| Số file parquet telemetry | 105 |
| Tổng số dòng telemetry | 14,860,454 |
| Số schema quan sát được | 1 |

Schema hiện tại của toàn bộ 105 file:

```text
date
speed
throttle
gear
rpm
x
y
z
driver_number
circuit_id
session_key
session_type
event_name
year
```

> [!NOTE]
> Sau lần kiểm tra hiện tại, tất cả 105 file parquet có cùng schema trên.
> Cột `brake` chưa xuất hiện trong schema thực tế, dù code có hỗ trợ nếu FastF1 trả về `Brake`.

### 4.4 Các xử lý đã áp dụng cho telemetry

Các bước xử lý hiện tại:

1. **Chuẩn hóa thời gian**
   - FastF1 dùng `Time` là offset trong session.
   - Code chuyển thành timestamp thực:

```python
df["date"] = fastf1_session.date + df["Time"]
```

2. **Đổi tên cột**
   - `Speed` -> `speed`
   - `Throttle` -> `throttle`
   - `nGear` -> `gear`
   - `RPM` -> `rpm`
   - `X/Y/Z` -> `x/y/z`

3. **Merge car data và location**
   - `car_data` và `pos_data` được merge theo `date`.
   - Nếu location tồn tại thì output có `x/y/z`.

4. **Resample 1 giây**
   - Mỗi driver được gom về tần suất `1000ms`.
   - Cách aggregate: `mean(numeric_only=True)`.

5. **Xử lý jump bất thường của location**
   - Nếu `x` hoặc `y` nhảy quá `5000` đơn vị so với dòng trước, code đặt `NaN`.
   - Sau đó interpolate `x/y`.

6. **Ép dtype**
   - `speed`, `throttle`, `x`, `y`, `z`: `float32`.
   - `gear`: `int8`.
   - `rpm`: `int32`.
   - `driver_number`, `circuit_id`: integer nhỏ.

### 4.5 Những feature không còn nằm trong fetch layer

Theo quyết định hiện tại, fetch layer chỉ giữ **raw/resampled signals**.
Các feature engineered sau đã được bỏ khỏi telemetry parquet:

- `throttle_delta`
- `relative_speed`

Các feature này nên được tạo ở bước **feature engineering riêng**, không tạo trong bước crawl/fetch.

---

## 5. So sánh raw OpenF1 và telemetry FastF1

| Nhóm dữ liệu | Nguồn | Format | Tần suất | Vai trò |
|---|---|---|---|---|
| Sessions/meetings | OpenF1 | CSV | Theo session/meeting | Metadata |
| Drivers | OpenF1 | CSV | Theo driver-session | Mapping driver/team |
| Laps | OpenF1 | CSV | Theo lap | Hiệu năng lap/sector |
| Weather | OpenF1 | CSV | Time-series thưa | Điều kiện môi trường |
| Intervals | OpenF1 | CSV | Time-series race timing | Gap/context |
| Position | OpenF1 | CSV | Time-series race order | Thứ hạng driver |
| Race control | OpenF1 | CSV | Event-based | Flag/message |
| Car telemetry | FastF1 | Parquet | Resample 1 giây | Tín hiệu vận hành xe |
| Location | FastF1 | Parquet | Resample 1 giây | Tọa độ xe trên track |

---

## 6. Khóa join quan trọng

Các khóa thường dùng:

| Khóa | Dùng ở đâu | Ý nghĩa |
|---|---|---|
| `session_key` | Hầu hết raw + telemetry | Khóa session |
| `meeting_key` | Raw OpenF1 | Khóa race weekend |
| `driver_number` | Raw + telemetry | Khóa driver/xe |
| `date` | Time-series | Join theo thời gian |
| `year`, `event_name`, `session_type` | Telemetry parquet | Partition/metadata |

### Join raw với telemetry

Đối với dữ liệu time-series như `weather`, `intervals`, `position`:

- Join theo `session_key` + `driver_number` nếu có.
- Join thời gian nên dùng `nearest` hoặc `asof join`.
- Không nên assume timestamp khớp tuyệt đối.

Ví dụ logic hợp lý:

```text
telemetry.date ~ nearest intervals.date trong cùng session_key + driver_number
```

Đối với `stints`:

- Không join theo timestamp trực tiếp.
- Nên join theo `driver_number`, `session_key` và điều kiện:

```text
lap_start <= lap_number <= lap_end
```

Đối với `race_control`:

- Có thể tạo cờ trạng thái theo khoảng thời gian/lap.
- Không nên join 1-1 trực tiếp nếu message là event rời rạc.

---

## 7. Tìm hiểu dữ liệu và nhận xét ban đầu

### 7.1 Raw data

- `intervals.csv` là file raw lớn nhất với hơn 1.3 triệu dòng.
- `laps.csv` có gần 80 nghìn dòng, phù hợp cho feature ở cấp lap.
- `position.csv` có hơn 109 nghìn dòng, thể hiện race order theo thời gian.
- `weather.csv` nhỏ hơn nhiều, có thể dùng làm context chung cho session.

### 7.2 Telemetry data

- Telemetry hiện có hơn 14.8 triệu dòng.
- Mỗi file parquet tương ứng một tổ hợp:

```text
year + event + session
```

- Dữ liệu đã được resample về 1 giây nên dễ join hơn với các bảng time-series khác.
- Tuy nhiên, resample 1 giây làm mất tín hiệu rất ngắn hạn dưới 1 giây.

### 7.3 Location data

- `x/y/z` trong telemetry parquet là tọa độ xe từ FastF1 `pos_data`.
- Đây là vị trí vật lý/spatial position trên track.
- Không nên nhầm với `position.csv` của OpenF1, vì `position.csv` là thứ hạng race/order.

### 7.4 Dữ liệu 2026

Một số session 2026 chưa có telemetry/location đầy đủ từ FastF1:

- `Jeddah Qualifying`
- `Jeddah Race`
- `Miami Race`

Log cho thấy các session này có thể trả về:

```text
Car telemetry data is unavailable
Car position data is unavailable
Finished loading data for 0 drivers
```

Nguyên nhân có thể là FastF1 chưa cập nhật dữ liệu hoặc mapping event/session chưa ổn.

---

## 8. Các vấn đề chất lượng dữ liệu cần chú ý

### 8.1 Timestamp không đồng bộ tuyệt đối

Các nguồn có tần suất khác nhau:

- FastF1 telemetry/location: dày, đã resample 1 giây.
- OpenF1 intervals/position/weather: có nhịp cập nhật riêng.
- Race control: event-based.

Vì vậy khi join cần dùng tolerance thời gian, không nên join bằng timestamp tuyệt đối nếu không kiểm tra.

### 8.2 Resample 1 giây

Ưu điểm:

- Giảm kích thước dữ liệu.
- Dễ join và train model tabular hơn.
- Phù hợp cho phân tích tổng quát.

Nhược điểm:

- Mất biến động nhỏ hơn 1 giây.
- Không lý tưởng cho phân tích braking point, racing line chi tiết, hoặc dynamics rất mịn.

### 8.3 Cột `brake`

Code hiện hỗ trợ lấy `Brake` từ FastF1 nếu nguồn có cột này.
Tuy nhiên schema thực tế hiện chưa có `brake` trong 105 file parquet.
Cần kiểm tra thêm nguồn FastF1/version nếu `brake` là bắt buộc cho mô hình.

### 8.4 Duplicate sessions do nhiều session type/name

Log có một số trường hợp `Skip existing` sau khi đã save cùng event/session.
Điều này cho thấy danh sách session từ OpenF1 có thể có nhiều dòng map về cùng folder partition,
ví dụ cùng event và session type nhưng khác session name/format.
Cần chú ý nếu muốn phân biệt Sprint/Sprint Qualifying hoặc các session có tên gần giống nhau.

---

## 9. Khuyến nghị tổ chức pipeline tiếp theo

### 9.1 Giữ fetch layer sạch

Fetch layer nên chỉ làm:

- lấy dữ liệu;
- chuẩn hóa tên cột;
- chuẩn hóa timestamp;
- resample cơ bản nếu cần;
- lưu dữ liệu.

Không nên tạo feature ML phức tạp trong fetch layer.

### 9.2 Tạo feature engineering riêng

Nên có script riêng, ví dụ:

```text
src/build_telemetry_features.py
```

Feature có thể tạo sau:

- `throttle_delta`
- `relative_speed`
- rolling mean speed
- acceleration proxy
- distance-to-leader from intervals
- current race position
- tyre stint features
- weather context features

### 9.3 Tạo data quality report riêng

Nên có script kiểm tra:

- số file parquet theo năm/event/session;
- số dòng mỗi file;
- tỷ lệ missing `x/y/z`;
- tỷ lệ missing `speed/throttle/rpm`;
- session nào không có telemetry;
- schema consistency.

### 9.4 Tách cấp dữ liệu rõ ràng

Đề xuất phân tầng:

| Layer | Nội dung |
|---|---|
| `data/raw` | CSV OpenF1 nguyên bản/ít xử lý |
| `data/year=...` | FastF1 telemetry + location đã resample 1 giây |
| `data/processed` | Dataset đã join và feature engineered |
| `reports/data_quality` | Báo cáo chất lượng dữ liệu |

---

## 10. Kết luận

Pipeline hiện tại đã có hai nhóm dữ liệu quan trọng:

1. **Raw OpenF1 CSV**
   - Mạnh về metadata, race context, laps, weather, intervals, race order.

2. **FastF1 telemetry/location parquet**
   - Mạnh về tín hiệu vận hành xe và tọa độ xe trên track.
   - Đã resample về 1 giây.
   - Đã gộp car data và location trong cùng file.

Cách tổ chức hiện tại phù hợp để tiếp tục xây dựng bước `processed`/feature engineering.
Điểm quan trọng là không nên nhầm:

- `position.csv` = thứ hạng xe trong cuộc đua.
- `x/y/z` = tọa độ xe trên track.
- `intervals.csv` = gap/race context, không phải telemetry.
- `telemetry parquet` = car data + location đã resample 1 giây.
