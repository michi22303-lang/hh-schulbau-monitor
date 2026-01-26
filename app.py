import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2

# --- 1. DATENBASIS ---
SCHUL_DATEN = {
    "Altona": {
        "Othmarschen": [
            {
                "name": "Gymnasium Hochrad", 
                "id": "5887", 
                "students": 950, 
                "address": "Hochrad 2, 22605 Hamburg",
                "kess": 6, 
                "baujahr": "1902"
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

STADTTEIL_INFOS = {
    "Othmarschen": "Wohlhabender Elbvorort, geprägt durch Villenbebauung. Geringe Dichte, viel Grün.",
    "Kirchwerder": "Ländlich, Teil der Vierlande. Landwirtschaft, Naturschutz, geringe Dichte.",
    "Billstedt": "Dicht besiedelt, hoher Geschosswohnungsbau, multikulturell, Entwicklungsgebiet."
}

# --- 2. APIS & WMS ---
API_URL_TRANSPARENZ = "https://suche.transparenz.hamburg.de/api/3/action/package_search"
API_URL_WEATHER = "https://api.open-meteo.com/v1/forecast"

# Geodienste Hamburg
WMS_ALKIS = "https://geodienste.hamburg.de/HH_WMS_ALKIS"
WMS_DENKMAL = "https://geodienste.hamburg.de/HH_WMS_Denkmalkartierung"
WMS_LAERM = "https://geodienste.hamburg.de/HH_WMS_Strassenlaerm_2017"
WMS_HOCHWASSER = "https://geodienste.hamburg.de/HH_WMS_Ueberschwemmungsgebiete"
WMS_SOLAR = "https://geodienste.hamburg.de/HH_WMS_Solaratlas"
WMS_GRUENDACH = "https://geodienste.hamburg.de/HH_WMS_Gruendachpotenzial"

# --- 3. HELFER ---
@st.cache_data(show_spinner=False)
def get_coordinates(address_string):
    if not address_string: return None
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address_string, "format": "json", "limit": 1}
    headers = {'User-Agent': 'HH-Schulbau-Monitor-V12/1.0'}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        data = response.json()
        if data:
            return [float(data[0]["lat"]), float(data[0]["lon"])]
    except: return None
    return None

def get_weather_data(lat, lon):
    params = {"latitude": lat, "longitude": lon, "current_weather": "true", "timezone": "Europe/Berlin"}
    try:
        r = requests.get(API_URL_WEATHER, params=params, timeout=3)
        return r.json().get("current_weather", None)
    except: return None

def calculate_distance_rathaus(lat, lon):
    R = 6373.0
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
st.set_page_config(page_title="HH Schulbau Monitor V12", layout="wide", page_icon="🏫")
st.title("🏫 Hamburger Schulbau-Monitor")

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("1. Standort")
    bezirke = list(SCHUL_DATEN.keys())
    selected_bezirk = st.selectbox("Bezirk", bezirke)
    stadtteile = list(SCHUL_DATEN[selected_bezirk].keys())
    selected_stadtteil = st.selectbox("Stadtteil", stadtteile)
    schulen_liste = SCHUL_DATEN[selected_bezirk][selected_stadtteil]
    schule_obj = st.selectbox("Schule", schulen_liste, format_func=lambda x: f"{x['name']} ({x['id']})")
    
    st.markdown("---")
    
    st.header("2. Karten-Optionen")
    
    # BASICS
    st.caption("Grundlagen")
    map_style = st.radio("Hintergrund:", ("Straßen (OSM)", "Satellit (Hybrid)", "Grau (Planung)"), index=0)
    
    # WIEDER DA: RADIUS & BAHN
    st.caption("Orientierung (Wieder da!)")
    show_radius = st.checkbox("⭕ 1km Einzugsgebiet", value=True)
    show_transit = st.checkbox("🚆 ÖPNV / Bahn", value=True)
    
    # FACHDATEN
    st.caption("Fach-Layer (Overlays)")
    show_alkis = st.checkbox("📐 Kataster (ALKIS)", value=True)
    show_denkmal = st.checkbox("🏛️ Denkmalschutz", value=False)
    show_laerm = st.checkbox("🔊 Straßenlärm (Lden)", value=False)
    show_flood = st.checkbox("🌊 Hochwasser-Risiko", value=False)
    
    st.divider()
    if st.button("🔄 Reset"):
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
    dist = calculate_distance_rathaus(coords[0], coords[1])
    col3.metric("Luftlinie Zentrum", f"{dist:.1f} km")
    col4.metric("Schülerzahl", schule_obj.get('students', '-'))

    st.markdown("---")

    # TABS (Jetzt 4 Stück!)
    tab_map, tab_energy, tab_env, tab_docs = st.tabs(["🗺️ Hauptkarte", "☀️ Energie & Nachhaltigkeit", "📊 Umfeld & Wetter", "📂 Dokumente"])

    # --- TAB 1: HAUPTKARTE ---
    with tab_map:
        # 1. Basis-Karte erstellen
        if map_style == "Straßen (OSM)":
            m = folium.Map(location=coords, zoom_start=18, tiles="OpenStreetMap")
        elif map_style == "Satellit (Hybrid)":
            m = folium.Map(location=coords, zoom_start=18, tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr="Esri")
            folium.TileLayer(tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", attr="Esri Ref", overlay=True, name="Labels").add_to(m)
        else:
            m = folium.Map(location=coords, zoom_start=18, tiles="cartodbpositron", attr="CartoDB")

        # 2. Orientierung (Radius & Bahn) - ZUERST hinzufügen
        if show_radius:
            folium.Circle(
                radius=1000, 
                location=coords, 
                color="#3186cc", 
                fill=True, 
                fill_opacity=0.05, 
                popup="1km Radius"
            ).add_to(m)
            
        if show_transit:
            folium.TileLayer(
                tiles="https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png", 
                attr="OpenRailwayMap", 
                overlay=True,
                name="ÖPNV"
            ).add_to(m)

        # 3. WMS Overlays (ALKIS, Lärm, Denkmal) - DANACH hinzufügen (Layer Order!)
        if show_alkis:
            folium.WmsTileLayer(
                url=WMS_ALKIS, 
                layers="alkis_flurstuecke,alkis_gebaeude", 
                fmt="image/png", transparent=True, 
                name="ALKIS", attr="HH Geodienste", overlay=True
            ).add_to(m)
            
        if show_denkmal:
            folium.WmsTileLayer(
                url=WMS_DENKMAL, 
                layers="dk_denkmal_flaeche,dk_denkmal_punkt", 
                fmt="image/png", transparent=True, 
                name="Denkmalschutz", attr="HH Geodienste", overlay=True
            ).add_to(m)
            
        if show_laerm:
            folium.WmsTileLayer(
                url=WMS_LAERM, 
                layers="laerm_str_lden", 
                fmt="image/png", transparent=True, opacity=0.6, 
                name="Lärm", attr="HH Geodienste", overlay=True
            ).add_to(m)
            
        if show_flood:
            folium.WmsTileLayer(
                url=WMS_HOCHWASSER, 
                layers="ueberschwemmungsgebiete", 
                fmt="image/png", transparent=True, opacity=0.5, 
                name="Hochwasser", attr="HH Geodienste", overlay=True
            ).add_to(m)

        # 4. Marker (Ganz oben)
        folium.Marker(coords, popup=schule_obj['name'], icon=folium.Icon(color="red", icon="graduation-cap", prefix="fa")).add_to(m)

        # Rendern
        st_folium(m, height=600, use_container_width=True, key=f"main_map_{schule_obj['id']}_{map_style}_{show_transit}_{show_radius}_{show_laerm}")
        
        # Externe Links
        c1, c2, c3 = st.columns(3)
        c1.link_button("🌍 3D Google Earth", f"https://earth.google.com/web/search/{coords[0]},{coords[1]}")
        c2.link_button("🗺️ Google Maps", f"https://www.google.com/maps/search/?api=1&query={coords[0]},{coords[1]}")
        c3.link_button("📰 News zur Schule", f"https://www.google.com/search?q={schule_obj['name']}+Hamburg&tbm=nws")

    # --- TAB 2: ENERGIE (NEU!) ---
    with tab_energy:
        st.subheader("☀️ Solaratlas & Gründach-Potenzial")
        st.info("Diese Karte zeigt, welche Dächer für Photovoltaik geeignet sind. Datenquelle: Hamburger Solaratlas.")
        
        col_e_map, col_e_legend = st.columns([3, 1])
        
        with col_e_map:
            m_solar = folium.Map(location=coords, zoom_start=19, tiles="cartodbpositron")
            
            # Basis Luftbild (damit man das Dach erkennt)
            folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                attr="Esri",
                name="Luftbild",
                overlay=False
            ).add_to(m_solar)

            # Solar Layer
            folium.WmsTileLayer(
                url=WMS_SOLAR,
                layers="solar_potenzial_dach", # Layer Name kann variieren, oft "klasse_dachflaechen" oder ähnlich
                fmt="image/png",
                transparent=True,
                opacity=0.7,
                name="Solarpotenzial",
                attr="Geoportal Hamburg",
                overlay=True
            ).add_to(m_solar)
            
            folium.Marker(coords, popup="Standort", icon=folium.Icon(color="red", icon="bolt", prefix="fa")).add_to(m_solar)
            st_folium(m_solar, height=500, use_container_width=True, key="solar_map")
            
        with col_e_legend:
            st.markdown("**Legende Potenzial:**")
            st.markdown("🔴 **Sehr gut** (Süd-Ausrichtung)")
            st.markdown("🟠 **Gut** (Ost/West)")
            st.markdown("🟡 **Bedingt**")
            st.markdown("⚪ **Nicht geeignet**")
            st.caption("Ein Klick auf die Dächer ist hier nicht möglich, bitte nutzen Sie dafür 'Geo-Online'.")


    # --- TAB 3: UMFELD & WETTER ---
    with tab_env:
        col_weather, col_social = st.columns(2)
        with col_weather:
            st.subheader("🌦️ Wetter")
            weather = get_weather_data(coords[0], coords[1])
            if weather:
                w_code = weather['weathercode']
                icon = "☀️" if w_code == 0 else "🌧️"
                st.metric("Temperatur", f"{weather['temperature']} °C", f"Wind: {weather['windspeed']} km/h")
                st.caption(f"Status: {icon} (Code {w_code})")
            else:
                st.warning("Keine Daten.")

        with col_social:
            st.subheader("🏙️ Profil")
            st.markdown(f"**Stadtteil:** {STADTTEIL_INFOS.get(selected_stadtteil, '-')}")
            kess = schule_obj.get("kess", 3)
            st.markdown(f"**Sozialindex (KESS): {kess}/6**")
            st.progress(kess/6)
            st.caption("Höher = Schwierigeres Umfeld / Mehr Förderbedarf")

    # --- TAB 4: DOKUMENTE ---
    with tab_docs:
        schul_query = f'"{schule_obj["name"]}" OR "{schule_obj["id"]}"'
        scenarios = [
            {"Icon": "📜", "Topic": "SEPL", "Query": f'Schulentwicklungsplan "{selected_bezirk}"'},
            {"Icon": "🏗️", "Topic": "Bau & Sanierung", "Query": f'{schul_query} Neubau OR Sanierung'},
            {"Icon": "⚖️", "Topic": "B-Plan", "Query": f'Bebauungsplan "{selected_stadtteil}"'}
        ]
        for s in scenarios:
            with st.expander(f"{s['Icon']} {s['Topic']}", expanded=False):
                with st.spinner("Suche..."):
                    raw = query_transparenzportal(s['Query'])
                if raw:
                    st.dataframe(pd.DataFrame(extract_docs(raw)), column_config={"Link": st.column_config.LinkColumn("PDF")}, hide_index=True)
                else:
                    st.caption("Nichts gefunden.")
