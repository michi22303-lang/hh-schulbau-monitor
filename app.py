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

# HIER IST DIE URL FÜR DAS SONDERVERMÖGEN (OGC API)
# Basierend auf Ihrem Fund: "bsb_sonderverm_schulimmobilien"
API_OGC_SCHULE = "https://api.hamburg.de/datasets/v1/bsb_sonderverm_schulimmobilien/collections/bsb_sonderverm_schulimmobilien/items"

# WMS Dienste (Alle wieder da!)
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
    headers = {'User-Agent': 'HH-Schulbau-Monitor-V19/1.0'}
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

# --- NEU: OGC API MIT KORREKTER BBOX (Lon, Lat) ---
@st.cache_data(show_spinner=False)
def get_sondervermoegen_data(lat, lon):
    # OGC API Items erwartet oft BBOX=minLon,minLat,maxLon,maxLat
    # Ihr vorheriger Fehler deutete auf vertauschte Achsen hin.
    delta = 0.0025 # ca 250m Suchradius
    
    # REIHENFOLGE: LON, LAT (nicht Lat, Lon)
    bbox = f"{lon-delta},{lat-delta},{lon+delta},{lat+delta}"
    
    params = {
        "bbox": bbox,
        "limit": 5,
        "f": "json"
    }
    
    try:
        r = requests.get(API_OGC_SCHULE, params=params, timeout=5)
        if r.status_code == 200:
            return r.json()
    except:
        return None
    return None

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
st.set_page_config(page_title="HH Schulbau Monitor V19", layout="wide", page_icon="🏫")
st.title("🏫 Hamburger Schulbau-Monitor")

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("Standort")
    bezirke = list(SCHUL_DATEN.keys())
    sel_bez = st.selectbox("Bezirk", bezirke)
    sel_stadt = st.selectbox("Stadtteil", list(SCHUL_DATEN[sel_bez].keys()))
    schule_obj = st.selectbox("Schule", SCHUL_DATEN[sel_bez][sel_stadt], format_func=lambda x: f"{x['name']}")
    
    st.markdown("---")
    st.header("Karten-Ebenen")
    
    map_style = st.radio("Hintergrund:", ("Planung (Grau)", "Straßen (OSM)", "Satellit"), index=0)
    
    st.caption("Eigentum & Grenzen")
    # Umbenannt für Korrektheit!
    show_sondervermoegen = st.checkbox("🟦 Sondervermögen Schulimmobilien", value=True, help="Lädt die amtlichen Flächen der SBH via OGC API")
    show_alkis = st.checkbox("⬛ Kataster-Plan (ALKIS)", value=True, help="Zeigt Grundstücksgrenzen und Hausnummern (Bild)")
    
    st.caption("Analyse-Layer (Wieder da!)")
    show_transit = st.checkbox("🚆 ÖPNV & Bahn", value=True)
    show_laerm = st.checkbox("🔊 Straßenlärm (Lden)", value=False)
    show_hochwasser = st.checkbox("🌊 Hochwasser-Risiko", value=False)
    show_denkmal = st.checkbox("🏛️ Denkmalschutz", value=False)
    show_radius = st.checkbox("⭕ 1km Einzugsgebiet", value=False)
    
    if st.button("Reset"): st.cache_data.clear(); st.rerun()

# --- 6. MAIN ---
if schule_obj:
    coords = get_coordinates(schule_obj["address"])
    if not coords: coords = [53.550, 9.992]; st.warning("Fallback Koordinaten.")

    # Daten laden (Sondervermögen)
    geo_sv = get_sondervermoegen_data(coords[0], coords[1])
    
    sv_hits = 0
    if geo_sv and 'features' in geo_sv:
        sv_hits = len(geo_sv['features'])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Bezirk", sel_bez)
    c2.metric("Schüler", schule_obj["students"])
    
    # Statusanzeige für das Sondervermögen
    if sv_hits > 0:
        c3.metric("Status Sondervermögen", "✅ Gefunden")
    else:
        c3.metric("Status Sondervermögen", "⚠️ Nicht im Index")
        
    c4.metric("Koordinate", f"{coords[0]:.4f}, {coords[1]:.4f}")
    
    st.markdown("---")
    
    tab_map, tab_solar, tab_info, tab_docs = st.tabs(["🗺️ Karte & Analyse", "☀️ Solarpotenzial", "📊 Umfeld", "📂 Akten"])

    with tab_map:
        # 1. Basis-Karte
        if map_style == "Straßen (OSM)":
            m = folium.Map(location=coords, zoom_start=18, tiles="OpenStreetMap")
        elif map_style == "Satellit":
            m = folium.Map(location=coords, zoom_start=18, tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr="Esri")
            folium.TileLayer(tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", attr="Esri Ref", overlay=True, name="Labels").add_to(m)
        else:
            m = folium.Map(location=coords, zoom_start=18, tiles="cartodbpositron", attr="CartoDB")

        # 2. Sondervermögen (Vektor)
        if show_sondervermoegen and sv_hits > 0:
            folium.GeoJson(
                geo_sv,
                name="Sondervermögen Schulimmobilien",
                style_function=lambda x: {'fillColor': '#0033cc', 'color': '#0033cc', 'weight': 3, 'fillOpacity': 0.4},
                tooltip=folium.GeoJsonTooltip(fields=['id'], aliases=['Objekt ID:'])
            ).add_to(m)

        # 3. ALKIS (Bild) - Backup für Grenzen
        if show_alkis:
            folium.WmsTileLayer(
                url=WMS_STADTPLAN, layers="schwarzweiss", fmt="image/png", transparent=True, 
                name="Kataster", attr="Geoportal HH", overlay=True, opacity=0.7
            ).add_to(m)

        # 4. OVERLAYS (Alle wieder eingebaut!)
        if show_transit:
            folium.TileLayer(tiles="https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png", attr="OpenRailwayMap", overlay=True).add_to(m)
            
        if show_laerm:
            folium.WmsTileLayer(url=WMS_LAERM, layers="laerm_str_lden", fmt="image/png", transparent=True, opacity=0.5, name="Lärm", attr="HH", overlay=True).add_to(m)

        if show_hochwasser:
            folium.WmsTileLayer(url=WMS_HOCHWASSER, layers="ueberschwemmungsgebiete", fmt="image/png", transparent=True, opacity=0.5, name="Hochwasser", attr="HH", overlay=True).add_to(m)

        if show_denkmal:
            folium.WmsTileLayer(url=WMS_DENKMAL, layers="dk_denkmal_flaeche,dk_denkmal_punkt", fmt="image/png", transparent=True, name="Denkmal", attr="HH", overlay=True).add_to(m)

        if show_radius:
            folium.Circle(radius=1000, location=coords, color="#3186cc", fill=True, fill_opacity=0.05).add_to(m)

        # Marker
        folium.Marker(coords, popup=schule_obj["name"], icon=folium.Icon(color="red", icon="graduation-cap", prefix="fa")).add_to(m)
        
        st_folium(m, height=650, use_container_width=True, key=f"map_v19_{schule_obj['id']}_{map_style}_{show_sondervermoegen}")
        
        # Info falls Sondervermögen leer
        if show_sondervermoegen and sv_hits == 0:
            st.toast("Kein Eintrag im 'Sondervermögen'-Datensatz an dieser Koordinate gefunden. Nutzen Sie den Kataster-Plan zur Orientierung.", icon="ℹ️")


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
