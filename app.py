import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
import wikipedia

# --- 1. DATENBASIS ---
SCHUL_DATEN = {
    "Altona": {
        "Othmarschen": [
            {"name": "Gymnasium Hochrad", "id": "5887", "students": "ca. 950", "address": "Hochrad 2, 22605 Hamburg"} 
        ]
    },
    "Bergedorf": {
        "Kirchwerder": [
            {"name": "Schule Zollenspieker", "id": "5648", "students": "ca. 230", "address": "Kirchwerder Landweg 558, 21037 Hamburg"}
        ]
    },
    "Mitte": {
        "Billstedt": [
            {"name": "Grundschule Mümmelmannsberg", "id": "5058", "students": "ca. 340", "address": "Mümmelmannsberg 52, 22115 Hamburg"}
        ]
    }
}

# --- 2. API URLs ---
API_URL_TRANSPARENZ = "https://suche.transparenz.hamburg.de/api/3/action/package_search"

# WMS DIENSTE (Geodienste Hamburg)
WMS_ALKIS = "https://geodienste.hamburg.de/HH_WMS_ALKIS"
WMS_DENKMAL = "https://geodienste.hamburg.de/HH_WMS_Denkmalkartierung"
WMS_LAERM = "https://geodienste.hamburg.de/HH_WMS_Strassenlaerm_2017" # Lärmkarten
WMS_HOCHWASSER = "https://geodienste.hamburg.de/HH_WMS_Ueberschwemmungsgebiete"

# --- 3. HELFER ---
@st.cache_data(show_spinner=False)
def get_coordinates(address_string):
    if not address_string: return None
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address_string, "format": "json", "limit": 1}
    headers = {'User-Agent': 'HH-Schulbau-Monitor-V10/1.0'}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        data = response.json()
        if data:
            return [float(data[0]["lat"]), float(data[0]["lon"])]
    except: return None
    return None

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

@st.cache_data
def get_wiki_summary(term):
    wikipedia.set_lang("de")
    try:
        # Versuche eine Zusammenfassung zu finden
        return wikipedia.summary(term, sentences=3)
    except:
        return "Keine Wikipedia-Daten verfügbar."

# --- 4. UI SETUP ---
st.set_page_config(page_title="HH Schulbau Monitor V10", layout="wide", page_icon="🏫")
st.title("🏫 Hamburger Schulbau-Monitor")

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("1. Standort-Wahl")
    bezirke = list(SCHUL_DATEN.keys())
    selected_bezirk = st.selectbox("Bezirk", bezirke)
    stadtteile = list(SCHUL_DATEN[selected_bezirk].keys())
    selected_stadtteil = st.selectbox("Stadtteil", stadtteile)
    schulen_liste = SCHUL_DATEN[selected_bezirk][selected_stadtteil]
    schule_obj = st.selectbox("Schule", schulen_liste, format_func=lambda x: f"{x['name']} ({x['id']})")
    
    st.markdown("---")
    
    st.header("2. Karten-Layer")
    
    # A) Hintergrundkarte
    st.caption("🗺️ Basis")
    map_style = st.radio(
        "Stil:",
        ("Straßen (OSM)", "Satellit (Hybrid)", "Grau (Planung)"),
        label_visibility="collapsed"
    )
    
    # B) Overlays
    st.caption("🏗️ Fachdaten (Overlays)")
    show_alkis = st.checkbox("📐 Kataster (ALKIS)", value=True, help="Grundstücksgrenzen & Hausnummern")
    show_denkmal = st.checkbox("🏛️ Denkmalschutz", value=False, help="Denkmalgeschützte Gebäude (Rot/Schraffiert)")
    show_laerm = st.checkbox("🔊 Straßenlärm (Tag/Nacht)", value=False, help="Lärmkartierung (Lden)")
    show_flood = st.checkbox("🌊 Hochwasser-Risiko", value=False, help="Überschwemmungsgebiete")
    
    st.caption("📍 Orientierung")
    show_transit = st.checkbox("🚆 ÖPNV / Bahn", value=False)
    show_radius = st.checkbox("⭕ 1km Einzugsgebiet", value=False)
    
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

    # Header mit Wikipedia Info
    col1, col2 = st.columns([2, 1])
    with col1:
        c1, c2, c3 = st.columns(3)
        c1.metric("Schülerzahl", schule_obj.get('students', '-'))
        c2.metric("Kennziffer", schule_obj.get('id', '-'))
        c3.metric("Bezirk", selected_bezirk)
        st.markdown(f"**Adresse:** {adresse}")
        
        # Externe Links (Quick Actions)
        st.markdown("##### 🚀 Externe Ansichten")
        cl_a, cl_b, cl_c = st.columns(3)
        # Google Earth Link Generator
        g_earth_url = f"https://earth.google.com/web/search/{coords[0]},{coords[1]}"
        g_maps_url = f"https://www.google.com/maps/search/?api=1&query={coords[0]},{coords[1]}"
        g_news_url = f"https://www.google.com/search?q={schule_obj['name']}+Hamburg&tbm=nws"
        
        cl_a.link_button("🌍 3D Google Earth", g_earth_url)
        cl_b.link_button("🗺️ Google Maps", g_maps_url)
        cl_c.link_button("📰 News Suche", g_news_url)

    with col2:
        # Wikipedia Kontext box
        with st.container(border=True):
            st.caption(f"Info: {selected_stadtteil}")
            st.markdown(f"_{get_wiki_summary(selected_stadtteil + ' Hamburg')}_")

    st.markdown("---")

    # TABS
    tab_map, tab_docs = st.tabs(["🗺️ Profi-Karte", "📂 Dokumente & Analysen"])

    # --- TAB 1: KARTE ---
    with tab_map:
        # Basis Karte
        if map_style == "Straßen (OSM)":
            m = folium.Map(location=coords, zoom_start=18, tiles="OpenStreetMap")
        elif map_style == "Satellit (Hybrid)":
            m = folium.Map(location=coords, zoom_start=18, tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr="Esri")
            folium.TileLayer(tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", attr="Esri Ref", overlay=True, name="Labels").add_to(m)
        else:
            m = folium.Map(location=coords, zoom_start=18, tiles="cartodbpositron", attr="CartoDB")

        # --- FACH-OVERLAYS ---
        
        # 1. ALKIS
        if show_alkis:
            folium.WmsTileLayer(url=WMS_ALKIS, layers="alkis_flurstuecke,alkis_gebaeude", fmt="image/png", transparent=True, name="ALKIS", attr="Geoportal HH", overlay=True).add_to(m)

        # 2. Denkmalschutz (Neu)
        if show_denkmal:
            folium.WmsTileLayer(
                url=WMS_DENKMAL,
                layers="dk_denkmal_flaeche,dk_denkmal_punkt", # Flächen und Punkte
                fmt="image/png",
                transparent=True,
                name="Denkmalschutz",
                attr="Geoportal HH",
                overlay=True
            ).add_to(m)

        # 3. Lärmkataster (Neu) - Lden (24h Lärmindex)
        if show_laerm:
            folium.WmsTileLayer(
                url=WMS_LAERM,
                layers="laerm_str_lden", # Layer für 24h Lärm
                fmt="image/png",
                transparent=True,
                opacity=0.6, # Leicht transparent, damit man die Karte drunter sieht
                name="Lärmkataster",
                attr="Geoportal HH",
                overlay=True
            ).add_to(m)
            
        # 4. Hochwasser (Neu)
        if show_flood:
            folium.WmsTileLayer(
                url=WMS_HOCHWASSER,
                layers="ueberschwemmungsgebiete", 
                fmt="image/png",
                transparent=True,
                opacity=0.5,
                name="Hochwasser",
                attr="Geoportal HH",
                overlay=True
            ).add_to(m)

        # Standard Overlays
        if show_transit:
            folium.TileLayer(tiles="https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png", attr="OpenRailwayMap", overlay=True).add_to(m)
        if show_radius:
            folium.Circle(radius=1000, location=coords, color="#3186cc", fill=True, fill_opacity=0.1).add_to(m)

        # Marker
        folium.Marker(coords, popup=schule_obj['name'], icon=folium.Icon(color="red", icon="graduation-cap", prefix="fa")).add_to(m)

        # Legende
        st_folium(m, height=700, use_container_width=True, key=f"m_{schule_obj['id']}_{map_style}_{show_laerm}_{show_denkmal}")
        
        # Legenden-Erklärung (Statisch, da WMS Legenden Bilder sind)
        if show_laerm: st.caption("🔴 Lärm-Legende: Rot/Lila = Hohe Lärmbelastung (> 65 dB)")
        if show_denkmal: st.caption("🏛️ Denkmal-Legende: Schraffierte Flächen stehen unter Denkmalschutz.")

    # --- TAB 2: DOKUMENTE ---
    with tab_docs:
        schul_query = f'"{schule_obj["name"]}" OR "{schule_obj["id"]}"'
        search_scenarios = [
            {"Icon": "📜", "Topic": "Schulentwicklungsplan", "Query": f'Schulentwicklungsplan "{selected_bezirk}"'},
            {"Icon": "🏗️", "Topic": "Bau & Sanierung", "Query": f'{schul_query} Neubau OR Sanierung'},
            {"Icon": "⚖️", "Topic": "Bebauungspläne", "Query": f'Bebauungsplan "{selected_stadtteil}"'},
            {"Icon": "💶", "Topic": "Zuwendungen & Finanzen", "Query": f'{schul_query} Zuwendung'} # Neu: Finanzen
        ]
        
        for scenario in search_scenarios:
            with st.expander(f"{scenario['Icon']} {scenario['Topic']}", expanded=False):
                with st.spinner("Suche..."):
                    raw = query_transparenzportal(scenario['Query'])
                if raw:
                    st.dataframe(pd.DataFrame(extract_docs(raw)), column_config={"Link": st.column_config.LinkColumn("PDF")}, hide_index=True, use_container_width=True)
                else:
                    st.caption("Keine Ergebnisse.")
