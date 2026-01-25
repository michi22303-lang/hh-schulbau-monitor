import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium

# --- 1. DATENBASIS (Stammdaten mit Adressen) ---
# Hier sind die Adressen hinterlegt, die für das Geocoding genutzt werden.
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

# --- 2. KONFIGURATION & API URLs ---
API_URL_TRANSPARENZ = "https://suche.transparenz.hamburg.de/api/3/action/package_search"
WMS_ALKIS = "https://geodienste.hamburg.de/HH_WMS_ALKIS"
WMS_DOP = "https://geodienste.hamburg.de/HH_WMS_DOP"

# --- 3. HELFER-FUNKTIONEN ---

@st.cache_data(show_spinner=False)
def get_coordinates(address_string):
    """
    Holt Koordinaten (Lat, Lon) für eine Adresse via Nominatim (OSM).
    Nutzt Caching, um die API zu schonen.
    """
    if not address_string:
        return None
        
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address_string,
        "format": "json",
        "limit": 1
    }
    # User-Agent ist Pflicht bei Nominatim, sonst wird man blockiert
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
    except Exception:
        return None

def query_transparenzportal(search_term, limit=5):
    """Fragt die CKAN API des Transparenzportals ab."""
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
    """Wandelt API-Ergebnisse in eine saubere Liste um."""
    cleaned = []
    for item in results:
        resources = item.get("resources", [])
        target_link = item.get("url", "") # Fallback
        
        # Bevorzuge PDF-Links
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

# --- 4. UI SETUP ---
st.set_page_config(page_title="HH Schulbau Monitor", layout="wide")
st.title("🏫 Hamburger Schulbau-Monitor")

# --- 5. SIDEBAR (Auswahl-Logik) ---
with st.sidebar:
    st.header("Standort-Auswahl")
    
    # Kaskadierende Auswahl
    bezirke = list(SCHUL_DATEN.keys())
    selected_bezirk = st.selectbox("1. Bezirk", bezirke)
    
    stadtteile = list(SCHUL_DATEN[selected_bezirk].keys())
    selected_stadtteil = st.selectbox("2. Stadtteil", stadtteile)
    
    schulen_liste = SCHUL_DATEN[selected_bezirk][selected_stadtteil]
    
    # Wählt das ganze Objekt (Dictionary) aus
    schule_obj = st.selectbox(
        "3. Schule", 
        schulen_liste, 
        format_func=lambda x: f"{x['name']} ({x['id']})"
    )
    
    st.divider()
    st.caption("Karten-Layer")
    show_alkis = st.checkbox("ALKIS (Flurstücke)", value=True)
    show_luftbild = st.checkbox("Luftbild (DOP20)", value=False)

# --- 6. HAUPTBEREICH (Logic & Display) ---
if schule_obj:
    
    # Adresse sicher abrufen (verhindert KeyErrors)
    adresse = schule_obj.get("address", "")
    
    # Koordinaten holen (mit Lade-Indikator oben rechts)
    coords = get_coordinates(adresse)
    
    # Fallback, falls Geocoding fehlschlägt (Rathausmarkt)
    if not coords:
        if adresse:
            st.warning(f"Konnte Adresse '{adresse}' nicht auf der Karte finden. Zeige Hamburg-Zentrum.")
        coords = [53.550, 9.992]

    # A. KEY METRICS
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Bezirk / Stadtteil", f"{selected_bezirk} / {selected_stadtteil}")
    col2.metric("Kennziffer", schule_obj.get('id', '-'))
    col3.metric("Schülerzahl", schule_obj.get('students', '-'))
    col4.metric("Adresse", adresse)

    st.divider()

    # B. TABS
    tab_map, tab_docs = st.tabs(["🗺️ Karte & Kataster", "📂 Dokumente & Planung"])

    # --- TAB 1: KARTE ---
    with tab_map:
        # Karte erstellen
        m = folium.Map(location=coords, zoom_start=18)

        # Luftbild Layer
        if show_luftbild:
            folium.WmsTileLayer(
                url=WMS_DOP,
                layers="dop20",
                fmt="image/png",
                name="Luftbild",
                attr="Geoportal Hamburg"
            ).add_to(m)

        # ALKIS Layer (Transparent)
        if show_alkis:
            folium.WmsTileLayer(
                url=WMS_ALKIS,
                layers="alkis_flurstuecke",
                fmt="image/png",
                transparent=True,
                name="ALKIS Flurstücke",
                attr="Geoportal Hamburg"
            ).add_to(m)
            folium.WmsTileLayer(
                url=WMS_ALKIS,
                layers="alkis_gebaeude",
                fmt="image/png",
                transparent=True,
                name="ALKIS Gebäude",
                attr="Geoportal Hamburg"
            ).add_to(m)

        # Roter Marker für die Schule
        folium.Marker(
            coords, 
            popup=f"{schule_obj['name']}",
            icon=folium.Icon(color="red", icon="home")
        ).add_to(m)

        st_folium(m, height=500, use_container_width=True)

    # --- TAB 2: DOKUMENTE ---
    with tab_docs:
        # Suchbegriff: Name ODER ID (oft genauer)
        schul_query = f'"{schule_obj["name"]}" OR "{schule_obj["id"]}"'
        
        search_scenarios = [
            {
                "Icon": "📜", 
                "Topic": "SEPL & Bedarf", 
                "Query": f'Schulentwicklungsplan "{selected_bezirk}"'
            },
            {
                "Icon": "🏗️", 
                "Topic": "Drucksachen (Bau)", 
                "Query": f'{schul_query} Neubau OR Sanierung OR Drucksache'
            },
            {
                "Icon": "⚖️", 
                "Topic": "B-Pläne", 
                "Query": f'Bebauungsplan "{selected_stadtteil}"'
            }
        ]

        for scenario in search_scenarios:
            with st.expander(f"{scenario['Icon']} {scenario['Topic']}", expanded=False):
                with st.spinner(f"Suche nach {scenario['Topic']}..."):
                    raw_results = query_transparenzportal(scenario['Query'])
                
                if raw_results:
                    df = pd.DataFrame(extract_docs(raw_results))
                    st.dataframe(
                        df, 
                        column_config={"Link": st.column_config.LinkColumn("Link zum PDF")}, 
                        hide_index=True, 
                        use_container_width=True
                    )
                else:
                    st.info("Keine Dokumente gefunden.")

elif not schule_obj:
    st.info("Bitte wählen Sie links eine Schule aus.")
