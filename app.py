import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium

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
WMS_ALKIS = "https://geodienste.hamburg.de/HH_WMS_ALKIS"

# --- 3. HELFER ---
@st.cache_data(show_spinner=False)
def get_coordinates(address_string):
    if not address_string: return None
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address_string, "format": "json", "limit": 1}
    headers = {'User-Agent': 'HH-Schulbau-Monitor-V9/1.0'}
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

# --- 4. UI SETUP ---
st.set_page_config(page_title="HH Schulbau Monitor V9", layout="wide")
st.title("🏫 Hamburger Schulbau-Monitor")

# --- 5. SIDEBAR (KOMPLETT) ---
with st.sidebar:
    st.header("1. Standort-Wahl")
    bezirke = list(SCHUL_DATEN.keys())
    selected_bezirk = st.selectbox("Bezirk", bezirke)
    stadtteile = list(SCHUL_DATEN[selected_bezirk].keys())
    selected_stadtteil = st.selectbox("Stadtteil", stadtteile)
    schulen_liste = SCHUL_DATEN[selected_bezirk][selected_stadtteil]
    schule_obj = st.selectbox("Schule", schulen_liste, format_func=lambda x: f"{x['name']} ({x['id']})")
    
    st.markdown("---")
    
    st.header("2. Karten-Ebenen")
    st.caption("Wählen Sie hier den Look der Karte:")
    
    # A) Hintergrundkarte
    map_style = st.radio(
        "Basiskarte:",
        ("Straßenkarte (OSM)", "Satellit Hybrid", "Grau (Minimal)"),
        index=0
    )
    
    st.caption("Zusatz-Infos einblenden:")
    
    # B) Overlays
    show_alkis = st.checkbox("📐 Kataster (ALKIS)", value=True, help="Zeigt Grundstücksgrenzen und Hausnummern (HH Server)")
    show_transit = st.checkbox("🚆 ÖPNV / Bahn", value=False, help="Zeigt Bahnlinien und Haltestellen (OpenRailwayMap)")
    show_radius = st.checkbox("⭕ 1km Einzugsgebiet", value=False, help="Zeigt einen Kreis von 1km Radius um die Schule")
    
    st.divider()
    if st.button("🔄 Cache leeren"):
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
    col1.metric("Bezirk / Stadtteil", f"{selected_bezirk} / {selected_stadtteil}")
    col2.metric("Kennziffer", schule_obj.get('id', '-'))
    col3.metric("Schülerzahl", schule_obj.get('students', '-'))
    col4.metric("Adresse", adresse)
    
    st.markdown("---")

    # Tabs
    tab_map, tab_docs = st.tabs(["🗺️ Karte & Umgebung", "📂 Dokumente & Planung"])

    # --- TAB 1: KARTE (Jetzt volle Breite) ---
    with tab_map:
        # Karte konfigurieren basierend auf Sidebar-Auswahl
        if map_style == "Straßenkarte (OSM)":
            m = folium.Map(location=coords, zoom_start=18, tiles="OpenStreetMap")
            
        elif map_style == "Satellit Hybrid":
            # Esri World Imagery + Beschriftungen
            m = folium.Map(
                location=coords, 
                zoom_start=18, 
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                attr="Esri World Imagery"
            )
            # Beschriftungs-Overlay (Reference Overlay)
            folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
                attr="Esri Reference",
                name="Beschriftung",
                overlay=True
            ).add_to(m)
            
        else: # Grau (Minimal)
            m = folium.Map(
                location=coords, 
                zoom_start=18, 
                tiles="cartodbpositron",
                attr="CartoDB"
            )

        # 1. Overlay: ALKIS (Kataster)
        if show_alkis:
            folium.WmsTileLayer(
                url=WMS_ALKIS,
                layers="alkis_flurstuecke,alkis_bezeichnung,alkis_gebaeude",
                fmt="image/png",
                transparent=True,
                name="ALKIS",
                attr="Geoportal Hamburg",
                overlay=True
            ).add_to(m)

        # 2. Overlay: ÖPNV (Neu!)
        if show_transit:
            folium.TileLayer(
                tiles="https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png",
                attr="OpenRailwayMap",
                name="ÖPNV",
                overlay=True
            ).add_to(m)

        # 3. Overlay: Radius (Neu!)
        if show_radius:
            folium.Circle(
                radius=1000, # Meter
                location=coords,
                popup="1km Umkreis",
                color="#3186cc",
                fill=True,
                fill_color="#3186cc"
            ).add_to(m)

        # Marker der Schule
        folium.Marker(
            coords, 
            popup=f"<b>{schule_obj['name']}</b><br>{adresse}", 
            icon=folium.Icon(color="red", icon="graduation-cap", prefix="fa")
        ).add_to(m)

        # Karte rendern (Key ändert sich bei jeder Änderung in der Sidebar -> Force Reload)
        st_folium(
            m, 
            height=650, 
            use_container_width=True, 
            key=f"map_{schule_obj['id']}_{map_style}_{show_alkis}_{show_transit}_{show_radius}"
        )
        
        # Legende unter der Karte
        st.caption("Datenquellen: OpenStreetMap, Geoportal Hamburg, Esri, OpenRailwayMap.")

    # --- TAB 2: DOKUMENTE ---
    with tab_docs:
        schul_query = f'"{schule_obj["name"]}" OR "{schule_obj["id"]}"'
        search_scenarios = [
            {"Icon": "📜", "Topic": "Schulentwicklungsplan (SEPL)", "Query": f'Schulentwicklungsplan "{selected_bezirk}"'},
            {"Icon": "🏗️", "Topic": "Bau, Sanierung & Drucksachen", "Query": f'{schul_query} Neubau OR Sanierung OR Drucksache'},
            {"Icon": "⚖️", "Topic": "Bebauungspläne (B-Plan)", "Query": f'Bebauungsplan "{selected_stadtteil}"'}
        ]
        
        col_search_info, _ = st.columns([2,1])
        with col_search_info:
            st.info(f"Suche im Transparenzportal Hamburg für: **{schule_obj['name']}**")

        for scenario in search_scenarios:
            with st.expander(f"{scenario['Icon']} {scenario['Topic']}", expanded=False):
                with st.spinner("Lade Daten..."):
                    raw = query_transparenzportal(scenario['Query'])
                if raw:
                    st.dataframe(pd.DataFrame(extract_docs(raw)), column_config={"Link": st.column_config.LinkColumn("PDF öffnen")}, hide_index=True, use_container_width=True)
                else:
                    st.caption("Keine Treffer gefunden.")
