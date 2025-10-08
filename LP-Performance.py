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
Diese App ermöglicht die Auswertung von **Ladepunkten** aus Excel-Dateien:
- **Monatswerte je Standort** (mit Filter)
- **Geografische Heatmap** basierend auf Energiemengen
""")

# ===============================
# ⚙️ FUNKTIONEN MIT CACHE
# ===============================

@st.cache_data(show_spinner=True)
def load_excel(file):
    """Excel-Datei einlesen und zurückgeben."""
    try:
        return pd.read_excel(file)
    except Exception as e:
        st.error(f"Fehler beim Laden der Datei: {e}")
        return None

# ===============================
# 📂 SIDEBAR: Datei-Upload
# ===============================
st.sidebar.header("📂 Datenquellen")

uploaded_file_1 = st.sidebar.file_uploader(
    "Lade Monatsdaten (z. B. Test LP-Tool.xlsx)",
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
    df_data = load_excel(uploaded_file_1)

    if df_data is not None and not df_data.empty:
        st.subheader("📊 Monatswerte je Standort")
        st.dataframe(df_data.head(), use_container_width=True)

        # Erforderliche Spalten prüfen
        if all(col in df_data.columns for col in ["Standort", "Monat", "Energiemenge"]):
            standorte = sorted(df_data["Standort"].unique())
            selected_standort = st.selectbox("Standort auswählen:", standorte, key="standort")

            df_filtered = df_data[df_data["Standort"] == selected_standort]

            # Chart (Monatswerte)
            st.line_chart(
                df_filtered.set_index("Monat")["Energiemenge"],
                use_container_width=True
            )
        else:
            st.warning("Bitte sicherstellen, dass die Spalten **'Standort'**, **'Monat'** und **'Energiemenge'** vorhanden sind.")
    else:
        st.error("Die geladene Datei ist leer oder fehlerhaft.")
else:
    st.info("Bitte zuerst die Datei **Test LP-Tool.xlsx** hochladen.")

# ===============================
# 🗺️ HEATMAP MIT GEO-DATEN
# ===============================
if uploaded_file_1 and uploaded_file_2:
    df_geo = load_excel(uploaded_file_2)

    if df_geo is not None and not df_geo.empty:
        st.subheader("🌍 Standort-Heatmap basierend auf Energiemengen")
        st.dataframe(df_geo.head(), use_container_width=True)

        # Erwartete Spalten prüfen
        if all(col in df_geo.columns for col in ["Standort", "Latitude", "Longitude"]):
            # Zusammenführen
            df_merged = pd.merge(df_data, df_geo, on="Standort", how="inner")

            # Sicherstellen, dass nur gültige Koordinaten verwendet werden
            df_merged = df_merged.dropna(subset=["Latitude", "Longitude"])

            if not df_merged.empty and "Energiemenge" in df_merged.columns:
                # Mittlere Position für Kartenzentrum
                lat_center = df_merged["Latitude"].mean()
                lon_center = df_merged["Longitude"].mean()

                st.pydeck_chart(pdk.Deck(
                    map_style="mapbox://styles/mapbox/light-v9",
                    initial_view_state=pdk.ViewState(
                        latitude=lat_center,
                        longitude=lon_center,
                        zoom=6,
                        pitch=40,
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
                            get_radius=2000,
                            get_fill_color='[255, 0, 0, 160]',
                        )
                    ],
                ))

            else:
                st.warning("Keine gültigen Energiemengen- oder Standortdaten gefunden.")
        else:
            st.error("Die zweite Datei muss Spalten **'Standort'**, **'Latitude'** und **'Longitude'** enthalten.")
    else:
        st.error("Fehler beim Laden der Geodaten.")
