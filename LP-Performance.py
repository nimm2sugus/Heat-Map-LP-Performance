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
# ⚙️ ROBUSTE GEO-FUNKTION
# ===============================
@st.cache_data(show_spinner=True)
def load_geo_excel(file):
    raw = pd.read_excel(file, header=None)
    labels = raw.iloc[:, 0].astype(str).str.strip()  # Spalte A = Labels
    standorte = raw.columns[1:]  # Spalten B…Z = Standorte

    geo_records = []

    for col_idx, standort in enumerate(standorte, start=1):
        col_values = raw.iloc[:, col_idx]

        current_steuergerät = None
        laengengrad = None
        breitengrad = None
        ladepunkte = []

        for i, val in enumerate(col_values):
            val = str(val).strip().replace(",", ".").replace("°", "")
            label = labels[i]

            if label == "Steuergerät":
                current_steuergerät = val
                ladepunkte = []
                continue

            if label == "Ladepunkt" and re.match(r"DE\*ARK\*E\d{5}\*\d{3}", val):
                ladepunkte.append(val)
                continue

            if label == "Längengrad":
                try:
                    laengengrad = float(re.findall(r"[-+]?\d*\.\d+|\d+", val)[0])
                except:
                    laengengrad = None
                continue

            if label == "Breitengrad":
                try:
                    breitengrad = float(re.findall(r"[-+]?\d*\.\d+|\d+", val)[0])
                except:
                    breitengrad = None
                continue

        # Alle Ladepunkte abspeichern
        if current_steuergerät and ladepunkte:
            for lp in ladepunkte:
                geo_records.append({
                    "Standort": str(standort),
                    "Steuergerät": current_steuergerät,
                    "Ladepunkt": lp,
                    "Längengrad": laengengrad,
                    "Breitengrad": breitengrad
                })

    geo_df = pd.DataFrame(geo_records)

    # Sicherstellen, dass die Spalten existieren
    for col in ["Breitengrad", "Längengrad"]:
        if col not in geo_df.columns:
            geo_df[col] = None

    geo_df = geo_df.dropna(subset=["Breitengrad", "Längengrad"])
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

    if not df_geo.empty:
        df_sum = df_data.groupby("Standort")["Energiemenge"].sum().reset_index()
        df_merged = pd.merge(
            df_sum,
            df_geo.groupby("Standort")[["Breitengrad", "Längengrad"]].first().reset_index(),
            on="Standort",
            how="inner"
        )

        if not df_merged.empty:
            st.pydeck_chart(pdk.Deck(
                map_style="open-street-map",
                initial_view_state=pdk.ViewState(
                    latitude=df_merged["Breitengrad"].mean(),
                    longitude=df_merged["Längengrad"].mean(),
                    zoom=6,
                    pitch=0,
                ),
                layers=[
                    pdk.Layer(
                        "HeatmapLayer",
                        data=df_merged,
                        get_position='[Längengrad, Breitengrad]',
                        get_weight="Energiemenge",
                        radiusPixels=60,
                        aggregation=pdk.types.String("SUM")
                    ),
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=df_merged,
                        get_position='[Längengrad, Breitengrad]',
                        get_radius=3000,
                        get_fill_color='[255, 0, 0, 160]',
                    )
                ],
            ))
        else:
            st.warning("Keine übereinstimmenden Standorte für Heatmap gefunden.")
    else:
        st.warning("Geo-Datei enthält keine gültigen Koordinaten für die Heatmap.")
