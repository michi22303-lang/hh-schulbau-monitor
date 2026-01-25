import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
import time

# --- DATENBASIS (Jetzt mit ADRESSEN statt Koordinaten) ---
SCHUL_DATEN = {
    "Altona": {
        "Othmarschen": [
            {
                "name": "Gymnasium Hochrad", 
                "id": "5887", 
                "students": "ca. 950", 
                "address": "Hochrad 2, 22605 Hamburg"
            } 
        ]
    },
    "Bergedorf": {
        "Kirchwerder": [
            {
                "name": "Schule Zollenspieker", 
                "id": "5648", 
                "students": "ca. 230", 
                "address": "Kirchwerder Landweg 558, 21037 Hamburg"
            }
        ]
    },
    "Mitte": {
        "Billstedt": [
            {
                "name": "Grundschule Mümmelmannsberg", 
                "id": "5058", 
                "students": "ca. 340", 
                "address": "Mümmelmannsberg 52, 22115 Hamburg"
            }
        ]
    }
}

# --- KONFIGURATION ---
API_URL_TRANSPARENZ = "https://suche.transparenz.hamburg.de/api/3/action/package_search"
WMS_ALKIS = "https://geodienste.hamburg.de/HH_WMS_ALKIS"
WMS_DOP = "https://geodienste.hamburg.de/HH_WMS_DOP"

# --- HELFER-FUNKTIONEN ---

@st.cache_data(show_spinner=False)
def get_coordinates(address_string):
    """
    Holt Koordinaten (Lat, Lon) für eine Adresse via Nominatim (OSM).
    Nutzt Caching, um die API zu schonen.
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address_string,
        "format": "json",
        "limit": 1
    }
    # User-Agent ist Pflicht bei Nominatim!
    headers = {'User-Agent': 'HH-Schulbau-Monitor/1.0'}
    
    try:
        response = requests.get(url, params=params, headers=headers)
        data = response.json()
        if data:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            return [lat, lon]
        else:
            return None
    except Exception as e:
        return None

def query_transparenzportal(search_term, limit=5):
    """Fragt die CKAN API ab."""
    params = {
        "q": search_term,
        "rows": limit,
        "sort": "score desc, metadata_modified desc"
    }
    try:
        response = requests.get(API_URL_TRANSPARENZ, params=params)
        data = response.json()
        return data["result"]["results"] if data.get("success") else []
    except Exception:
        return []

def extract_docs(results):
    cleaned = []
    for item in results:
        resources = item.get("resources", [])
        target_link = item.get("url", "")
        for res in resources:
            if res.get("format", "").lower() == "pdf":
                target_link = res.get("url")
                break
        
        cleaned.append({
            "Dokument": item.get("title"),
            "Datum": item.get("metadata_modified", "")[:10],
            "Link": target_link
        })
    return cleaned

# --- UI SETUP ---
st.set_page_config(page_title="HH Schulbau Monitor V4", layout="wide")
st.title("🏫 Hamburger Schulbau-Monitor")

# --- SIDEBAR ---
with st.sidebar:
    st.header("Standort-Auswahl")
    bezirke = list(SCHUL_DATEN.keys())
    selected_bezirk = st.selectbox("1. Bezirk", bezirke)
    stadtteile = list(SCHUL_DATEN[selected_bezirk].keys())
    selected_stadtteil = st.selectbox("2. Stadtteil", stadtteile)
    schulen_liste = SCHUL_DATEN[selected_bezirk][selected_stadtteil]
    
    schule_obj = st.selectbox(
        "3. Schule", 
        schulen_liste, 
        format_func=lambda x: f"{x['name']} ({x['id']})"
    )
    
    st.divider()
    st.caption("Karten-Optionen")
    show_alkis = st.checkbox("ALKIS (Flurstücke)", value=True)
    show_luftbild = st.checkbox("Luftbild (DOP20)", value=False)

# --- LOGIK: Koordinaten abrufen ---
if schule_obj:
    coords = get_coordinates(schule_obj["address"])
    
    if not coords:
        st.error(f"Konnte keine Koordinaten für '{schule_obj['address']}' finden.")
        # Fallback auf Rathausmarkt, damit App nicht crasht
        coords = [53.550, 9.992] 
    
    # --- HAUPTBEREICH ---
    
    # Metriken
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Bezirk / Stadtteil", f"{selected_bezirk} / {selected_stadtteil}")
    col2.metric("Kennziffer", schule_obj['id'])
    col3.metric("Schülerzahl", schule_obj['students'])
    col4.metric("Adresse", schule_obj['address']) # Neue Anzeige

    # Tabs
    tab_map, tab_docs = st.tabs(["🗺️ Karte & Kataster", "📂 Dokumente & Planung"])

    # --- TAB 1: KARTE ---
    with tab_map:
        if coords:
            m = folium.Map(location=coords, zoom_start=18)

            if show_luftbild:
                folium.WmsTileLayer(
                    url=WMS_DOP, layers="dop20", fmt="image/png",
                    name="Luftbild", attr="Geoportal Hamburg"
                ).add_to(m)

            if show_alkis:
                folium.WmsTileLayer(
                    url=WMS_ALKIS, layers="alkis_flurstuecke", fmt="image/png",
                    transparent=True, name="ALKIS Flurstücke", attr="Geoportal Hamburg"
                ).add_to(m)
                folium.WmsTileLayer(
                    url=WMS_ALKIS, layers="alkis_gebaeude", fmt="image/png",
                    transparent=True, name="ALKIS Gebäude", attr="Geoportal Hamburg"
                ).add_to(m)

            # Marker
            folium.Marker(
                coords, 
                popup=f"{schule_obj['name']}\n{schule_obj['address']}",
                icon=folium.Icon(color="red", icon="home")
            ).add_to(m)

            st_folium(m, height=500, use_container_width=True)

    # --- TAB 2: DOKUMENTE ---
    with tab_docs:
        schul_query = f'"{schule_obj["name"]}" OR "{schule_obj["id"]}"'
        
        search_scenarios = [
            {"Icon": "📜", "Topic": "SEPL & Bedarf", "Query": f'Schulentwicklungsplan "{selected_bezirk}"'},
            {"Icon": "🏗️", "Topic": "Drucksachen (Bau)", "Query": f'{schul_query} Neubau OR Sanierung OR Drucksache'},
            {"Icon": "⚖️", "Topic": "B-Pläne", "Query": f'Bebauungsplan "{selected_stadtteil}"'}
        ]

        for scenario in search_scenarios:
            with st.expander(f"{scenario['Icon']} {scenario['Topic']}", expanded=False):
                with st.spinner("Suche im Transparenzportal..."):
                    raw_results = query_transparenzportal(scenario['Query'])
                
                if raw_results:
                    df = pd.DataFrame(extract_docs(raw_results))
                    st.dataframe(
                        df, 
                        column_config={"Link": st.column_config.LinkColumn("PDF")}, 
                        hide_index=True, 
                        use_container_width=True
                    )
                else:
                    st.info("Keine Dokumente gefunden.")
