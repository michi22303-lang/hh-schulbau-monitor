import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
import json

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

# --- 2. APIs & DIENSTE ---
API_URL_TRANSPARENZ = "https://suche.transparenz.hamburg.de/api/3/action/package_search"
API_URL_WEATHER = "https://api.open-meteo.com/v1/forecast"

# WFS (Vektordaten für Gebäude-Auswahl)
WFS_ALKIS_SIMPLE = "https://geodienste.hamburg.de/WFS_HH_ALKIS_vereinfacht"

# WMS (Hintergrundbilder & Overlays)
WMS_STADTPLAN = "https://geodienste.hamburg.de/HH_WMS_Stadtplan"
WMS_ALKIS_BILD = "https://geodienste.hamburg.de/HH_WMS_ALKIS" # Spezieller Bild-Dienst für ALKIS
WMS_SOLAR = "https://geodienste.hamburg.de/HH_WMS_Solaratlas"
WMS_LAERM = "https://geodienste.hamburg.de/HH_WMS_Strassenlaerm_2017"
WMS_HOCHWASSER = "https://geodienste.hamburg.de/HH_WMS_Ueberschwemmungsgebiete"
WMS_DENKMAL = "https://geodienste.hamburg.de/HH_WMS_Denkmalkartierung"

# --- 3. HELFER ---
@st.cache_data(show_spinner=False)
def get_coordinates(address_string):
    if not address_string: return None
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address_string, "format": "json", "limit": 1}
    headers = {'User-Agent': 'HH-Schulbau-Monitor-V25/1.0'}
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

# --- GEBÄUDE DATEN LADEN (ROBUST) ---
@st.cache_data(show_spinner=False)
def get_buildings_robust(lat, lon):
    # Radius ca. 200m
    delta = 0.002
    
    # STRATEGIE A: WFS 1.1.0 mit Lat, Lon
    bbox_a = f"{lat-delta},{lon-delta},{lat+delta},{lon+delta}"
    
    params = {
        "SERVICE": "WFS",
        "VERSION": "1.1.0",         
        "REQUEST": "GetFeature",
        "TYPENAME": "alkis_gebaeude", 
        "OUTPUTFORMAT": "json",     
        "SRSNAME": "EPSG:4326",
        "BBOX": f"{bbox_a},EPSG:4326"
    }
    
    debug_log = []
    
    try:
        r = requests.get(WFS_ALKIS_SIMPLE, params=params, timeout=6)
        if r.status_code == 200:
            data = r.json()
            if data and "features" in data and len(data["features"]) > 0:
                return data, debug_log
    except Exception as e:
        debug_log.append(f"A failed: {str(e)}")

    # STRATEGIE B: WFS 1.0.0 mit Lon, Lat (Fallback)
    bbox_b = f"{lon-delta},{lat-delta},{lon+delta},{lat+delta}"
    params["VERSION"] = "1.0.0"
    params["BBOX"] = bbox_b 
    
    try:
        r = requests.get(WFS_ALKIS_SIMPLE, params=params, timeout=6)
        if r.status_code == 200:
            data = r.json()
            if data and "features" in data and len(data["features"]) > 0:
                return data, debug_log
    except Exception as e:
        debug_log.append(f"B failed: {str(e)}")

    return None, debug_log

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
st.set_page_config(page_title="HH Schulbau Monitor V25", layout="wide", page_icon="🏫")
st.title("🏫 Hamburger Schulbau-Monitor")

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("1. Standort")
    bezirke = list(SCHUL_DATEN.keys())
    sel_bez = st.selectbox("Bezirk", bezirke)
    sel_stadt = st.selectbox("Stadtteil", list(SCHUL_DATEN[sel_bez].keys()))
    schule_obj = st.selectbox("Schule", SCHUL_DATEN[sel_bez][sel_stadt], format_func=lambda x: f"{x['name']}")
    
    # Koordinaten
    coords = get_coordinates(schule_obj["address"])
    if not coords: coords = [53.550, 9.992]

    st.markdown("---")
    st.header("2. Gebäude-Auswahl")
    
    # Gebäude laden
    geo_buildings, debug_info = get_buildings_robust(coords[0], coords[1])
    
    selected_building_id = None
    if geo_buildings and "features" in geo_buildings:
        b_options = []
        for f in geo_buildings["features"]:
            props = f.get("properties", {})
            bid = f.get("id")
            nutzung = props.get("gebaeudefunktion_bezeichnung", "Gebäude") or "Gebäude"
            b_options.append({"label": f"{nutzung} ({bid})", "id": bid})
            
        sel = st.selectbox("Gebäude hervorheben:", b_options, format_func=lambda x: x["label"])
        selected_building_id = sel["id"]
        st.caption(f"{len(b_options)} Gebäude im Umkreis erkannt.")
    else:
        st.warning("Keine Gebäudedaten.")

    st.markdown("---")
    st.header("3. Karten-Layer")
    
    map_style = st.radio("Hintergrund:", ("Planung (Grau)", "Straßen (OSM)", "Satellit"), index=0)
    
    st.caption("Basis-Daten")
    show_alkis_plan = st.checkbox("⬛ Flurstücke & Nummern", value=True, help="Zeigt den Katasterplan mit Grundstücksgrenzen")
    show_radius = st.checkbox("⭕ 1km Radius", value=False)
    
    st.caption("Fach-Overlays")
    show_transit = st.checkbox("🚆 ÖPNV & Bahn", value=True)
    show_laerm = st.checkbox("🔊 Straßenlärm", value=False)
    show_hochwasser = st.checkbox("🌊 Hochwasser", value=False)
    show_denkmal = st.checkbox("🏛️ Denkmalschutz", value=False)
    
    if st.button("Reset"): st.cache_data.clear(); st.rerun()

# --- 6. MAIN ---
if schule_obj:
    c1, c2, c3 = st.columns(3)
    c1.metric("Bezirk", sel_bez)
    c2.metric("Schüler", schule_obj["students"])
    
    cnt = len(geo_buildings['features']) if (geo_buildings and 'features' in geo_buildings) else 0
    c3.metric("Gebäude-Vektoren", cnt)
    
    st.markdown("---")
    
    tab_map, tab_solar, tab_info, tab_docs = st.tabs(["🗺️ Karte & Analyse", "☀️ Solarpotenzial", "📊 Umfeld", "📂 Akten"])

    with tab_map:
        # Basis
        if map_style == "Straßen (OSM)":
            m = folium.Map(location=coords, zoom_start=19, tiles="OpenStreetMap")
        elif map_style == "Satellit":
            m = folium.Map(location=coords, zoom_start=19, tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr="Esri")
            folium.TileLayer(tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", attr="Esri Ref", overlay=True, name="Labels").add_to(m)
        else:
            m = folium.Map(location=coords, zoom_start=19, tiles="cartodbpositron", attr="CartoDB")

        # 1. GEBÄUDE VEKTOREN (Grau)
        if geo_buildings and "features" in geo_buildings:
            folium.GeoJson(
                geo_buildings,
                name="Alle Gebäude",
                style_function=lambda x: {'fillColor': '#999999', 'color': '#444444', 'weight': 1, 'fillOpacity': 0.2},
                tooltip=folium.GeoJsonTooltip(fields=['gebaeudefunktion_bezeichnung'], aliases=['Typ:'], localize=True)
            ).add_to(m)

        # 2. GEBÄUDE HIGHLIGHT (Rot)
        if geo_buildings and selected_building_id:
            feats = geo_buildings["features"]
            target = next((f for f in feats if f.get("id") == selected_building_id), None)
            if target:
                folium.GeoJson(
                    target,
                    name="Auswahl",
                    style_function=lambda x: {'fillColor': '#ff0000', 'color': 'red', 'weight': 3, 'fillOpacity': 0.6},
                    tooltip="Ausgewählt"
                ).add_to(m)

        # 3. FLURSTÜCKE (ALKIS PLAN)
        if show_alkis_plan:
            folium.WmsTileLayer(
                url=WMS_STADTPLAN, 
                layers="schwarzweiss", # Das ist der Layer, der Flurstücke und Nummern enthält
                fmt="image/png", 
                transparent=True, 
                name="Flurstücke", 
                attr="Geoportal Hamburg", 
                overlay=True, 
                opacity=0.6
            ).add_to(m)

        # 4. OVERLAYS (Alle wieder da!)
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
        
        st_folium(m, height=650, use_container_width=True, key=f"map_v25_{selected_building_id}_{show_alkis_plan}")

    with tab_solar:
        col_s1, col_s2 = st.columns([3,1])
        with col_s1:
            m_solar = folium.Map(location=coords, zoom_start=19, tiles="cartodbpositron")
            folium.TileLayer(tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr="Esri", overlay=False).add_to(m_solar)
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
