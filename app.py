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

# --- 2. KONFIGURATION & API URLs ---
API_URL_TRANSPARENZ = "https://suche.transparenz.hamburg.de/api/3/action/package_search"
# WMS URLs (Geodienste Hamburg)
WMS_ALKIS = "https://geodienste.hamburg.de/HH_WMS_ALKIS"
WMS_DOP = "https://geodienste.hamburg.de/HH_WMS_DOP" 

# --- 3. HELFER-FUNKTIONEN ---

@st.cache_data(show_spinner=False)
def get_coordinates(address_string):
    if not address_string: return None
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address_string, "format": "json", "limit": 1}
    headers = {'User-Agent': 'HH-Schulbau-Monitor/1.0'}
    try:
        response = requests.get(url, params=params, headers=headers)
        data = response.json()
        if data:
            return [float(data[0]["lat"]), float(data[0]["lon"])]
    except: return None
    return None

def query_transparenzportal(search_term, limit=5):
    params = {"q": search_term, "rows": limit, "sort": "score desc, metadata_modified desc"}
    try:
        response = requests.get(API_URL_TRANSPARENZ, params=params)
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
st.set_page_config(page_title="HH Schulbau Monitor V5", layout="wide")
st.title("🏫 Hamburger Schulbau-Monitor")

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("Standort-Auswahl")
    bezirke = list(SCHUL_DATEN.keys())
    selected_bezirk = st.selectbox("1. Bezirk", bezirke)
    stadtteile = list(SCHUL_DATEN[selected_bezirk].keys())
    selected_stadtteil = st.selectbox("2. Stadtteil", stadtteile)
    schulen_liste = SCHUL_DATEN[selected_bezirk][selected_stadtteil]
    schule_obj = st.selectbox("3. Schule", schulen_liste, format_func=lambda x: f"{x['name']} ({x['id']})")
    
    st.divider()
    st.caption("Karten-Ebenen")
    # Default ALKIS auf "True" für Kataster-Infos
    show_alkis = st.checkbox("ALKIS (Flurstücke & Nummern)", value=True) 
    show_luftbild = st.checkbox("Luftbild (DOP20)", value=True)

# --- 6. HAUPTBEREICH ---
if schule_obj:
    adresse = schule_obj.get("address", "")
    coords = get_coordinates(adresse)
    
    # Fallback Coordinates (Rathaus)
    if not coords: coords = [53.550, 9.992]

    # A. INFO HEADER
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Bezirk / Stadtteil", f"{selected_bezirk} / {selected_stadtteil}")
    col2.metric("Kennziffer", schule_obj.get('id', '-'))
    col3.metric("Schülerzahl", schule_obj.get('students', '-'))
    col4.metric("Adresse", adresse)
    
    st.markdown("---")

    # B. TABS
    tab_map, tab_docs = st.tabs(["🗺️ Kataster & Luftbild", "📂 Dokumente & Planung"])

    # --- TAB 1: KARTE ---
    with tab_map:
        col_map, col_info = st.columns([3, 1])
        
        with col_map:
            # Karte initialisieren
            m = folium.Map(location=coords, zoom_start=19) # Zoom 19 ist wichtig für Flurstücksnummern!

            # 1. Layer: Luftbild (Fix: Layer-Name "DOP" statt "dop20")
            if show_luftbild:
                folium.WmsTileLayer(
                    url=WMS_DOP,
                    layers="DOP",  # <--- HIER WAR DER FEHLER (Layer Name)
                    fmt="image/jpeg",
                    name="Luftbild",
                    attr="Geoportal Hamburg"
                ).add_to(m)

            # 2. Layer: ALKIS (Transparent darüber)
            if show_alkis:
                # Flurstücke (Die schwarzen Linien)
                folium.WmsTileLayer(
                    url=WMS_ALKIS,
                    layers="alkis_flurstuecke",
                    fmt="image/png",
                    transparent=True,
                    name="ALKIS Grenzen",
                    attr="Geoportal Hamburg"
                ).add_to(m)
                
                # Flurstücksnummern & Texte (Wichtig!)
                folium.WmsTileLayer(
                    url=WMS_ALKIS,
                    layers="alkis_bezeichnung", # <--- HIER SIND DIE NUMMERN
                    fmt="image/png",
                    transparent=True,
                    name="ALKIS Nummern",
                    attr="Geoportal Hamburg"
                ).add_to(m)
                
                # Gebäudeumringe
                folium.WmsTileLayer(
                    url=WMS_ALKIS,
                    layers="alkis_gebaeude",
                    fmt="image/png",
                    transparent=True,
                    name="ALKIS Gebäude",
                    attr="Geoportal Hamburg"
                ).add_to(m)

            # Marker
            folium.Marker(
                coords, 
                popup=schule_obj['name'],
                icon=folium.Icon(color="red", icon="home")
            ).add_to(m)

            st_folium(m, height=600, use_container_width=True)

        with col_info:
            st.info("ℹ️ **Hinweis zur Größe:**")
            st.markdown("""
            Die exakte Quadratmeterzahl (amtliche Fläche) ist in den Kartendiensten nicht direkt auslesbar.
            
            Um das **Flurstückskataster** einzusehen (inkl. Größe), nutzen Sie bitte den offiziellen Viewer der Stadt:
            """)
            
            # Generischer Link zu Geo-Online (Startet Suche)
            geo_online_link = "https://geoportal-hamburg.de/geo-online/"
            st.link_button("↗️ Zu Geo-Online Hamburg", geo_online_link)
            
            st.caption("Dort können Sie auf das Grundstück klicken, um die Fläche in m² zu sehen.")

    # --- TAB 2: DOKUMENTE ---
    with tab_docs:
        schul_query = f'"{schule_obj["name"]}" OR "{schule_obj["id"]}"'
        search_scenarios = [
            {"Icon": "📜", "Topic": "SEPL", "Query": f'Schulentwicklungsplan "{selected_bezirk}"'},
            {"Icon": "🏗️", "Topic": "Bau & Drucksachen", "Query": f'{schul_query} Neubau OR Sanierung OR Drucksache'},
            {"Icon": "⚖️", "Topic": "B-Pläne", "Query": f'Bebauungsplan "{selected_stadtteil}"'}
        ]

        for scenario in search_scenarios:
            with st.expander(f"{scenario['Icon']} {scenario['Topic']}", expanded=False):
                with st.spinner("Lade..."):
                    raw = query_transparenzportal(scenario['Query'])
                if raw:
                    st.dataframe(pd.DataFrame(extract_docs(raw)), column_config={"Link": st.column_config.LinkColumn("PDF")}, hide_index=True, use_container_width=True)
                else:
                    st.warning("Nichts gefunden.")
