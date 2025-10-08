import streamlit as st
import pandas as pd
import pydeck as pdk
import re

# ===============================
# 🧭 APP KONFIGURATION
# ===============================
st.set_page_config(
    page_title="LP-Tool Dashboard",
    layout="wide",
    page_icon="🔋",
    initial_sidebar_state="expanded"
)

# ===============================
# 🔑 TOKEN-KONFIGURATION (Optional)
# ===============================
MAPBOX_API_KEY = "pk.eyJ1IjoibmltbTJzdWd1cyIsImEiOiJjbWdoeGMwbzEwMWN6MmpxeHNuOWtwb2N5In0.Y0VtWicxzoEvUcxdsLh9sQ"

st.title("🔋 LP-Tool Dashboard – Standortanalyse & Heatmap")
st.markdown(
    "Diese App liest Excel-Dateien mit Monatswerten pro Ladepunkt und erstellt Diagramme und eine geografische Heatmap.")

if MAPBOX_API_KEY == "DEIN_KEY_HIER" or MAPBOX_API_KEY == "":
    st.info(
        "Hinweis: Für die beste Kartendarstellung können Sie einen kostenlosen Mapbox API Key im Skript eintragen. Aktuell wird OpenStreetMap verwendet.")


# ===============================
# ⚙️ DATENLADE-FUNKTIONEN
# ===============================
@st.cache_data(show_spinner=True)
def load_excel(file):
    expected_cols = ["Steuergerät ID", "EVSE-ID", "Ist in kWh", "YTD-Summe", "YTD-Schnitt (pro Monat)"]
    raw = pd.read_excel(file, header=None)
    header_row_index = raw[raw.apply(lambda row: all(col in row.values for col in expected_cols), axis=1)].index
    if not header_row_index.empty:
        header_row = header_row_index[0]
        df = pd.read_excel(file, header=header_row)
        return df
    else:
        st.error("Der erwartete Header wurde in der ersten Excel-Datei nicht gefunden.")
        return pd.DataFrame()


@st.cache_data(show_spinner=True)
def transform_monthly_data(df):
    df["Standort"] = df["Ist in kWh"].fillna(method="ffill")
    df = df.rename(columns={"Steuergerät ID": "Steuergerät", "EVSE-ID": "EVSE", "YTD-Summe": "YTD_Summe",
                            "YTD-Schnitt (pro Monat)": "YTD_Schnitt"})
    df_clean = df.dropna(subset=['EVSE', 'Steuergerät']).copy()
    month_order = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
                   "November", "Dezember"]
    id_cols = ["Standort", "Steuergerät", "EVSE", "YTD_Summe", "YTD_Schnitt"]
    value_vars_exist = [c for c in month_order if c in df_clean.columns]
    df_long = df_clean.melt(id_vars=id_cols, value_vars=value_vars_exist, var_name="Monat", value_name="Energiemenge")
    df_long["Energiemenge"] = pd.to_numeric(df_long["Energiemenge"], errors="coerce")
    df_long = df_long.dropna(subset=["Energiemenge", "Standort"])
    df_long["Monat"] = pd.Categorical(df_long["Monat"], categories=month_order, ordered=True)
    df_long = df_long.sort_values(["Standort", "Monat"])
    return df_long


@st.cache_data(show_spinner=True)
def load_geo_excel_final(file):
    raw = pd.read_excel(file, header=None)
    header_row_index = -1
    for i in range(min(10, len(raw))):
        if any(pd.notna(val) for val in raw.iloc[i, 1:].values):
            header_row_index = i
            break
    if header_row_index == -1: return pd.DataFrame()
    standort_namen = raw.iloc[header_row_index, 1:].tolist()
    data_df = raw.iloc[header_row_index + 1:].reset_index(drop=True)
    labels = data_df.iloc[:, 0].astype(str).str.strip()
    geo_records = []
    for col_idx, standort_name in enumerate(standort_namen, start=1):
        if pd.isna(standort_name) or col_idx >= len(data_df.columns): continue
        col_values = data_df.iloc[:, col_idx]
        current_steuergerät, ladepunkte, laengengrad, breitengrad = None, [], None, None
        for i, val in enumerate(col_values):
            if pd.isna(val) or i >= len(labels): continue
            val_str, label = str(val).strip(), labels[i]
            is_steuergeraet_row = 'steuergerät' in label.lower()
            is_evse_id_row = re.match(r"DE\*ARK\*E\d{5}\*\d{3}", val_str, re.IGNORECASE)
            if is_steuergeraet_row and val_str:
                if all((current_steuergerät, ladepunkte, laengengrad is not None, breitengrad is not None)):
                    for lp in ladepunkte: geo_records.append(
                        {"Standort": str(standort_name), "Steuergerät": current_steuergerät, "EVSE-ID": lp,
                         "Längengrad": laengengrad, "Breitengrad": breitengrad})
                current_steuergerät, ladepunkte, laengengrad, breitengrad = val_str, [], None, None
                continue
            if is_evse_id_row:
                ladepunkte.append(val_str)
            elif label.lower() == "längengrad":
                try:
                    laengengrad = float(
                        re.findall(r"[-+]?\d*\.\d+|\d+", val_str.replace(",", ".").replace("°", "").strip())[0])
                except (ValueError, IndexError):
                    laengengrad = None
            elif label.lower() == "breitengrad":
                try:
                    breitengrad = float(
                        re.findall(r"[-+]?\d*\.\d+|\d+", val_str.replace(",", ".").replace("°", "").strip())[0])
                except (ValueError, IndexError):
                    breitengrad = None
        if all((current_steuergerät, ladepunkte, laengengrad is not None, breitengrad is not None)):
            for lp in ladepunkte: geo_records.append(
                {"Standort": str(standort_name), "Steuergerät": current_steuergerät, "EVSE-ID": lp,
                 "Längengrad": laengengrad, "Breitengrad": breitengrad})
    geo_df = pd.DataFrame(geo_records)
    return geo_df if geo_df.empty else geo_df.dropna(subset=["Breitengrad", "Längengrad"])


# ===============================
# 📂 SIDEBAR: Datei-Uploads
# ===============================
st.sidebar.header("📂 Datenquellen")
uploaded_file_1 = st.sidebar.file_uploader("Lade Monatsdaten (Test LP-Tool.xlsx)", type=["xlsx"], key="file1")
uploaded_file_2 = st.sidebar.file_uploader("Lade Geokoordinaten (LS-Geokoordinaten.xlsx)", type=["xlsx"], key="file2")

# ===============================
# 📈 GESAMT-DATENANALYSE
# ===============================
df_data, df_geo = None, None
if uploaded_file_1 and uploaded_file_2:
    df_data = transform_monthly_data(load_excel(uploaded_file_1))
    df_geo = load_geo_excel_final(uploaded_file_2)
else:
    st.info("Bitte laden Sie beide Excel-Dateien hoch, um die Analyse zu starten.")

if df_data is not None and not df_data.empty:
    st.header("📊 Monatliche Gesamtenergiemenge (Alle Standorte)")
    df_chart_total = df_data.groupby("Monat")["Energiemenge"].sum().reset_index()
    st.bar_chart(df_chart_total, x="Monat", y="Energiemenge", use_container_width=True)

# ===============================
# 🗺️ GESAMT-HEATMAP
# ===============================
if df_data is not None and df_geo is not None and not df_geo.empty:
    st.header("🌍 Interaktive Heatmap (Alle Standorte)")

    col1, col2 = st.columns([3, 1])
    with col1:
        time_options = ["Gesamtzeit"] + df_data['Monat'].unique().tolist()
        selected_timespan = st.selectbox("Zeitraum für Heatmap auswählen:", time_options)

    with col2:
        swap_coords = st.checkbox("Längen-/Breitengrad tauschen",
                                  help="Aktivieren, falls die Punkte am falschen Ort auf der Weltkarte erscheinen.")

    if selected_timespan == "Gesamtzeit":
        df_sum = df_data.groupby(["Standort", "Steuergerät"])["Energiemenge"].sum().reset_index()
    else:
        df_monthly = df_data[df_data["Monat"] == selected_timespan]
        df_sum = df_monthly.groupby(["Standort", "Steuergerät"])["Energiemenge"].sum().reset_index()

    df_geo_unique = df_geo.groupby(["Standort", "Steuergerät"])[["Breitengrad", "Längengrad"]].first().reset_index()
    df_merged = pd.merge(df_sum, df_geo_unique, on=["Standort", "Steuergerät"], how="inner")

    if swap_coords:
        df_merged = df_merged.rename(columns={"Längengrad": "temp", "Breitengrad": "Längengrad"})
        df_merged = df_merged.rename(columns={"temp": "Breitengrad"})
        st.info("Längengrad und Breitengrad wurden für die Darstellung vertauscht.")

    if not df_merged.empty:
        use_mapbox = MAPBOX_API_KEY != "DEIN_KEY_HIER" and MAPBOX_API_KEY != ""

        st.pydeck_chart(pdk.Deck(
            map_provider="mapbox" if use_mapbox else None,
            map_style=pdk.map_styles.SATELLITE if use_mapbox else 'open-street-map',
            api_keys={'mapbox': MAPBOX_API_KEY} if use_mapbox else None,
            initial_view_state=pdk.ViewState(latitude=df_merged["Breitengrad"].mean(),
                                             longitude=df_merged["Längengrad"].mean(), zoom=5, pitch=45),
            layers=[
                pdk.Layer("HeatmapLayer", data=df_merged, get_position='[Längengrad, Breitengrad]',
                          get_weight="Energiemenge", radiusPixels=80),
                # --- KORREKTUR: Visuelle Präzision erhöht ---
                pdk.Layer(
                    "ScatterplotLayer",
                    data=df_merged,
                    get_position='[Längengrad, Breitengrad]',
                    get_radius=50,  # Radius auf 50 Meter reduziert für einen präzisen Punkt
                    get_fill_color='[255, 140, 0, 150]',  # Leuchtendes Orange
                    get_line_color='[255, 255, 255]',  # Weißer Rand
                    line_width_min_pixels=1,
                    pickable=True
                )
            ],
            # --- KORREKTUR: Tooltip um exakte Koordinaten erweitert ---
            tooltip={
                "html": "<b>Standort:</b> {Standort}<br/><b>Steuergerät:</b> {Steuergerät}<br/><b>Energiemenge:</b> {Energiemenge} kWh<br/><b>Koordinaten:</b> [{Längengrad}, {Breitengrad}]",
                "style": {"backgroundColor": "steelblue", "color": "white"}}
        ))
    else:
        st.warning(f"Für die aktuelle Auswahl wurden keine darstellbaren Daten gefunden.")
