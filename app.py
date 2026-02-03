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

# DER GEHEIMTIPP: WFS "Vereinfacht" (Viel robuster!)
WFS_ALKIS_SIMPLE = "https://geodienste.hamburg.de/WFS_HH_ALKIS_vereinfacht"

# Hintergrund-Bilder (WMS)
WMS_STADTPLAN = "https://geodienste.hamburg.de/HH_WMS_Stadtplan"
WMS_SOLAR = "https://geodienste.hamburg.de/HH_WMS_Solaratlas"
WMS_LAERM = "https://geodienste.hamburg.de/HH_WMS_Strassenlaerm_2017"

# --- 3. HELFER ---
@st.cache_data(show_spinner=False)
def get_coordinates(address_string):
    if not address_string: return None
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address_string, "format": "json", "limit": 1}
    headers = {'User-Agent': 'HH-Schulbau-Monitor-V23/1.0'}
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

# --- NEU: GEBÄUDE LADEN (ROBUST) ---
@st.cache_data(show_spinner=False)
def get_buildings_robust(lat, lon):
    # Suchradius
    delta = 0.002
    
    # TRICK: Wir probieren BEIDE Reihenfolgen für die Bounding Box.
    # WFS Server sind manchmal unberechenbar, so fangen wir alles ab.
    
    # Versuch 1: Lon, Lat (Standard für viele WFS 1.1)
    bbox_1 = f"{lon-delta},{lat-delta},{lon+delta},{lat+delta}"
    
    params = {
        "SERVICE": "WFS",
        "VERSION": "1.1.0",         # 1.1.0 ist robuster als 2.0
        "REQUEST": "GetFeature",
        "TYPENAME": "alkis_gebaeude", # Layer Name im vereinfachten Dienst
        "OUTPUTFORMAT": "json",     # Format "json" (nicht application/geo+json)
        "SRSNAME": "EPSG:4326",
        "BBOX": f"{bbox_1},EPSG:4326"
    }
    
    debug_url = ""
    try:
        req = requests.Request('GET', WFS_ALKIS_SIMPLE, params=params)
        prep = req.prepare()
        debug_url = prep.url # Für Debugger
        
        r = requests.Session().send(prep, timeout=8)
        
        if r.status_code == 200:
            data = r.json()
            # Check: Haben wir Features?
            if data and "features" in data and len(data["features"]) > 0:
                return data, debug_url
            else:
                # Versuch 2: Lat, Lon (Falls Server andersrum tickt)
                bbox_2 = f"{lat-delta},{lon-delta},{lat+delta},{lon+delta}"
                params["BBOX"] = f"{bbox_2},EPSG:4326"
                r2 = requests.get(WFS_ALKIS_SIMPLE, params=params, timeout=8)
                if r2.status_code == 200:
                    return r2.json(), r2.url
        
        return None, debug_url
    except Exception as e:
        return None, f"{str(e)} | {debug_url}"

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
st.set_page_config(page_title="HH Schulbau Monitor V23", layout="wide", page_icon="🏫")
st.title("🏫 Hamburger Schulbau-Monitor")

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("1. Standort")
    bezirke = list(SCHUL_DATEN.keys())
    sel_bez = st.selectbox("Bezirk", bezirke)
    sel_stadt = st.selectbox("Stadtteil", list(SCHUL_DATEN[sel_bez].keys()))
    schule_obj = st.selectbox("Schule", SCHUL_DATEN[sel_bez][sel_stadt], format_func=lambda x: f"{x['name']}")
    
    coords = get_coordinates(schule_obj["address"])
    if not coords: coords = [53.550, 9.992]

    st.markdown("---")
    st.header("2. Gebäude-Selektor")
    
    # Gebäude laden
    geo_buildings, debug_url = get_buildings_robust(coords[0], coords[1])
    
    selected_building_id = None
    
    if geo_buildings and "features" in geo_buildings and len(geo_buildings["features"]) > 0:
        buildings_list = []
        for feat in geo_buildings["features"]:
            props = feat.get("properties", {})
            b_id = feat.get("id")
            
            # Nutzung auslesen (oft 'gebaeudefunktion_bezeichnung' oder 'nutzungsart')
            nutzung = props.get("gebaeudefunktion_bezeichnung", "Gebäude")
            if not nutzung: nutzung = "Gebäude"
            
            label = f"{nutzung} ({b_id})"
            buildings_list.append({"label": label, "id": b_id})
            
        st.success(f"{len(buildings_list)} Gebäude gefunden!")
        sel_b_obj = st.selectbox("Wähle Gebäude:", buildings_list, format_func=lambda x: x["label"])
        selected_building_id = sel_b_obj["id"]
    else:
        st.warning("Keine Gebäude gefunden.")
        
    st.markdown("---")
    st.header("3. Layer")
    map_style = st.radio("Hintergrund:", ("Planung (Grau)", "Straßen (OSM)", "Satellit"), index=0)
    show_alkis_img = st.checkbox("⬛ Kataster (Bild)", value=True)
    if st.button("Reset"): st.cache_data.clear(); st.rerun()

# --- 6. MAIN ---
if schule_obj:
    c1, c2, c3 = st.columns(3)
    c1.metric("Bezirk", sel_bez)
    c2.metric("Schüler", schule_obj["students"])
    
    if geo_buildings and "features" in geo_buildings:
        c3.metric("Gebäude im Radius", len(geo_buildings['features']))
    else:
        c3.metric("Gebäude", "0")
    
    st.markdown("---")
    
    tab_map, tab_solar, tab_info, tab_docs = st.tabs(["🗺️ Gebäude & Analyse", "☀️ Solarpotenzial", "📊 Umfeld", "📂 Akten"])

    with tab_map:
        if map_style == "Straßen (OSM)":
            m = folium.Map(location=coords, zoom_start=19, tiles="OpenStreetMap")
        elif map_style == "Satellit":
            m = folium.Map(location=coords, zoom_start=19, tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr="Esri")
            folium.TileLayer(tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", attr="Esri Ref", overlay=True, name="Labels").add_to(m)
        else:
            m = folium.Map(location=coords, zoom_start=19, tiles="cartodbpositron", attr="CartoDB")

        # 1. ALLE GEBÄUDE (Grau)
        if geo_buildings and "features" in geo_buildings:
            folium.GeoJson(
                geo_buildings,
                name="Alle Gebäude",
                style_function=lambda x: {
                    'fillColor': '#666666', 'color': 'black', 'weight': 1, 'fillOpacity': 0.2
                },
                tooltip=folium.GeoJsonTooltip(fields=['gebaeudefunktion_bezeichnung'], aliases=['Typ:'], localize=True)
            ).add_to(m)

        # 2. HIGHLIGHT (Rot)
        if geo_buildings and selected_building_id:
            highlight_feat = [f for f in geo_buildings["features"] if f.get("id") == selected_building_id]
            if highlight_feat:
                folium.GeoJson(
                    highlight_feat[0],
                    name="Auswahl",
                    style_function=lambda x: {'fillColor': '#ff0000', 'color': '#ff0000', 'weight': 3, 'fillOpacity': 0.6},
                    tooltip="Auswahl"
                ).add_to(m)

        if show_alkis_img:
            folium.WmsTileLayer(
                url=WMS_STADTPLAN, layers="schwarzweiss", fmt="image/png", transparent=True, 
                name="Kataster Bild", attr="HH", overlay=True, opacity=0.5
            ).add_to(m)

        folium.Marker(coords, popup=schule_obj["name"], icon=folium.Icon(color="red", icon="graduation-cap", prefix="fa")).add_to(m)
        
        # KEY = Refresh trigger
        st_folium(m, height=600, use_container_width=True, key=f"map_v23_{selected_building_id}")

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

with st.expander("🔧 Tech-Debugger"):
    st.write(debug_url)
    if not geo_buildings: st.error("Keine Daten.")
