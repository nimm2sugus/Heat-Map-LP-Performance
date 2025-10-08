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
st.markdown("Diese App liest Excel-Dateien mit Monatswerten pro Ladepunkt und erstellt Diagramme und eine geografische Heatmap.")

# ===============================
# ⚙️ CACHING FÜR MONATSDATEN
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
    df = df.rename(columns={"Steuergerät ID": "Steuergerät", "EVSE-ID": "EVSE", "YTD-Summe": "YTD_Summe", "YTD-Schnitt (pro Monat)": "YTD_Schnitt"})
    month_order = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
    id_cols = ["Standort", "Steuergerät", "EVSE", "YTD_Summe", "YTD_Schnitt"]
    df_long = df.melt(id_vars=id_cols, value_vars=[c for c in month_order if c in df.columns], var_name="Monat", value_name="Energiemenge")
    df_long["Energiemenge"] = pd.to_numeric(df_long["Energiemenge"], errors="coerce")
    df_long = df_long.dropna(subset=["Energiemenge"])
    df_long["Monat"] = pd.Categorical(df_long["Monat"], categories=month_order, ordered=True)
    df_long = df_long.sort_values(["Standort", "Monat"])
    return df_long

# ===============================
# ⚙️ DEBUG-VERSION DER GEO-FUNKTION
# ===============================
@st.cache_data(show_spinner=True)
def load_geo_excel_debug(file):
    st.info("DEBUG-MODUS: Starte Einlesen der Geo-Datei...")
    
    raw = pd.read_excel(file, header=None)
    header_row_index = -1
    for i in range(min(10, len(raw))):
        if any(pd.notna(val) for val in raw.iloc[i, 1:].values):
            header_row_index = i
            st.info(f"DEBUG: Header-Zeile mit Standortnamen in Zeile {i+1} der Excel-Datei gefunden.")
            break
            
    if header_row_index == -1:
        st.error("DEBUG-FEHLER: Konnte keine Header-Zeile (mit Standorten ab Spalte B) finden. Abbruch.")
        return pd.DataFrame()

    standort_namen = raw.iloc[header_row_index, 1:].tolist()
    data_df = raw.iloc[header_row_index + 1:].reset_index(drop=True)
    labels = data_df.iloc[:, 0].astype(str).str.strip()
    geo_records = []
    
    st.info(f"DEBUG: {len(standort_namen)} Standorte (Spalten) werden verarbeitet.")

    for col_idx, standort_name in enumerate(standort_namen, start=1):
        if pd.isna(standort_name) or col_idx >= len(data_df.columns): continue
        
        st.markdown(f"--- \n ### DEBUG: Verarbeite Standort: `{standort_name}`")
        col_values = data_df.iloc[:, col_idx]
        current_steuergerät, ladepunkte, laengengrad, breitengrad = None, [], None, None

        for i, val in enumerate(col_values):
            if pd.isna(val) or i >= len(labels): continue
            val_str, label = str(val).strip(), labels[i]

            if label == "Steuergerät" and val_str:
                if current_steuergerät:
                    st.warning(f"DEBUG: Prüfe vorherigen Block '{current_steuergerät}'...")
                    is_complete = True
                    if not ladepunkte: is_complete = False; st.error("   - FEHLER: Keine EVSE-IDs gefunden.")
                    if laengengrad is None: is_complete = False; st.error("   - FEHLER: Längengrad fehlt.")
                    if breitengrad is None: is_complete = False; st.error("   - FEHLER: Breitengrad fehlt.")
                    
                    if is_complete:
                        st.success(f"   -> Block '{current_steuergerät}' ist vollständig und wird gespeichert.")
                        for lp in ladepunkte: geo_records.append({"Standort": str(standort_name), "Steuergerät": current_steuergerät, "EVSE-ID": lp, "Längengrad": laengengrad, "Breitengrad": breitengrad})
                    else:
                        st.error(f"   -> Block '{current_steuergerät}' ist unvollständig und wird VERWORFEN.")
                
                st.info(f"DEBUG: Neuer Block für Steuergerät '{val_str}' gestartet.")
                current_steuergerät, ladepunkte, laengengrad, breitengrad = val_str, [], None, None
                continue

            if label == "EVSE-ID":
                if re.match(r"DE\*ARK\*E\d{5}\*\d{3}", val_str, re.IGNORECASE):
                    ladepunkte.append(val_str)
                else: 
                    st.warning(f"DEBUG: Ignoriere EVSE-ID '{val_str}', da sie nicht dem erwarteten Format entspricht.")
            elif label == "Längengrad" and val_str:
                try: laengengrad = float(re.findall(r"[-+]?\d*\.\d+|\d+", val_str.replace(",", ".").replace("°", "").strip())[0])
                except (ValueError, IndexError): laengengrad = None
            elif label == "Breitengrad" and val_str:
                try: breitengrad = float(re.findall(r"[-+]?\d*\.\d+|\d+", val_str.replace(",", ".").replace("°", "").strip())[0])
                except (ValueError, IndexError): breitengrad = None

        if current_steuergerät:
            st.warning(f"DEBUG: Prüfe letzten Block '{current_steuergerät}' in Spalte '{standort_name}'...")
            is_complete = True
            if not ladepunkte: is_complete = False; st.error("   - FEHLER: Keine EVSE-IDs gefunden.")
            if laengengrad is None: is_complete = False; st.error("   - FEHLER: Längengrad fehlt.")
            if breitengrad is None: is_complete = False; st.error("   - FEHLER: Breitengrad fehlt.")

            if is_complete:
                st.success(f"   -> Letzter Block '{current_steuergerät}' ist vollständig und wird gespeichert.")
                for lp in ladepunkte: geo_records.append({"Standort": str(standort_name), "Steuergerät": current_steuergerät, "EVSE-ID": lp, "Längengrad": laengengrad, "Breitengrad": breitengrad})
            else:
                st.error(f"   -> Letzter Block '{current_steuergerät}' ist unvollständig und wird VERWORFEN.")
    
    st.markdown("---")
    st.info(f"DEBUG-ZUSAMMENFASSUNG: {len(geo_records)} gültige Datensätze vor der Endprüfung gefunden.")
    geo_df = pd.DataFrame(geo_records)
    if not geo_df.empty:
        cleaned_df = geo_df.dropna(subset=["Breitengrad", "Längengrad"])
        st.info(f"DEBUG: Nach der Endprüfung bleiben {len(cleaned_df)} Datensätze übrig.")
        return cleaned_df
    
    st.error("DEBUG-ERGEBNIS: Die Funktion gibt eine leere Tabelle zurück.")
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
            st.markdown(f"**Anzahl Ladepunkte:** {df_filtered['EVSE'].nunique()} | **Steuergeräte:** {df_filtered['Steuergerät'].nunique()}")
            df_chart = df_filtered.groupby("Monat")["Energiemenge"].sum().reset_index()
            st.bar_chart(df_chart, x="Monat", y="Energiemenge", use_container_width=True)
else:
    st.info("Bitte zuerst die Datei **Test LP-Tool.xlsx** hochladen.")

# ===============================
# 🗺️ HEATMAP
# ===============================
if df_data is not None and uploaded_file_2:
    # HIER WIRD DIE DEBUG-FUNKTION AUFGERUFEN
    df_geo = load_geo_excel_debug(uploaded_file_2)
    
    st.header("🌍 Standort-Heatmap")

    if not df_geo.empty:
        time_options = ["Gesamtzeit"] + df_data['Monat'].unique().tolist()
        selected_timespan = st.selectbox("Zeitraum für Heatmap auswählen:", time_options)

        if selected_timespan == "Gesamtzeit":
            st.subheader("Gesamtenergiemenge aller Monate")
            df_sum = df_data.groupby("Standort")["Energiemenge"].sum().reset_index()
        else:
            st.subheader(f"Energiemenge im {selected_timespan}")
            df_monthly = df_data[df_data["Monat"] == selected_timespan]
            df_sum = df_monthly.groupby("Standort")["Energiemenge"].sum().reset_index()

        df_geo_unique = df_geo.groupby("Standort")[["Breitengrad", "Längengrad"]].first().reset_index()
        df_merged = pd.merge(df_sum, df_geo_unique, on="Standort", how="inner")

        if not df_merged.empty:
            st.pydeck_chart(pdk.Deck(
                map_style="mapbox://styles/mapbox/light-v9",
                initial_view_state=pdk.ViewState(latitude=df_merged["Breitengrad"].mean(), longitude=df_merged["Längengrad"].mean(), zoom=6, pitch=0),
                layers=[
                    pdk.Layer("HeatmapLayer", data=df_merged, get_position='[Längengrad, Breitengrad]', get_weight="Energiemenge", radiusPixels=60, aggregation=pdk.types.String("SUM")),
                    pdk.Layer("ScatterplotLayer", data=df_merged, get_position='[Längengrad, Breitengrad]', get_radius=3000, get_fill_color='[255, 0, 0, 160]', pickable=True)
                ],
                tooltip={"html": "<b>Standort:</b> {Standort} <br/> <b>Energiemenge:</b> {Energiemenge} kWh", "style": {"backgroundColor": "steelblue", "color": "white"}}
            ))
        else:
            st.warning(f"Keine übereinstimmenden Standorte mit Energiedaten für den Zeitraum '{selected_timespan}' gefunden.")
    else:
        st.warning("Die hochgeladene Geo-Datei enthält keine gültigen oder auslesbaren Koordinaten. Bitte prüfen Sie die DEBUG-Meldungen oben.")
