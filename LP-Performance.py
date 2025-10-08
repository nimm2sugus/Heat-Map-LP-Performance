import streamlit as st
import pandas as pd
import pydeck as pdk

st.set_page_config(page_title="LP-Tool Dashboard", layout="wide")

st.title("🔋 LP-Tool Auswertung & Standort-Heatmap")

st.sidebar.header("📂 Datenquellen")

# === Datei 1: Test LP-Tool ===
uploaded_file_1 = st.sidebar.file_uploader("Lade Monatsdaten (Test LP-Tool.xlsx)", type=["xlsx"])
uploaded_file_2 = st.sidebar.file_uploader("Lade Geokoordinaten (z. B. 2025 06 25 - LS-Geokoordinaten.xlsx)", type=["xlsx"])

if uploaded_file_1:
    df_data = pd.read_excel(uploaded_file_1)
    st.subheader("📊 Monatswerte je Standort")

    # Vermutete Spaltennamen anpassen:
    # z. B.: "Standort", "Monat", "Energiemenge (kWh)"
    # → falls anders, hier anpassen
    st.write("Vorschau der Daten:")
    st.dataframe(df_data.head())

    if "Standort" in df_data.columns:
        standorte = sorted(df_data["Standort"].unique())
        selected_standort = st.selectbox("Standort auswählen:", standorte)

        df_filtered = df_data[df_data["Standort"] == selected_standort]

        if "Monat" in df_filtered.columns and "Energiemenge" in df_filtered.columns:
            st.line_chart(df_filtered.set_index("Monat")["Energiemenge"])
        else:
            st.warning("Spalten 'Monat' und 'Energiemenge' nicht gefunden – bitte Struktur prüfen.")
    else:
        st.error("Spalte 'Standort' nicht gefunden – bitte Excel-Struktur prüfen.")

    # === Datei 2: Geokoordinaten für Heatmap ===
    if uploaded_file_2:
        df_geo = pd.read_excel(uploaded_file_2)
        st.subheader("🌍 Standort-Heatmap")

        st.write("Vorschau der Geodaten:")
        st.dataframe(df_geo.head())

        # Erwartete Spaltennamen prüfen und ggf. anpassen
        # z. B.: "Standort", "Latitude", "Longitude"
        if all(col in df_geo.columns for col in ["Standort", "Latitude", "Longitude"]):
            # Daten zusammenführen
            merged = pd.merge(df_data, df_geo, on="Standort", how="inner")

            if "Energiemenge" not in merged.columns:
                st.warning("Spalte 'Energiemenge' nicht gefunden – bitte prüfen.")
            else:
                st.map(merged[["Latitude", "Longitude"]])

                st.pydeck_chart(pdk.Deck(
                    map_style="mapbox://styles/mapbox/light-v9",
                    initial_view_state=pdk.ViewState(
                        latitude=merged["Latitude"].mean(),
                        longitude=merged["Longitude"].mean(),
                        zoom=6,
                        pitch=40,
                    ),
                    layers=[
                        pdk.Layer(
                            "HeatmapLayer",
                            data=merged,
                            get_position='[Longitude, Latitude]',
                            get_weight="Energiemenge",
                            radiusPixels=60,
                            aggregation=pdk.types.String("SUM")
                        )
                    ],
                ))
        else:
            st.error("Die zweite Datei muss Spalten 'Standort', 'Latitude' und 'Longitude' enthalten.")
else:
    st.info("Bitte zuerst die Datei **Test LP-Tool.xlsx** hochladen.")
