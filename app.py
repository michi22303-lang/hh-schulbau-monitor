import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2

# --- 1. ERWEITERTE DATENBASIS ---
# Wir simulieren hier harte Fakten, die Wikipedia ersetzen
SCHUL_DATEN = {
    "Altona": {
        "Othmarschen": [
            {
                "name": "Gymnasium Hochrad", 
                "id": "5887", 
                "students": 950, 
                "address": "Hochrad 2, 22605 Hamburg",
                "kess": 6, # Sozialindex (1=niedrig, 6=hoch)
                "baujahr": "1902 / Erweiterungen 1970er"
            } 
        ]
    },
    "Bergedorf": {
        "Kirchwerder": [
            {
                "name": "Schule Zollenspieker", 
                "id": "5648", 
                "students": 230, 
                "address": "Kirchwerder Landweg 558, 21037 Hamburg",
                "kess": 4,
                "baujahr": "1910"
            }
        ]
    },
    "Mitte": {
        "Billstedt": [
            {
                "name": "Grundschule Mümmelmannsberg", 
                "id": "5058", 
                "students": 340, 
                "address": "Mümmelmannsberg 52, 22115 Hamburg",
                "kess": 2,
                "baujahr": "1975"
            }
        ]
    }
}

# Statische Stadtteil-Profile (statt Wikipedia)
STADTTEIL_INFOS = {
    "Othmarschen": "Wohlhabender Elbvorort, geprägt durch Villenbebauung und Parkanlagen. Hohes Einkommensniveau, geringe Baudichte.",
    "Kirchwerder": "Ländlich geprägt, Teil der Vier- und Marschlande. Fokus auf Landwirtschaft und Naturschutz, geringe Bevölkerungsdichte.",
    "Billstedt": "Dicht besiedelter Stadtteil im Osten. Hoher Anteil an Geschosswohnungsbau, multikulturelle Bevölkerungsstruktur, Entwicklungsgebiet."
}

# --- 2. APIS ---
API_URL_TRANSPARENZ = "https://suche.transparenz.hamburg.de/api/3/action/package_search"
# Open-Meteo (Kostenlos, kein Key)
API_URL_WEATHER = "https://api.open-meteo.com/v1/forecast"

# Geodienste
WMS_ALKIS = "https://geodienste.hamburg.de/HH_WMS_ALKIS"
WMS_DENKMAL = "https://geodienste.hamburg.de/HH_WMS_Denkmalkartierung"
WMS_LAERM = "https://geodienste.hamburg.de/HH_WMS_Strassenlaerm_2017"
WMS_HOCHWASSER = "https://geodienste.hamburg.de/HH_WMS_Ueberschwemmungsgebiete"

# --- 3. HELFER-FUNKTIONEN ---

@st.cache_data(show_spinner=False)
def get_coordinates(address_string):
    if not address_string: return None
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address_string, "format": "json", "limit": 1}
    headers = {'User-Agent': 'HH-Schulbau-Monitor-V11/1.0'}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        data = response.json()
        if data:
            return [float(data[0]["lat"]), float(data[0]["lon"])]
    except: return None
    return None

def get_weather_data(lat, lon):
    # Holt aktuelles Wetter für Koordinaten
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": "true",
        "timezone": "Europe/Berlin"
    }
    try:
        r = requests.get(API_URL_WEATHER, params=params, timeout=3)
        return r.json().get("current_weather", None)
    except:
        return None

def calculate_distance_rathaus(lat, lon):
    # Haversine Formel für Distanz zum Rathaus (53.550, 9.992)
    R = 6373.0 # Radius Erde km
    lat1, lon1 = radians(53.550), radians(9.992)
    lat2, lon2 = radians(lat), radians(lon)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def query_transparenzportal(search_term, limit=5):
    params = {"q": search_term, "rows": limit, "sort": "score desc, metadata_modified desc"}
    try:
        response = requests.get(API_URL_TRANSPARENZ, params=params, timeout=5)
        data = response.json()
        return data["result"]["results"] if data.get("success") else []
    except: return []

def extract_docs(results):
    cleaned = []
    for item in results:
        res_list = item.get("resources", [])
        link = item.get("url", "")
        for res in res_list:
            if res.get("format", "").lower() == "pdf":
                link = res.get("url")
                break
        cleaned.append({"Dokument": item.get("title"), "Datum": item.get("metadata_modified", "")[:10], "Link": link})
    return cleaned

# --- 4. UI SETUP ---
st.set_page_config(page_title="HH Schulbau Monitor V11", layout="wide", page_icon="🏫")
st.title("🏫 Hamburger Schulbau-Monitor")

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("Standort & Layer")
    
    # Auswahl
    bezirke = list(SCHUL_DATEN.keys())
    selected_bezirk = st.selectbox("Bezirk", bezirke)
    stadtteile = list(SCHUL_DATEN[selected_bezirk].keys())
    selected_stadtteil = st.selectbox("Stadtteil", stadtteile)
    schulen_liste = SCHUL_DATEN[selected_bezirk][selected_stadtteil]
    schule_obj = st.selectbox("Schule", schulen_liste, format_func=lambda x: f"{x['name']} ({x['id']})")
    
    st.markdown("---")
    
    # Karten-Optionen
    map_style = st.radio("Basiskarte:", ("Straßen (OSM)", "Satellit (Hybrid)", "Grau (Planung)"), index=0)
    
    st.caption("Fachdaten:")
    show_alkis = st.checkbox("📐 Kataster (ALKIS)", value=True)
    show_denkmal = st.checkbox("🏛️ Denkmalschutz", value=False)
    show_laerm = st.checkbox("🔊 Straßenlärm", value=False)
    show_flood = st.checkbox("🌊 Hochwasser", value=False)
    
    st.divider()
    if st.button("🔄 Reload"):
        st.cache_data.clear()
        st.rerun()

# --- 6. HAUPTBEREICH ---
if schule_obj:
    adresse = schule_obj.get("address", "")
    coords = get_coordinates(adresse)
    
    if not coords:
        coords = [53.550, 9.992]
        st.warning("Adresse nicht gefunden. Zeige Fallback (Rathaus).")

    # Header Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Bezirk", selected_bezirk)
    col2.metric("Kennziffer", schule_obj.get('id', '-'))
    col3.metric("Schülerzahl", schule_obj.get('students', '-'))
    # Entfernung berechnen
    dist = calculate_distance_rathaus(coords[0], coords[1])
    col4.metric("Distanz Zentrum", f"{dist:.1f} km")
    
    st.markdown("---")

    # TABS
    tab_map, tab_env, tab_docs = st.tabs(["🗺️ Karte", "📊 Umfeld & Wetter", "📂 Dokumente"])

    # --- TAB 1: KARTE ---
    with tab_map:
        if map_style == "Straßen (OSM)":
            m = folium.Map(location=coords, zoom_start=18, tiles="OpenStreetMap")
        elif map_style == "Satellit (Hybrid)":
            m = folium.Map(location=coords, zoom_start=18, tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr="Esri")
            folium.TileLayer(tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", attr="Esri Ref", overlay=True, name="Labels").add_to(m)
        else:
            m = folium.Map(location=coords, zoom_start=18, tiles="cartodbpositron", attr="CartoDB")

        # Overlays
        if show_alkis:
            folium.WmsTileLayer(url=WMS_ALKIS, layers="alkis_flurstuecke,alkis_gebaeude", fmt="image/png", transparent=True, name="ALKIS", attr="Geoportal HH", overlay=True).add_to(m)
        if show_denkmal:
            folium.WmsTileLayer(url=WMS_DENKMAL, layers="dk_denkmal_flaeche,dk_denkmal_punkt", fmt="image/png", transparent=True, name="Denkmalschutz", attr="Geoportal HH", overlay=True).add_to(m)
        if show_laerm:
            folium.WmsTileLayer(url=WMS_LAERM, layers="laerm_str_lden", fmt="image/png", transparent=True, opacity=0.6, name="Lärmkataster", attr="Geoportal HH", overlay=True).add_to(m)
        if show_flood:
            folium.WmsTileLayer(url=WMS_HOCHWASSER, layers="ueberschwemmungsgebiete", fmt="image/png", transparent=True, opacity=0.5, name="Hochwasser", attr="Geoportal HH", overlay=True).add_to(m)

        # Marker
        folium.Marker(coords, popup=schule_obj['name'], icon=folium.Icon(color="red", icon="graduation-cap", prefix="fa")).add_to(m)

        st_folium(m, height=600, use_container_width=True, key=f"map_v11_{schule_obj['id']}_{map_style}_{show_laerm}")
        
        # Link Buttons unter der Karte
        c1, c2, c3 = st.columns(3)
        c1.link_button("🌍 3D Google Earth", f"https://earth.google.com/web/search/{coords[0]},{coords[1]}")
        c2.link_button("🗺️ Google Maps", f"https://www.google.com/maps/search/?api=1&query={coords[0]},{coords[1]}")
        c3.link_button("📰 Google News zur Schule", f"https://www.google.com/search?q={schule_obj['name']}+Hamburg&tbm=nws")


    # --- TAB 2: UMFELD & WETTER (NEU) ---
    with tab_env:
        col_weather, col_social = st.columns(2)
        
        # A) WETTER
        with col_weather:
            st.subheader("🌦️ Wetter vor Ort")
            weather = get_weather_data(coords[0], coords[1])
            if weather:
                w_code = weather['weathercode']
                w_icon = "☀️" if w_code == 0 else "☁️" if w_code < 60 else "🌧️"
                
                wc1, wc2 = st.columns(2)
                wc1.metric("Temperatur", f"{weather['temperature']} °C")
                wc2.metric("Wind", f"{weather['windspeed']} km/h")
                st.caption(f"Status: {w_icon} (Code: {w_code})")
            else:
                st.warning("Wetterdaten nicht verfügbar.")
                
            st.info("Relevanz: Wichtig für Baustellenplanung (Kranbetrieb) und Schulhofgestaltung.")

        # B) SOZIALSTRUKTUR & PROFIL
        with col_social:
            st.subheader("🏙️ Standort-Profil")
            
            # Stadtteil-Text (Ersatz für Wikipedia)
            st_info_text = STADTTEIL_INFOS.get(selected_stadtteil, "Keine spezifischen Daten.")
            st.markdown(f"**Charakteristik {selected_stadtteil}:**")
            st.markdown(f"_{st_info_text}_")
            
            st.divider()
            
            # Sozialindex Visualisierung
            kess = schule_obj.get("kess", 3)
            st.markdown(f"**Sozialindex (KESS-Faktor): {kess}/6**")
            st.progress(kess / 6)
            if kess >= 5:
                st.caption("🔴 Hoher Förderbedarf / Herausforderndes Umfeld")
            elif kess <= 2:
                st.caption("🟢 Privilegiertes Umfeld / Geringer Förderbedarf")
            else:
                st.caption("🟡 Mittlerer Sozialstatus")


    # --- TAB 3: DOKUMENTE ---
    with tab_docs:
        schul_query = f'"{schule_obj["name"]}" OR "{schule_obj["id"]}"'
        search_scenarios = [
            {"Icon": "📜", "Topic": "Schulentwicklungsplan", "Query": f'Schulentwicklungsplan "{selected_bezirk}"'},
            {"Icon": "🏗️", "Topic": "Bau & Sanierung", "Query": f'{schul_query} Neubau OR Sanierung'},
            {"Icon": "⚖️", "Topic": "Bebauungspläne", "Query": f'Bebauungsplan "{selected_stadtteil}"'},
             {"Icon": "💶", "Topic": "Zuwendungen", "Query": f'{schul_query} Zuwendung'}
        ]
        
        for scenario in search_scenarios:
            with st.expander(f"{scenario['Icon']} {scenario['Topic']}", expanded=False):
                with st.spinner("Suche..."):
                    raw = query_transparenzportal(scenario['Query'])
                if raw:
                    st.dataframe(pd.DataFrame(extract_docs(raw)), column_config={"Link": st.column_config.LinkColumn("PDF")}, hide_index=True, use_container_width=True)
                else:
                    st.caption("Keine Ergebnisse.")
