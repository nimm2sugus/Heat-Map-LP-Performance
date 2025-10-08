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

st.title("🔋 LP-Tool Dashboard – Standortanalyse & Heatmap")

st.markdown("""
Diese App liest Excel-Dateien mit Monatswerten pro Ladepunkt und erstellt:
- Diagramme je Standort  
- Eine geografische Heatmap nach Energiemengen  
""")

# ===============================
# ⚙️ HELPER FÜR DYNAMISCHES HEADER-FINDEN (Monatsdaten)
# ===============================
def find_header_row(file, required_columns):
    raw = pd.read_excel(file, header=None)
    for i, row in raw.iterrows():
        row_values = [str(col).strip() for col in row]
        if all(req in row_values for req in required_columns):
            return i, raw
    raise ValueError(f"Keine passende Header-Zeile gefunden. Erwartete Spalten: {required_columns}")

def load_excel_dynamic(file, required_columns):
    header_row, _ = find_header_row(file, required_columns)
    df = pd.read_excel(file, header=header_row)
    return df

# ===============================
# ⚙️ CACHING
# ===============================
@st.cache_data(show_spinner=True)
def load_excel(file):
    expected_cols = ["Steuergerät ID", "EVSE-ID", "Ist in kWh", "YTD-Summe", "YTD-Schnitt (pro Monat)"]
    return load_excel_dynamic(file, expected_cols)

@st.cache_data(show_spinner=True)
def transform_monthly_data(df):
    df["Standort"] = df["Ist in kWh"].fillna(method="ffill")
    df = df.rename(columns={
        "Steuergerät ID": "Steuergerät",
        "EVSE-ID": "EVSE",
        "YTD-Summe": "YTD_Summe",
        "YTD-Schnitt (pro Monat)": "YTD_Schnitt"
    })

    month_order = [
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ]
    id_cols = ["Standort", "Steuergerät", "EVSE", "YTD_Summe", "YTD_Schnitt"]

    df_long = df.melt(
        id_vars=id_cols,
        value_vars=[c for c in month_order if c in df.columns],
        var_name="Monat",
        value_name="Energiemenge"
    )

    df_long["Energiemenge"] = pd.to_numeric(df_long["Energiemenge"], errors="coerce")
    df_long = df_long.dropna(subset=["Energiemenge"])
    df_long["Monat"] = pd.Categorical(df_long["Monat"], categories=month_order, ordered=True)
    df_long = df_long.sort_values(["Standort", "Monat"])
    return df_long

# ===============================
# ⚙️ GEO-FUNKTION (Spalten = Standorte)
# ===============================
def find_geo_header_row(file):
    raw = pd.read_excel(file, header=None)
    for i, row in raw.iterrows():
        if any(str(c).strip() for c in row):
            return i
    raise ValueError("Keine passende Header-Zeile für Geo-Datei gefunden.")

@st.cache_data(show_spinner=True)
def load_geo_excel(file):
    header_row = find_geo_header_row(file)
    df_raw = pd.read_excel(file, header=header_row)

    geo_records = []

    for col_idx in range(df_raw.shape[1]):  # jede Spalte = Standort
        standort = str(df_raw.columns[col_idx]).strip()
        if not standort or standort.lower() == "nan":
            continue

        col_data = df_raw.iloc[:, col_idx].dropna().reset_index(drop=True)

        current_steuergerät = None
        ladepunkte = []
        lon = lat = None

        for i in range(len(col_data)):
            val = str(col_data[i]).strip().replace(",", ".")
            label = val.lower()

            # Längengrad / Breitengrad
            if "längengrad" in label:
                try:
                    lon = float(re.findall(r"[-+]?\d*\.\d+|\d+", val)[0])
                except:
                    lon = None
                continue
            elif "breitengrad" in label:
                try:
                    lat = float(re.findall(r"[-+]?\d*\.\d+|\d+", val)[0])
                except:
                    lat = None
                continue

            # Steuergerät
            if re.match(r"^[A-Za-z0-9]{6,}$", val):
                current_steuergerät = val
                ladepunkte = []
                continue

            # Ladepunkte
            if re.match(r"DE\*ARK\*E\d{5}\*\d{3}", val):
                ladepunkte.append(val)

        # alle Ladepunkte abspeichern
        if current_steuergerät and ladepunkte:
            for lp in ladepunkte:
                geo_records.append({
                    "Standort": standort,
                    "Steuergerät": current_steuergerät,
                    "Ladepunkt": lp,
                    "Longitude": lon,
                    "Latitude": lat
                })

    geo_df = pd.DataFrame(geo_records).drop_duplicates()
    return geo_df

# ===============================
# 📂 SIDEBAR: Datei-Uploads
# ===============================
st.sidebar.header("📂 Datenquellen")
uploaded_file_1 = st.sidebar.file_uploader("Lade Monatsdaten (Test LP-Tool.xlsx)", type=["xlsx"], key="file1")
uploaded_file_2 = st.sidebar.file_uploader("Lade Geokoordinaten (LS-Geokoordinaten.xlsx)", type=["xlsx"], key="file2")

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
# 🗺️ HEATMAP
# ===============================
if uploaded_file_1 and uploaded_file_2:
    df_geo = load_geo_excel(uploaded_file_2)
    st.subheader("🌍 Standort-Heatmap basierend auf Energiemengen")
    st.dataframe(df_geo.head(20), use_container_width=True)

    if all(col in df_geo.columns for col in ["Standort", "Latitude", "Longitude"]):
        df_sum = df_data.groupby("Standort")["Energiemenge"].sum().reset_index()
        df_merged = pd.merge(
            df_sum,
            df_geo.groupby("Standort")[["Latitude", "Longitude"]].first().reset_index(),
            on="Standort",
            how="inner"
        )

        st.pydeck_chart(pdk.Deck(
            map_style="open-street-map",
            initial_view_state=pdk.ViewState(
                latitude=df_merged["Latitude"].mean(),
                longitude=df_merged["Longitude"].mean(),
                zoom=6,
                pitch=0,
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
