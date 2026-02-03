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
    "Othmarschen": "Wohlhabender Elbvorort, Villenbebauung.",
    "Kirchwerder": "Ländlich, Vierlande, Landwirtschaft.",
    "Billstedt": "Dicht besiedelt, Geschosswohnungsbau."
}

# --- 2. APIs & DIENSTE ---
API_URL_TRANSPARENZ = "https://suche.transparenz.hamburg.de/api/3/action/package_search"
API_URL_WEATHER = "https://api.open-meteo.com/v1/forecast"

# KORREKTE URLS FÜR HAMBURG
# 1. WFS für die blauen Flächen (LIG)
WFS_LIG_URL = "https://geodienste.hamburg.de/HH_WFS_LIG_Grundbesitz"
# 2. WFS für ALKIS (Die normalen schwarzen Linien - als Fallback extrem wichtig!)
WFS_ALKIS_URL = "https://geodienste.hamburg.de/HH_WFS_ALKIS"

# WMS (Hintergrundbilder)
WMS_STADTPLAN = "https://geodienste.hamburg.de/HH_WMS_Stadtplan"
WMS_SOLAR = "https://geodienste.hamburg.de/HH_WMS_Solaratlas"

# --- 3. HELFER ---
@st.cache_data(show_spinner=False)
def get_coordinates(address_string):
    if not address_string: return None
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address_string, "format": "json", "limit": 1}
    headers = {'User-Agent': 'HH-Schulbau-Monitor-V18/1.0'}
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

# --- WFS ABFRAGE (ROBUST) ---
@st.cache_data(show_spinner=False)
def get_wfs_data(url, layer_name, lat, lon):
    # Wir nutzen WFS 1.1.0 -> Das ist toleranter mit Koordinaten
    version = "1.1.0"
    
    # Bounding Box: 
    # Bei WFS 1.1.0 und EPSG:4326 ist die Reihenfolge oft: Lat, Lon (oder umgekehrt je nach Server-Laune)
    # Wir machen die Box groß genug, damit wir treffen (ca 300m)
    d = 0.003
    
    # Standard-Versuch: Lat, Lon (Wie GPS)
    bbox = f"{lat-d},{lon-d},{lat+d},{lon+d}"
    
    params = {
        "SERVICE": "WFS",
        "VERSION": version,
        "REQUEST": "GetFeature",
        "TYPENAME": layer_name, # Achtung: 1.1.0 heißt es TYPENAME (ohne S)
        "OUTPUTFORMAT": "application/json", # GeoJSON
        "SRSNAME": "EPSG:4326",
        "BBOX": f"{bbox},EPSG:4326"
    }
    
    try:
        # Request senden
        r = requests.get(url, params=params, timeout=8)
        
        # Debugging-Hilfe: URL speichern
        final_url = r.url
        
        if r.status_code == 200:
            data = r.json()
            # Checken ob Features drin sind
            count = len(data.get('features', []))
            return data, count, final_url
        else:
            return None, 0, final_url
    except Exception as e:
        return None, 0, str(e)

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
st.set_page_config(page_title="HH Schulbau Monitor V18", layout="wide", page_icon="🏫")
st.title("🏫 Hamburger Schulbau-Monitor")

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("Standort")
    bezirke = list(SCHUL_DATEN.keys())
    sel_bez = st.selectbox("Bezirk", bezirke)
    sel_stadt = st.selectbox("Stadtteil", list(SCHUL_DATEN[sel_bez].keys()))
    schule_obj = st.selectbox("Schule", SCHUL_DATEN[sel_bez][sel_stadt], format_func=lambda x: f"{x['name']}")
    
    st.markdown("---")
    st.header("Karten-Layer")
    
    map_style = st.radio("Hintergrund:", ("Planung (Grau)", "Straßen (OSM)", "Satellit"), index=0)
    
    st.caption("Vektor-Daten (Klickbar)")
    show_schul_prop = st.checkbox("🟦 Schul-Eigentum (LIG)", value=True, help="Versucht, das spezielle Schulgrundstück zu laden")
    show_alkis_vec = st.checkbox("⬛ Alle Flurstücke (ALKIS)", value=True, help="Lädt ALLE Grundstücksgrenzen als Backup")
    
    st.caption("Bild-Overlays")
    show_transit = st.checkbox("🚆 ÖPNV", value=True)
    
    if st.button("Reset"): st.cache_data.clear(); st.rerun()

# --- 6. MAIN ---
if schule_obj:
    coords = get_coordinates(schule_obj["address"])
    if not coords: coords = [53.550, 9.992]; st.warning("Fallback Koordinaten.")

    # 1. VERSUCH: Schulimmobilien (LIG)
    geo_schule, count_schule, url_schule = get_wfs_data(
        WFS_LIG_URL, 
        "bsb_sonderverm_schulimmobilien", 
        coords[0], coords[1]
    )
    
    # 2. VERSUCH: ALKIS Flurstücke (Immer da!)
    # Layername oft: "alkis_flurstuecke" oder "flurstueck"
    # Wir nutzen den Dienst, der sicher geht.
    geo_alkis, count_alkis, url_alkis = get_wfs_data(
        WFS_ALKIS_URL,
        "alkis_flurstuecke", 
        coords[0], coords[1]
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Bezirk", sel_bez)
    c2.metric("Schüler", schule_obj["students"])
    
    # Statusanzeige
    if count_schule > 0:
        c3.metric("Schul-Fläche", "Gefunden ✅")
    else:
        c3.metric("Schul-Fläche", "Nicht definiert ❌")
        
    c4.metric("Flurstücke Umgebung", count_alkis)
    
    st.markdown("---")
    
    tab_map, tab_solar, tab_info, tab_docs = st.tabs(["🗺️ Karte & Grenzen", "☀️ Solarpotenzial", "📊 Umfeld", "📂 Akten"])

    with tab_map:
        if map_style == "Straßen (OSM)":
            m = folium.Map(location=coords, zoom_start=18, tiles="OpenStreetMap")
        elif map_style == "Satellit":
            m = folium.Map(location=coords, zoom_start=18, tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr="Esri")
            folium.TileLayer(tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", attr="Esri Ref", overlay=True, name="Labels").add_to(m)
        else:
            m = folium.Map(location=coords, zoom_start=18, tiles="cartodbpositron", attr="CartoDB")

        # LAYER A: Schulimmobilien (Blau gefüllt)
        if show_schul_prop and count_schule > 0:
            folium.GeoJson(
                geo_schule,
                name="Schulimmobilien",
                style_function=lambda x: {'fillColor': '#0044ff', 'color': '#0044ff', 'weight': 3, 'fillOpacity': 0.4},
                tooltip=folium.GeoJsonTooltip(fields=['flurstueckskennzeichen'], aliases=['Flurstück:'], localize=True)
            ).add_to(m)
        
        # LAYER B: ALKIS Flurstücke (Schwarze Linien, keine Füllung) -> Das ist das Sicherheitsnetz!
        if show_alkis_vec and count_alkis > 0:
            folium.GeoJson(
                geo_alkis,
                name="Alle Flurstücke",
                style_function=lambda x: {'fillColor': 'transparent', 'color': 'black', 'weight': 1, 'opacity': 0.5},
                tooltip="Flurstücksgrenze"
            ).add_to(m)

        # Overlays
        if show_transit:
            folium.TileLayer(tiles="https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png", attr="OpenRailwayMap", overlay=True).add_to(m)

        folium.Marker(coords, popup=schule_obj["name"], icon=folium.Icon(color="red", icon="graduation-cap", prefix="fa")).add_to(m)
        
        st_folium(m, height=600, use_container_width=True, key=f"map_v18_{schule_obj['id']}_{map_style}")
        
        # Info Box
        if count_schule == 0:
            st.warning("⚠️ Hinweis: Es wurde keine explizite Schulfläche im LIG-Datensatz gefunden. Die schwarzen Linien (ALKIS) zeigen aber die korrekten Grundstücksgrenzen.")

    with tab_solar:
        col_s1, col_s2 = st.columns([3,1])
        with col_s1:
            m_solar = folium.Map(location=coords, zoom_start=19, tiles="cartodbpositron")
            folium.TileLayer(tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr="Esri", overlay=False).add_to(m_solar)
            # Nutze WMS für Solar, da Bilder ausreichen
            folium.WmsTileLayer(url=WMS_SOLAR, layers="solarpotenzial_dach", fmt="image/png", transparent=True, opacity=0.8, name="Solar", attr="HH", overlay=True).add_to(m_solar)
            st_folium(m_solar, height=500, use_container_width=True, key="solar_view")
        with col_s2:
            st.markdown("🔴 Sehr gut\n🟠 Gut\n🟡 Mittel")

    with tab_info:
        c1, c2 = st.columns(2)
        with c1:
            w = get_weather_data(coords[0], coords[1])
            if w: st.metric("Temp", f"{w['temperature']} °C", f"Wind: {w['windspeed']} km/h")
        with c2:
            st.subheader("Profil")
            st.markdown(f"**{sel_stadt}**")
            st.progress(schule_obj['kess']/6)
            st.caption("KESS")

    with tab_docs:
        q_name = f'"{schule_obj["name"]}" OR "{schule_obj["id"]}"'
        scenarios = [{"Topic": "SEPL", "Q": f'Schulentwicklungsplan "{sel_bez}"'}, {"Topic": "Bau", "Q": f'{q_name} Neubau'}, {"Topic": "Finanzen", "Q": f'{q_name} Zuwendung'}]
        for s in scenarios:
            with st.expander(f"🔎 {s['Topic']}", expanded=False):
                data = query_transparenzportal(s['Q'])
                if data: st.dataframe(pd.DataFrame(extract_docs(data)), hide_index=True)

# --- DEBUGGER ---
with st.expander("🔧 WFS URL Debugger"):
    st.write("Schul-Daten URL:")
    st.code(url_schule)
    st.write("ALKIS-Daten URL (Backup):")
    st.code(url_alkis)
