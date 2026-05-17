import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# Cấu hình trang
st.set_page_config(
    page_title="F1 WinRate Predictor Dashboard",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS cho phong cách Premium
st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
    }
    .stMetric {
        background-color: #161b22;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #30363d;
    }
    h1, h2, h3 {
        color: #ff1e00 !important; /* F1 Red */
        font-family: 'Arial Black', sans-serif;
    }
    .stDataFrame {
        border: 1px solid #30363d;
    }
    </style>
    """, unsafe_allow_html=True)

# Đường dẫn dữ liệu
DATA_DIR = Path("data/processed")
BASE_DATA_PATH = DATA_DIR / "driver_session_base.csv"

def load_data():
    if not BASE_DATA_PATH.exists():
        return None
    df = pd.read_csv(BASE_DATA_PATH)
    return df

def main():
    st.title("🏎️ F1 WIN-RATE PREDICTOR")
    st.subheader("Data Explorer & Insights Dashboard")
    
    df = load_data()
    
    if df is None:
        st.warning("⚠️ Không tìm thấy dữ liệu đã xử lý. Vui lòng chạy Pipeline trước để tạo dữ liệu!")
        st.info("Chạy lệnh: `python run_e2e_pipeline.py` để bắt đầu.")
        return

    # Sidebar Filters
    st.sidebar.header("Bộ lọc dữ liệu")
    years = sorted(df['year'].unique(), reverse=True)
    selected_year = st.sidebar.selectbox("Chọn năm", years)
    
    filtered_df = df[df['year'] == selected_year]
    
    sessions = sorted(filtered_df['session_name'].unique())
    selected_session = st.sidebar.selectbox("Chọn chặng đua", ["Tất cả"] + sessions)
    
    if selected_session != "Tất cả":
        filtered_df = filtered_df[filtered_df['session_name'] == selected_session]

    # Metrics Row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Tổng số chặng", len(filtered_df['session_key'].unique()))
    with col2:
        st.metric("Số tay đua", len(filtered_df['driver_number'].unique()))
    with col3:
        avg_temp = filtered_df['track_temperature_mean'].mean() if 'track_temperature_mean' in filtered_df.columns else 0
        st.metric("Nhiệt độ sân TB", f"{avg_temp:.1f}°C")
    with col4:
        rain_sessions = filtered_df[filtered_df['rainfall_max'] > 0]['session_key'].nunique() if 'rainfall_max' in filtered_df.columns else 0
        st.metric("Số chặng mưa", rain_sessions)

    st.divider()

    # Layout chính: 2 cột
    left_col, right_col = st.columns([2, 1])

    with left_col:
        st.subheader("📊 Kết quả chặng đua & Thống kê")
        # Bảng dữ liệu chính
        display_cols = ['session_name', 'full_name', 'team_name', 'grid_position', 'final_position', 'status']
        st.dataframe(filtered_df[[c for c in display_cols if c in filtered_df.columns]], use_container_width=True)
        
        # Biểu đồ phân phối vị trí Grid vs Final
        if 'grid_position' in filtered_df.columns and 'final_position' in filtered_df.columns:
            st.subheader("📈 So sánh Vị trí Xuất phát vs Kết thúc")
            fig = px.scatter(
                filtered_df, 
                x="grid_position", 
                y="final_position", 
                color="team_name",
                hover_name="full_name",
                trendline="ols",
                title=f"Tương quan Grid vs Result - {selected_year}",
                template="plotly_dark",
                color_discrete_sequence=px.colors.qualitative.Safe
            )
            st.plotly_chart(fig, use_container_width=True)

    with right_col:
        st.subheader("🏆 Phân tích Đội đua")
        # Thống kê số lần thắng theo Team
        if 'target_win' in filtered_df.columns:
            wins_by_team = filtered_df.groupby('team_name')['target_win'].sum().sort_values(ascending=False).reset_index()
            wins_by_team = wins_by_team[wins_by_team['target_win'] > 0]
            
            fig_wins = px.pie(
                wins_by_team, 
                values='target_win', 
                names='team_name', 
                title="Tỉ lệ chiến thắng theo Đội",
                hole=0.4,
                template="plotly_dark"
            )
            st.plotly_chart(fig_wins, use_container_width=True)

        st.subheader("⏱️ Hiệu suất Vòng đua")
        # Histogram thời gian vòng đua trung bình
        if 'avg_lap_duration' in filtered_df.columns:
            fig_laps = px.histogram(
                filtered_df, 
                x="avg_lap_duration", 
                nbins=20,
                title="Phân phối thời gian vòng đua TB",
                template="plotly_dark",
                color_discrete_sequence=['#ff1e00']
            )
            st.plotly_chart(fig_laps, use_container_width=True)

    # Footer
    st.markdown("---")
    st.markdown(f"**F1 WinRate Predictor System** | Dự án DS108 | Cập nhật lúc: {pd.Timestamp.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    main()
