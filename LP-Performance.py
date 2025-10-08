import streamlit as st
import pandas as pd
import pydeck as pdk

# ===============================
# 🧭 APP KONFIGURATION
# ===============================
st.set_page_config(
    page_title="LP-Tool Dashboard",
    layout="wide",
    page_icon="🔋",
    initial_sidebar_state="expanded"
)

st.title("🔋 LP-Tool Dashboard – Standortanalyse & Heatmap")

st.markdown("""
Diese App liest Excel-Dateien mit Monatswerten pro Ladepunkt und erstellt:
- Diagramme je Standort  
- Eine geografische Heatmap nach Energiemengen  
""")

# ===============================
# ⚙️ CACHING
# ===============================
@st.cache_data(show_spinner=True)
def load_excel(file):
    return pd.read_excel(file, header=1)  # Zeile 2 ist Kopfzeile

@st.cache_data(show_spinner=True)
def transform_monthly_data(df):
    """
    Wandelt die LP-Tabelle in ein langes Format um.
    """
    # Standortnamen nach unten füllen
    df["Standort"] = df["Ist in kWh"].fillna(method="ffill")

    # Spalten standardisieren
    df = df.rename(columns={
        "Steuergerät ID": "Steuergerät",
        "EVSE-ID": "EVSE",
        "YTD-Summe": "YTD_Summe",
        "YTD-Schnitt (pro Monat)": "YTD_Schnitt"
    })

    # Relevante Spalten isolieren
    month_cols = [
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ]
    id_cols = ["Standort", "Steuergerät", "EVSE", "YTD_Summe", "YTD_Schnitt"]

    df_long = df.melt(
        id_vars=id_cols,
        value_vars=[c for c in month_cols if c in df.columns],
        var_name="Monat",
        value_name="Energiemenge"
    )

    # Numerische Umwandlung
    df_long["Energiemenge"] = pd.to_numeric(df_long["Energiemenge"], errors="coerce")
    df_long = df_long.dropna(subset=["Energiemenge"])

    return df_long

# ===============================
# 📂 SIDEBAR: Datei-Uploads
# ===============================
st.sidebar.header("📂 Datenquellen")

uploaded_file_1 = st.sidebar.file_uploader(
    "Lade Monatsdaten (Test LP-Tool.xlsx)",
    type=["xlsx"],
    key="file1"
)

uploaded_file_2 = st.sidebar.file_uploader(
    "Lade Geokoordinaten (z. B. 2025 06 25 - LS-Geokoordinaten.xlsx)",
    type=["xlsx"],
    key="file2"
)

# ===============================
# 📈 ANZEIGE DER MONATSDATEN
# ===============================
if uploaded_file_1:
    df_raw = load_excel(uploaded_file_1)
    df_data = transform_monthly_data(df_raw)

    st.subheader("📊 Bereinigte Monatswerte je Standort")
    st.dataframe(df_data.head(20), use_container_width=True)

    standorte = sorted(df_data["Standort"].dropna().unique())
    selected_standort = st.selectbox("Standort auswählen:", standorte)

    df_filtered = df_data[df_data["Standort"] == selected_standort]

    st.markdown(f"**Anzahl Ladepunkte:** {df_filtered['EVSE'].nunique()} | **Steuergeräte:** {df_filtered['Steuergerät'].nunique()}")

    df_chart = df_filtered.groupby("Monat")["Energiemenge"].sum().reset_index()
    st.bar_chart(df_chart, x="Monat", y="Energiemenge", use_container_width=True)

else:
    st.info("Bitte zuerst die Datei **Test LP-Tool.xlsx** hochladen.")

# ===============================
# 🗺️ HEATMAP (wenn Geo-Datei geladen)
# ===============================
if uploaded_file_1 and uploaded_file_2:
    df_geo = pd.read_excel(uploaded_file_2)

    st.subheader("🌍 Standort-Heatmap basierend auf Energiemengen")
    st.dataframe(df_geo.head(), use_container_width=True)

    if all(col in df_geo.columns for col in ["Standort", "Latitude", "Longitude"]):
        df_sum = df_data.groupby("Standort")["Energiemenge"].sum().reset_index()
        df_merged = pd.merge(df_sum, df_geo, on="Standort", how="inner")

        st.pydeck_chart(pdk.Deck(
            map_style="mapbox://styles/mapbox/light-v9",
            initial_view_state=pdk.ViewState(
                latitude=df_merged["Latitude"].mean(),
                longitude=df_merged["Longitude"].mean(),
                zoom=6,
                pitch=45,
            ),
            layers=[
                pdk.Layer(
                    "HeatmapLayer",
                    data=df_merged,
                    get_position='[Longitude, Latitude]',
                    get_weight="Energiemenge",
                    radiusPixels=60,
                    aggregation=pdk.types.String("SUM")
                ),
                pdk.Layer(
                    "ScatterplotLayer",
                    data=df_merged,
                    get_position='[Longitude, Latitude]',
                    get_radius=3000,
                    get_fill_color='[255, 0, 0, 160]',
                )
            ],
        ))
    else:
        st.error("Die Geo-Datei muss Spalten **'Standort'**, **'Latitude'** und **'Longitude'** enthalten.")
