import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2

# --- 1. DATENBASIS ---
SCHUL_DATEN = {
    "Altona": {
        "Othmarschen": [{"name": "Gymnasium Hochrad", "id": "5887", "students": 950, "address": "Hochrad 2, 22605 Hamburg", "kess": 6}] 
    },
    "Bergedorf": {
        "Kirchwerder": [{"name": "Schule Zollenspieker", "id": "5648", "students": 230, "address": "Kirchwerder Landweg 558, 21037 Hamburg", "kess": 4}]
    },
    "Mitte": {
        "Billstedt": [{"name": "Grundschule Mümmelmannsberg", "id": "5058", "students": 340, "address": "Mümmelmannsberg 52, 22115 Hamburg", "kess": 2}]
    }
}

STADTTEIL_INFOS = {
    "Othmarschen": "Wohlhabender Elbvorort, geprägt durch Villenbebauung.",
    "Kirchwerder": "Ländlich, Teil der Vierlande. Fokus auf Landwirtschaft.",
    "Billstedt": "Dicht besiedelt, hoher Geschosswohnungsbau, multikulturell."
}

# --- 2. APIs ---
API_URL_TRANSPARENZ = "https://suche.transparenz.hamburg.de/api/3/action/package_search"
API_URL_WEATHER = "https://api.open-meteo.com/v1/forecast"

# NEU: OGC API Features (Vektordaten für Schulimmobilien)
# Basis-URL für die Urban Data Platform Hamburg
API_OGC_SCHULE = "https://api.hamburg.de/datasets/v1/bsb_sonderverm_schulimmobilien/collections/bsb_sonderverm_schulimmobilien/items"
API_OGC_ERBBAU = "https://api.hamburg.de/datasets/v1/bsb_sonderverm_schulimmobilien/collections/bsb_sonderverm_schulimmobilien_erbbaurecht/items"

# WMS Dienste (Bilder)
WMS_STADTPLAN = "https://geodienste.hamburg.de/HH_WMS_Stadtplan"
WMS_LAERM = "https://geodienste.hamburg.de/HH_WMS_Strassenlaerm_2017"
WMS_SOLAR = "https://geodienste.hamburg.de/HH_WMS_Solaratlas"
WMS_HOCHWASSER = "https://geodienste.hamburg.de/HH_WMS_Ueberschwemmungsgebiete"

# --- 3. HELFER ---
@st.cache_data(show_spinner=False)
def get_coordinates(address_string):
    if not address_string: return None
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address_string, "format": "json", "limit": 1}
    headers = {'User-Agent': 'HH-Schulbau-Monitor-V14/1.0'}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        data = response.json()
        if data:
            return [float(data[0]["lat"]), float(data[0]["lon"])]
    except: return None
    return None

def get_weather_data(lat, lon):
    try:
        params = {"latitude": lat, "longitude": lon, "current_weather": "true", "timezone": "Europe/Berlin"}
        r = requests.get(API_URL_WEATHER, params=params, timeout=3)
        return r.json().get("current_weather", None)
    except: return None

def calculate_distance(lat, lon):
    R = 6373.0
    lat1, lon1 = radians(53.550), radians(9.992)
    lat2, lon2 = radians(lat), radians(lon)
    a = sin((lat2-lat1)/2)**2 + cos(lat1) * cos(lat2) * sin((lon2-lon1)/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

# NEU: Funktion um echte Schulgrenzen (Polygone) zu laden
@st.cache_data(show_spinner=False)
def get_school_property_geojson(lat, lon):
    # Wir bauen eine kleine Bounding Box (Suchfenster) um die Koordinate
    # ca. 200m Umkreis
    delta = 0.002 
    bbox = f"{lon-delta},{lat-delta},{lon+delta},{lat+delta}"
    
    params = {
        "bbox": bbox,
        "limit": 10  # Wir wollen nur Objekte in der Nähe
    }
    
    # 1. Normale Schulimmobilien abfragen
    try:
        r = requests.get(API_OGC_SCHULE, params=params, timeout=5)
        data_normal = r.json()
    except:
        data_normal = None

    # 2. Erbbaurecht abfragen
    try:
        r = requests.get(API_OGC_ERBBAU, params=params, timeout=5)
        data_erbbau = r.json()
    except:
        data_erbbau = None
        
    return data_normal, data_erbbau

def query_transparenzportal(search_term, limit=5):
    try:
        params = {"q": search_term, "rows": limit, "sort": "score desc, metadata_modified desc"}
        r = requests.get(API_URL_TRANSPARENZ, params=params, timeout=5)
        return r.json()["result"]["results"] if r.json().get("success") else []
    except: return []

def extract_docs(results):
    cleaned = []
    for item in results:
        res_list = item.get("resources", [])
        link = item.get("url", "")
        for res in res_list:
            if res.get("format", "").lower() == "pdf":
                link = res.get("url"); break
        cleaned.append({"Dokument": item.get("title"), "Datum": item.get("metadata_modified", "")[:10], "Link": link})
    return cleaned

# --- 4. UI SETUP ---
st.set_page_config(page_title="HH Schulbau Monitor V14", layout="wide", page_icon="🏫")
st.title("🏫 Hamburger Schulbau-Monitor")

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("Standort")
    bezirke = list(SCHUL_DATEN.keys())
    sel_bez = st.selectbox("Bezirk", bezirke)
    sel_stadt = st.selectbox("Stadtteil", list(SCHUL_DATEN[sel_bez].keys()))
    schule_obj = st.selectbox("Schule", SCHUL_DATEN[sel_bez][sel_stadt], format_func=lambda x: f"{x['name']}")
    
    st.markdown("---")
    st.header("Layer-Steuerung")
    
    map_style = st.radio("Hintergrund:", ("Planung (Grau)", "Straßen (OSM)", "Satellit"), index=0)
    
    st.caption("Eigentum & Kataster")
    # Das ist das neue Feature!
    show_real_property = st.checkbox("🟦 Amtliches Schulgrundstück", value=True, help="Zeigt die exakte, amtliche Fläche der Schulimmobilie (blau)")
    show_alkis = st.checkbox("📐 Flurstücke (ALKIS)", value=True)
    
    st.caption("Umwelt & Analyse")
    show_transit = st.checkbox("🚆 ÖPNV", value=True)
    show_radius = st.checkbox("⭕ 1km Radius", value=False)
    show_laerm = st.checkbox("🔊 Straßenlärm", value=False)
    show_flood = st.checkbox("🌊 Hochwasser", value=False)
    
    if st.button("Reset"): st.cache_data.clear(); st.rerun()

# --- 6. MAIN ---
if schule_obj:
    coords = get_coordinates(schule_obj["address"])
    if not coords: coords = [53.550, 9.992]; st.warning("Fallback Koordinaten.")

    # Daten laden (OGC API)
    geo_normal, geo_erbbau = get_school_property_geojson(coords[0], coords[1])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Bezirk", sel_bez)
    c2.metric("Schüler", schule_obj["students"])
    c3.metric("Distanz Zentrum", f"{calculate_distance(coords[0], coords[1]):.1f} km")
    
    # Checken ob wir Daten gefunden haben für das Metric-Feld
    prop_count = 0
    if geo_normal: prop_count += len(geo_normal.get('features', []))
    if geo_erbbau: prop_count += len(geo_erbbau.get('features', []))
    
    c4.metric("Grundstücks-Teile", prop_count, help="Anzahl der gefundenen amtlichen Schul-Flurstücke")
    
    st.markdown("---")
    
    tab_map, tab_solar, tab_info, tab_docs = st.tabs(["🗺️ Karte & Eigentum", "☀️ Solarpotenzial", "📊 Umfeld", "📂 Akten"])

    with tab_map:
        # Basis
        if map_style == "Straßen (OSM)":
            m = folium.Map(location=coords, zoom_start=18, tiles="OpenStreetMap")
        elif map_style == "Satellit":
            m = folium.Map(location=coords, zoom_start=18, tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr="Esri")
            folium.TileLayer(tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", attr="Esri Ref", overlay=True, name="Labels").add_to(m)
        else:
            m = folium.Map(location=coords, zoom_start=18, tiles="cartodbpositron", attr="CartoDB")

        # 1. NEU: Amtliche Schulgrundstücke (Vektordaten)
        if show_real_property:
            # Normale Schulimmobilien (Blau)
            if geo_normal and len(geo_normal.get('features', [])) > 0:
                folium.GeoJson(
                    geo_normal,
                    name="Schulimmobilien (SBH)",
                    style_function=lambda x: {
                        'fillColor': '#0033cc', # Dunkelblau
                        'color': '#0033cc',
                        'weight': 2,
                        'fillOpacity': 0.3
                    },
                    tooltip=folium.GeoJsonTooltip(fields=['id'], aliases=['Objekt-ID:'])
                ).add_to(m)
            
            # Erbbaurecht (Orange)
            if geo_erbbau and len(geo_erbbau.get('features', [])) > 0:
                folium.GeoJson(
                    geo_erbbau,
                    name="Erbbaurecht (SBH)",
                    style_function=lambda x: {
                        'fillColor': '#ff9900', # Orange
                        'color': '#ff9900',
                        'weight': 2,
                        'fillOpacity': 0.4,
                        'dashArray': '5, 5' # Gestrichelt
                    },
                    tooltip="Erbbaurecht"
                ).add_to(m)

        # 2. ALKIS (Schwarzplan)
        if show_alkis:
            folium.WmsTileLayer(
                url=WMS_STADTPLAN, layers="schwarzweiss", fmt="image/png", transparent=True, 
                name="Kataster (Plan)", attr="Geoportal HH", overlay=True, opacity=0.6
            ).add_to(m)

        # 3. Weitere Layer
        if show_transit:
            folium.TileLayer(tiles="https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png", attr="OpenRailwayMap", overlay=True).add_to(m)
        if show_laerm:
            folium.WmsTileLayer(url=WMS_LAERM, layers="laerm_str_lden", fmt="image/png", transparent=True, opacity=0.6, name="Lärm", attr="HH", overlay=True).add_to(m)
        if show_flood:
             folium.WmsTileLayer(url=WMS_HOCHWASSER, layers="ueberschwemmungsgebiete", fmt="image/png", transparent=True, opacity=0.5, name="Hochwasser", attr="HH", overlay=True).add_to(m)
        if show_radius:
            folium.Circle(radius=1000, location=coords, color="#3186cc", fill=True, fill_opacity=0.05).add_to(m)

        folium.Marker(coords, popup=schule_obj["name"], icon=folium.Icon(color="red", icon="graduation-cap", prefix="fa")).add_to(m)
        
        st_folium(m, height=600, use_container_width=True, key=f"map_v14_{schule_obj['id']}_{map_style}_{show_real_property}")
        
        # Legende für das neue Feature
        if show_real_property:
            st.info("🟦 **Blaue Flächen:** Amtliches Sondervermögen Schulimmobilien | 🟧 **Orange:** Erbbaurecht")

    with tab_solar:
        col_s1, col_s2 = st.columns([3,1])
        with col_s1:
            m_solar = folium.Map(location=coords, zoom_start=19, tiles="cartodbpositron")
            folium.TileLayer(tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr="Esri", overlay=False).add_to(m_solar)
            folium.WmsTileLayer(url=WMS_SOLAR, layers="solarpotenzial_dach", fmt="image/png", transparent=True, opacity=0.8, name="Solar", attr="Geoportal HH", overlay=True).add_to(m_solar)
            st_folium(m_solar, height=500, use_container_width=True, key="solar_view")
        with col_s2:
            st.markdown("🔴 Sehr gut\n🟠 Gut\n🟡 Mittel")

    with tab_info:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Wetter")
            w = get_weather_data(coords[0], coords[1])
            if w: st.metric("Temp", f"{w['temperature']} °C", f"Wind: {w['windspeed']} km/h")
        with c2:
            st.subheader("Profil")
            st.markdown(f"**{sel_stadt}**")
            st.progress(schule_obj['kess']/6)
            st.caption("KESS (Sozialindex)")

    with tab_docs:
        q_name = f'"{schule_obj["name"]}" OR "{schule_obj["id"]}"'
        scenarios = [
            {"Topic": "Schulentwicklungsplan", "Q": f'Schulentwicklungsplan "{sel_bez}"'},
            {"Topic": "Bau & Sanierung", "Q": f'{q_name} Neubau OR Sanierung'},
            {"Topic": "Finanzen", "Q": f'{q_name} Zuwendung'}
        ]
        for s in scenarios:
            with st.expander(f"🔎 {s['Topic']}", expanded=False):
                data = query_transparenzportal(s['Q'])
                if data: st.dataframe(pd.DataFrame(extract_docs(data)), hide_index=True)
                else: st.caption("Keine Treffer.")
