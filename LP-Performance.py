import streamlit as st
import pandas as pd
import pydeck as pdk
import re

# ===============================
# 🧭 APP-KONFIGURATION
# ===============================
st.set_page_config(
    page_title="LP-Tool Dashboard",
    layout="wide",
    page_icon="🔋",
    initial_sidebar_state="expanded"
)

st.title("🔋 LP-Tool Dashboard – Standortanalyse & Heatmap")

st.markdown("""
Diese Anwendung analysiert **Ladepunkt-Monatswerte** aus hierarchisch aufgebauten Excel-Dateien  
und stellt sie tabellarisch sowie geographisch dar.
""")

# ===============================
# ⚙️ FUNKTIONEN MIT CACHE
# ===============================
@st.cache_data(show_spinner=True)
def load_excel(file):
    """Lädt Excel-Datei (erste Tabelle)"""
    return pd.read_excel(file, header=None)

@st.cache_data(show_spinner=True)
def parse_hierarchical_excel(df):
    """
    Wandelt eine hierarchisch strukturierte Excel-Tabelle in eine flache Tabelle um.
    Erwartete Struktur:
    Standort-Zeilen, gefolgt von Steuergeräten und Ladepunkten mit Monatswerten.
    """
    data = []
    current_standort = None
    current_steuergerät = None

    for idx, row in df.iterrows():
        values = row.dropna().tolist()
        if not values:
            continue

        # Standort-Zeile erkennen (Beispiel: "Standort: Wien")
        if isinstance(values[0], str) and re.search(r"Standort", values[0], re.IGNORECASE):
            current_standort = values[0].split(":")[-1].strip() if ":" in values[0] else values[0].strip()
            continue

        # Steuergerät-Zeile (z. B. "Steuergerät: SG_01")
        if isinstance(values[0], str) and re.search(r"Steuergerät", values[0], re.IGNORECASE):
            current_steuergerät = values[0].split(":")[-1].strip() if ":" in values[0] else values[0].strip()
            continue

        # Datenzeilen mit Monatswerten
        # Beispiel: [Ladepunkt 1, 1200, 1300, 1100, ...]
        ladepunkt = values[0]
        months = [f"Monat_{i+1}" for i in range(len(values[1:]))]
        energiewerte = values[1:]

        for monat, wert in zip(months, energiewerte):
            data.append({
                "Standort": current_standort,
                "Steuergerät": current_steuergerät,
                "Ladepunkt": ladepunkt,
                "Monat": monat,
                "Energiemenge": wert
            })

    df_clean = pd.DataFrame(data)
    return df_clean

# ===============================
# 📂 SIDEBAR: Datei-Upload
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
    raw_df = load_excel(uploaded_file_1)
    df_data = parse_hierarchical_excel(raw_df)

    st.subheader("📊 Bereinigte Monatswerte je Standort")
    st.dataframe(df_data.head(20), use_container_width=True)

    # Standortauswahl
    standorte = sorted(df_data["Standort"].dropna().unique())
    selected_standort = st.selectbox("Standort auswählen:", standorte)

    df_filtered = df_data[df_data["Standort"] == selected_standort]

    st.markdown(f"**Anzahl Ladepunkte:** {df_filtered['Ladepunkt'].nunique()} | **Steuergeräte:** {df_filtered['Steuergerät'].nunique()}")

    # Chart der Summen je Monat
    df_chart = df_filtered.groupby("Monat")["Energiemenge"].sum()
    st.bar_chart(df_chart, use_container_width=True)

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
