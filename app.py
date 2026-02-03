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

# --- DIE HOSENTRÄGER-LÖSUNG ---
# 1. WMS (Bild): Zeigt die blaue Fläche IMMER an, egal wo der Pin ist.
WMS_SCHULEN_VISUAL = "https://geodienste.hamburg.de/HH_WMS_Schulimmobilien"

# 2. WFS (Daten): Versucht die Daten abzugreifen (für Klickbarkeit)
# Wir nutzen hier den LIG Dienst, der oft zuverlässiger antwortet
WFS_LIG_URL = "https://geodienste.hamburg.de/HH_WFS_LIG_Grundbesitz"

# Hintergrund
WMS_STADTPLAN = "https://geodienste.hamburg.de/HH_WMS_Stadtplan"
WMS_LAERM = "https://geodienste.hamburg.de/HH_WMS_Strassenlaerm_2017"
WMS_SOLAR = "https://geodienste.hamburg.de/HH_WMS_Solaratlas"
WMS_HOCHWASSER = "https://geodienste.hamburg.de/HH_WMS_Ueberschwemmungsgebiete"
WMS_DENKMAL = "https://geodienste.hamburg.de/HH_WMS_Denkmalkartierung"

# --- 3. HELFER ---
@st.cache_data(show_spinner=False)
def get_coordinates(address_string):
    if not address_string: return None
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address_string, "format": "json", "limit": 1}
    headers = {'User-Agent': 'HH-Schulbau-Monitor-V20/1.0'}
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

# --- WFS LOGIK MIT GRÖSSEREM SUCHRADIUS ---
@st.cache_data(show_spinner=False)
def get_school_property_wfs(lat, lon):
    # WIR VERGRÖSSERN DAS NETZ MASSIV!
    # 0.004 Grad sind ca. 300-400 Meter. Damit fangen wir das Grundstück,
    # auch wenn der Pin auf der Straße davor liegt.
    delta = 0.004 
    
    # BBOX Reihenfolge: Lat, Lon (Standard für WFS 1.1.0/EPSG:4326)
    bbox = f"{lat-delta},{lon-delta},{lat+delta},{lon+delta}" 
    
    params = {
        "SERVICE": "WFS",
        "VERSION": "1.1.0",
        "REQUEST": "GetFeature",
        "TYPENAME": "bsb_sonderverm_schulimmobilien",
        "OUTPUTFORMAT": "application/json",
        "SRSNAME": "EPSG:4326",
        "BBOX": f"{bbox},EPSG:4326"
    }
    
    try:
        r = requests.get(WFS_LIG_URL, params=params, timeout=6)
        if r.status_code == 200:
            return r.json(), r.url
        else:
            return None, r.url
    except Exception as e:
        return None, str(e)

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
st.set_page_config(page_title="HH Schulbau Monitor V20", layout="wide", page_icon="🏫")
st.title("🏫 Hamburger Schulbau-Monitor")

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("Standort")
    bezirke = list(SCHUL_DATEN.keys())
    sel_bez = st.selectbox("Bezirk", bezirke)
    sel_stadt = st.selectbox("Stadtteil", list(SCHUL_DATEN[sel_bez].keys()))
    schule_obj = st.selectbox("Schule", SCHUL_DATEN[sel_bez][sel_stadt], format_func=lambda x: f"{x['name']}")
    
    st.markdown("---")
    st.header("Ebenen")
    
    map_style = st.radio("Hintergrund:", ("Planung (Grau)", "Straßen (OSM)", "Satellit"), index=0)
    
    st.caption("Eigentum (Doppel-Strategie)")
    show_sv_wms = st.checkbox("🟦 Sondervermögen (Bild-Overlay)", value=True, help="Zeigt die blaue Fläche immer an (WMS).")
    show_sv_wfs = st.checkbox("✒️ Sondervermögen (Interaktiv)", value=True, help="Versucht, die Fläche klickbar zu machen (WFS).")
    
    st.caption("Planung")
    show_alkis = st.checkbox("📐 Kataster-Plan (ALKIS)", value=True)
    show_radius = st.checkbox("⭕ 1km Radius", value=False)
    
    st.caption("Umwelt")
    show_transit = st.checkbox("🚆 ÖPNV", value=True)
    show_laerm = st.checkbox("🔊 Straßenlärm", value=False)
    show_hochwasser = st.checkbox("🌊 Hochwasser", value=False)
    show_denkmal = st.checkbox("🏛️ Denkmalschutz", value=False)
    
    if st.button("Reset"): st.cache_data.clear(); st.rerun()

# --- 6. MAIN ---
if schule_obj:
    coords = get_coordinates(schule_obj["address"])
    if not coords: coords = [53.550, 9.992]; st.warning("Fallback Koordinaten.")

    # VERSUCH: Vektordaten mit großem Netz
    geo_sv, debug_url = get_school_property_wfs(coords[0], coords[1])
    
    sv_hits = 0
    if geo_sv and 'features' in geo_sv:
        sv_hits = len(geo_sv['features'])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Bezirk", sel_bez)
    c2.metric("Schüler", schule_obj["students"])
    
    # Status
    if sv_hits > 0:
        c3.metric("Interaktive Daten", "✅ Geladen")
    else:
        c3.metric("Interaktive Daten", "⚠️ Nur Bild-Overlay")
        
    c4.metric("KESS", schule_obj["kess"])
    
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

        # STRATEGIE 1: WMS (Bild) - Das Sicherheitsnetz!
        if show_sv_wms:
            folium.WmsTileLayer(
                url=WMS_SCHULEN_VISUAL,
                layers="bsb_sonderverm_schulimmobilien", # Layer Name für WMS
                fmt="image/png",
                transparent=True,
                name="Sondervermögen (Bild)",
                attr="Geoportal Hamburg",
                overlay=True,
                opacity=0.6 # Leicht transparentes Blau
            ).add_to(m)

        # STRATEGIE 2: WFS (Vektor) - Wenn verfügbar, drüberlegen für Tooltip
        if show_sv_wfs and sv_hits > 0:
            folium.GeoJson(
                geo_sv,
                name="Sondervermögen (Interaktiv)",
                style_function=lambda x: {'fillColor': 'blue', 'color': 'navy', 'weight': 2, 'fillOpacity': 0.1}, # Fast durchsichtig, da WMS drunter liegt
                tooltip=folium.GeoJsonTooltip(fields=['flurstueckskennzeichen'], aliases=['Flurstück:'], localize=True)
            ).add_to(m)

        # Kataster Backup
        if show_alkis:
            folium.WmsTileLayer(
                url=WMS_STADTPLAN, layers="schwarzweiss", fmt="image/png", transparent=True, 
                name="Kataster", attr="HH", overlay=True, opacity=0.7
            ).add_to(m)

        # Overlays
        if show_transit:
            folium.TileLayer(tiles="https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png", attr="OpenRailwayMap", overlay=True).add_to(m)
        if show_laerm:
            folium.WmsTileLayer(url=WMS_LAERM, layers="laerm_str_lden", fmt="image/png", transparent=True, opacity=0.5, name="Lärm", attr="HH", overlay=True).add_to(m)
        if show_hochwasser:
             folium.WmsTileLayer(url=WMS_HOCHWASSER, layers="ueberschwemmungsgebiete", fmt="image/png", transparent=True, opacity=0.5, name="Hochwasser", attr="HH", overlay=True).add_to(m)
        if show_denkmal:
            folium.WmsTileLayer(url=WMS_DENKMAL, layers="dk_denkmal_flaeche", fmt="image/png", transparent=True, opacity=0.6, name="Denkmal", attr="HH", overlay=True).add_to(m)

        if show_radius:
            folium.Circle(radius=1000, location=coords, color="#3186cc", fill=True, fill_opacity=0.05).add_to(m)

        folium.Marker(coords, popup=schule_obj["name"], icon=folium.Icon(color="red", icon="graduation-cap", prefix="fa")).add_to(m)
        
        st_folium(m, height=650, use_container_width=True, key=f"map_v20_{schule_obj['id']}_{map_style}_{show_sv_wms}")
        
        # Erklärung
        if show_sv_wms:
            st.info("ℹ️ Die **blau-lila gefärbten Flächen** zeigen das amtliche Sondervermögen Schulimmobilien (via WMS).")

    # --- TAB 2: SOLAR ---
    with tab_solar:
        col_s1, col_s2 = st.columns([3,1])
        with col_s1:
            m_solar = folium.Map(location=coords, zoom_start=19, tiles="cartodbpositron")
            folium.TileLayer(tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr="Esri", overlay=False).add_to(m_solar)
            folium.WmsTileLayer(url=WMS_SOLAR, layers="solarpotenzial_dach", fmt="image/png", transparent=True, opacity=0.8, name="Solar", attr="HH", overlay=True).add_to(m_solar)
            st_folium(m_solar, height=500, use_container_width=True, key="solar_view")
        with col_s2:
            st.markdown("🔴 Sehr gut\n🟠 Gut\n🟡 Mittel")

    # --- TAB 3: UMFELD ---
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

    # --- TAB 4: AKTEN ---
    with tab_docs:
        q_name = f'"{schule_obj["name"]}" OR "{schule_obj["id"]}"'
        scenarios = [{"Topic": "SEPL", "Q": f'Schulentwicklungsplan "{sel_bez}"'}, {"Topic": "Bau", "Q": f'{q_name} Neubau'}, {"Topic": "Finanzen", "Q": f'{q_name} Zuwendung'}]
        for s in scenarios:
            with st.expander(f"🔎 {s['Topic']}", expanded=False):
                data = query_transparenzportal(s['Q'])
                if data: st.dataframe(pd.DataFrame(extract_docs(data)), hide_index=True)
