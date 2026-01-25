import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium

# --- DATENBASIS (Jetzt mit KOORDINATEN) ---
# Koordinaten sind ca. Werte (Latitude, Longitude) für den Kartenfokus
SCHUL_DATEN = {
    "Altona": {
        "Othmarschen": [
            {"name": "Gymnasium Hochrad", "id": "5887", "students": "ca. 950", "coords": [53.553, 9.878]} 
        ]
    },
    "Bergedorf": {
        "Kirchwerder": [
            {"name": "Schule Zollenspieker", "id": "5648", "students": "ca. 230", "coords": [53.407, 10.183]}
        ]
    },
    "Mitte": {
        "Billstedt": [
            {"name": "Grundschule Mümmelmannsberg", "id": "5058", "students": "ca. 340", "coords": [53.531, 10.145]}
        ]
    }
}

# --- KONFIGURATION ---
API_URL = "https://suche.transparenz.hamburg.de/api/3/action/package_search"

# WMS-URLs der Stadt Hamburg (Offizielle Geodienste)
WMS_ALKIS = "https://geodienste.hamburg.de/HH_WMS_ALKIS"
WMS_DOP = "https://geodienste.hamburg.de/HH_WMS_DOP" # Luftbilder

# --- FUNKTIONEN ---
def query_transparenzportal(search_term, limit=5):
    """Fragt die CKAN API ab."""
    params = {
        "q": search_term,
        "rows": limit,
        "sort": "score desc, metadata_modified desc"
    }
    try:
        response = requests.get(API_URL, params=params)
        data = response.json()
        return data["result"]["results"] if data.get("success") else []
    except Exception:
        return []

def extract_docs(results):
    """Extrahiert Titel und Links."""
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
st.set_page_config(page_title="HH Schulbau Monitor V3", layout="wide")
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
    # Checkboxen für Karten-Layer
    st.caption("Karten-Optionen")
    show_alkis = st.checkbox("ALKIS (Flurstücke)", value=True)
    show_luftbild = st.checkbox("Luftbild (DOP20)", value=False)

# --- HAUPTBEREICH ---
if schule_obj:
    
    # Metriken oben
    col1, col2, col3 = st.columns(3)
    col1.metric("Bezirk / Stadtteil", f"{selected_bezirk} / {selected_stadtteil}")
    col2.metric("Schulkennziffer", schule_obj['id'])
    col3.metric("Schülerzahl (Prognose)", schule_obj['students'])

    # Tabs für bessere Übersicht
    tab_map, tab_docs = st.tabs(["🗺️ Karte & Kataster", "📂 Dokumente & Planung"])

    # --- TAB 1: KARTE (ALKIS & LUFTBILD) ---
    with tab_map:
        st.caption("Live-Daten aus dem Geoportal Hamburg (WMS)")
        
        # Karte initialisieren (zentriert auf Schule)
        m = folium.Map(location=schule_obj['coords'], zoom_start=18)

        # Layer 1: Luftbild (Wenn ausgewählt)
        if show_luftbild:
            folium.WmsTileLayer(
                url=WMS_DOP,
                layers="dop20",
                fmt="image/png",
                name="Luftbild",
                attr="Geoportal Hamburg"
            ).add_to(m)

        # Layer 2: ALKIS (Schwarzplan/Flurstücke)
        if show_alkis:
            # ALKIS wird oft transparent über das Luftbild gelegt
            folium.WmsTileLayer(
                url=WMS_ALKIS,
                layers="alkis_flurstuecke", # Layer-Name für Flurstücke
                fmt="image/png",
                transparent=True,
                name="ALKIS Flurstücke",
                attr="Geoportal Hamburg"
            ).add_to(m)
            
            # Gebäudeumringe zusätzlich
            folium.WmsTileLayer(
                url=WMS_ALKIS,
                layers="alkis_gebaeude", 
                fmt="image/png",
                transparent=True,
                name="ALKIS Gebäude",
                attr="Geoportal Hamburg"
            ).add_to(m)

        # Marker für die Schule
        folium.Marker(
            schule_obj['coords'], 
            popup=schule_obj['name'],
            icon=folium.Icon(color="red", icon="info-sign")
        ).add_to(m)

        # Karte rendern
        st_folium(m, height=500, use_container_width=True)

    # --- TAB 2: DOKUMENTE (TRANSPARENZPORTAL) ---
    with tab_docs:
        schul_query = f'"{schule_obj["name"]}" OR "{schule_obj["id"]}"'
        
        # Scenarios definieren
        search_scenarios = [
            {"Icon": "📜", "Topic": "SEPL & Bedarf", "Query": f'Schulentwicklungsplan "{selected_bezirk}"'},
            {"Icon": "🏗️", "Topic": "Drucksachen (Bau)", "Query": f'{schul_query} Neubau OR Sanierung OR Drucksache'},
            {"Icon": "⚖️", "Topic": "B-Pläne", "Query": f'Bebauungsplan "{selected_stadtteil}"'}
        ]

        for scenario in search_scenarios:
            with st.expander(f"{scenario['Icon']} {scenario['Topic']}", expanded=False):
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
