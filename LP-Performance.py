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
# ⚙️ HELPER FÜR DYNAMISCHES HEADER-FINDEN
# ===============================
def find_header_row(file, expected_columns):
    """
    Sucht die Zeile, die die erwarteten Spaltennamen enthält.
    Gibt die Zeilennummer zurück, die als Header genutzt werden soll.
    """
    raw = pd.read_excel(file, header=None)
    for i, row in raw.iterrows():
        if all(any(str(col).strip() == exp for col in row) for exp in expected_columns):
            return i, raw
    raise ValueError("Keine passende Header-Zeile gefunden.")

def load_excel_dynamic(file, expected_columns):
    """
    Liest eine Excel-Datei, sucht dynamisch die Header-Zeile und lädt die Daten ab dieser Zeile.
    """
    header_row, _ = find_header_row(file, expected_columns)
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
    """
    Wandelt die LP-Tabelle in langes Format um und sortiert Monate korrekt.
    """
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
# ⚙️ GEO-FUNKTION (dynamisch Header)
# ===============================
@st.cache_data(show_spinner=True)
def load_geo_excel(file):
    """
    Liest Geo-Excel mit dynamischem Header.
    Die Header-Zeile wird gesucht, danach werden alle Spalten als Standorte verarbeitet.
    """
    # Wir erwarten mindestens "Label" + einen Standort
    expected_columns = ["Label"]
    header_row, raw = find_header_row(file, expected_columns)
    df_raw = pd.read_excel(file, header=header_row)

    geo_records = []

    for col_idx in range(1, df_raw.shape[1]):
        standort = str(df_raw.columns[col_idx]).strip()
        if not standort or standort.lower() == "nan":
            continue

        col_data = df_raw.iloc[:, [0, col_idx]].dropna(subset=[df_raw.columns[col_idx]])
        col_data.columns = ["Label", "Value"]
        col_data["Label"] = col_data["Label"].astype(str).str.strip()
        col_data["Value"] = col_data["Value"].astype(str).str.strip()

        current_steuergerät = None
        ladepunkte = []
        lon = lat = None

        for _, row in col_data.iterrows():
            label = row["Label"].lower()
            val = row["Value"]

            if re.match(r"^[A-Za-z0-9]{6,}$", val) and "grad" not in label:
                if current_steuergerät and ladepunkte:
                    for lp in ladepunkte:
                        geo_records.append({
                            "Standort": standort,
                            "Steuergerät": current_steuergerät,
                            "Ladepunkt": lp,
                            "Longitude": lon,
                            "Latitude": lat
                        })
                current_steuergerät = val
                ladepunkte = []
                lon = lat = None

            elif re.match(r"DE\*ARK\*E\d{5}\*\d{3}", val):
                ladepunkte.append(val)

            elif "längengrad" in label:
                try:
                    lon = float(val.replace(",", "."))
                except:
                    lon = None
            elif "breitengrad" in label:
                try:
                    lat = float(val.replace(",", "."))
                except:
                    lat = None

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
    df_geo = load_geo_excel(uploaded_file_2)

    st.subheader("🌍 Standort-Heatmap basierend auf Energiemengen")
    st.dataframe(df_geo.head(), use_container_width=True)

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
