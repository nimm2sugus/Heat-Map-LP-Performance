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
# ⚙️ CACHING FÜR MONATSDATEN
# ===============================
@st.cache_data(show_spinner=True)
def load_excel(file):
    expected_cols = ["Steuergerät ID", "EVSE-ID", "Ist in kWh", "YTD-Summe", "YTD-Schnitt (pro Monat)"]
    raw = pd.read_excel(file, header=None)
    # Header dynamisch suchen
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
# ⚙️ KORRIGIERTE GEO-FUNKTION (FINDE ERSTE ZEILE MIT DATEN AB SPALTE B)
# ===============================
@st.cache_data(show_spinner=True)
def load_geo_excel(file):
    """
    Liest eine Excel-Datei mit Geodaten und erkennt dynamisch die Header-Zeile.
    Die Header-Zeile wird als die ERSTE Zeile definiert, die ab Spalte B einen Wert enthält.
    """
    raw = pd.read_excel(file, header=None)

    # --- Dynamische Header-Erkennung ---
    header_row_index = -1
    # Durchsuche die ersten 10 Zeilen der Datei.
    for i in range(min(10, len(raw))):
        row_values = raw.iloc[i].values
        # NEUES, VEREINFACHTES Kriterium:
        # Ist dies die erste Zeile, die ab der zweiten Spalte (Index 1) Daten enthält?
        if any(pd.notna(val) for val in row_values[1:]):
            header_row_index = i  # Zeilennummer speichern
            break  # Suche beenden, da die erste Zeile gefunden wurde

    # Wenn nach der Suche keine passende Zeile gefunden wurde, zeige eine Fehlermeldung.
    if header_row_index == -1:
        st.error("Konnte keine Daten ab Spalte B in den ersten 10 Zeilen der Geo-Datei finden.")
        return pd.DataFrame()

    # --- Datenextraktion basierend auf der gefundenen Header-Zeile ---
    standort_namen = raw.iloc[header_row_index, 1:].tolist()
    # Die eigentlichen Daten beginnen in der Zeile direkt nach dem Header.
    data_df = raw.iloc[header_row_index + 1:].reset_index(drop=True)
    labels = data_df.iloc[:, 0].astype(str).str.strip()

    geo_records = []

    # Iteration über jede Standort-Spalte.
    for col_idx, standort_name in enumerate(standort_namen, start=1):
        if pd.isna(standort_name) or col_idx >= len(data_df.columns):
            continue

        col_values = data_df.iloc[:, col_idx]

        current_steuergerät = None
        laengengrad = None
        breitengrad = None
        ladepunkte = []

        # Iteriere durch die Zeilen der aktuellen Standort-Spalte.
        for i, val in enumerate(col_values):
            if pd.isna(val) or i >= len(labels):
                continue

            val_str = str(val).strip()
            label = labels[i]

            if label == "Steuergerät" and val_str:
                if current_steuergerät and ladepunkte and laengengrad is not None and breitengrad is not None:
                    for lp in ladepunkte:
                        geo_records.append({
                            "Standort": str(standort_name),
                            "Steuergerät": current_steuergerät,
                            "EVSE-ID": lp,
                            "Längengrad": laengengrad,
                            "Breitengrad": breitengrad
                        })

                current_steuergerät = val_str
                ladepunkte = []
                laengengrad = None
                breitengrad = None
                continue

            if label == "Ladepunkt" and re.match(r"DE\*ARK\*E\d{5}\*\d{3}", val_str, re.IGNORECASE):
                ladepunkte.append(val_str)
                continue

            if label == "Längengrad" and val_str:
                try:
                    val_clean = val_str.replace(",", ".").replace("°", "").strip()
                    matches = re.findall(r"[-+]?\d*\.\d+|\d+", val_clean)
                    laengengrad = float(matches[0]) if matches else None
                except (ValueError, IndexError):
                    laengengrad = None
                continue

            if label == "Breitengrad" and val_str:
                try:
                    val_clean = val_str.replace(",", ".").replace("°", "").strip()
                    matches = re.findall(r"[-+]?\d*\.\d+|\d+", val_clean)
                    breitengrad = float(matches[0]) if matches else None
                except (ValueError, IndexError):
                    breitengrad = None
                continue

        # Speichere den letzten Block der Spalte.
        if current_steuergerät and ladepunkte and laengengrad is not None and breitengrad is not None:
            for lp in ladepunkte:
                geo_records.append({
                    "Standort": str(standort_name),
                    "Steuergerät": current_steuergerät,
                    "EVSE-ID": lp,
                    "Längengrad": laengengrad,
                    "Breitengrad": breitengrad
                })

    geo_df = pd.DataFrame(geo_records)

    if not geo_df.empty:
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
df_data = None
if uploaded_file_1:
    df_raw = load_excel(uploaded_file_1)
    if not df_raw.empty:
        df_data = transform_monthly_data(df_raw)

        st.subheader("📊 Bereinigte Monatswerte je Standort")
        st.dataframe(df_data.head(20), use_container_width=True)

        standorte = sorted(df_data["Standort"].dropna().unique())
        if standorte:
            selected_standort = st.selectbox("Standort auswählen:", standorte)
            df_filtered = df_data[df_data["Standort"] == selected_standort]

            st.markdown(
                f"**Anzahl Ladepunkte:** {df_filtered['EVSE'].nunique()} | **Steuergeräte:** {df_filtered['Steuergerät'].nunique()}")

            df_chart = df_filtered.groupby("Monat")["Energiemenge"].sum().reset_index()
            st.bar_chart(df_chart, x="Monat", y="Energiemenge", use_container_width=True)
else:
    st.info("Bitte zuerst die Datei **Test LP-Tool.xlsx** hochladen.")

# ===============================
# 🗺️ HEATMAP
# ===============================
if df_data is not None and uploaded_file_2:
    df_geo = load_geo_excel(uploaded_file_2)

    st.subheader("🌍 Standort-Heatmap basierend auf Energiemengen")

    if not df_geo.empty:
        st.markdown("Erfolgreich eingelesene Geodaten (Auszug):")
        st.dataframe(df_geo.head(20), use_container_width=True)

        df_sum = df_data.groupby("Standort")["Energiemenge"].sum().reset_index()

        df_geo_unique = df_geo.groupby("Standort")[["Breitengrad", "Längengrad"]].first().reset_index()

        df_merged = pd.merge(
            df_sum,
            df_geo_unique,
            on="Standort",
            how="inner"
        )

        if not df_merged.empty:
            st.pydeck_chart(pdk.Deck(
                map_style="mapbox://styles/mapbox/light-v9",
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
                        pickable=True
                    )
                ],
                tooltip={
                    "html": "<b>Standort:</b> {Standort} <br/> <b>Energiemenge:</b> {Energiemenge} kWh",
                    "style": {
                        "backgroundColor": "steelblue",
                        "color": "white"
                    }
                }
            ))
        else:
            st.warning("Keine übereinstimmenden Standorte zwischen den beiden Dateien für die Heatmap gefunden.")
    else:
        st.warning("Die hochgeladene Geo-Datei enthält keine gültigen oder auslesbaren Koordinaten.")
