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
# NEU: Stadtplan als Alternative Hintergrundkarte
WMS_STADTPLAN = "https://geodienste.hamburg.de/HH_WMS_Stadtplan"
# NEU: Bebauungspläne
WMS_BPLAN = "https://geodienste.hamburg.de/HH_WMS_Bebauungsplaene"

# --- 3. HELFER-FUNKTIONEN ---

@st.cache_data(show_spinner=False)
def get_coordinates(address_string):
    if not address_string: return None
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address_string, "format": "json", "limit": 1}
    # NEU: Wichtig für Nominatim: Referer oder Email hilft oft gegen Blockierung
    headers = {
        'User-Agent': 'HH-Schulbau-Monitor-StudentProject/1.0',
        'Referer': 'http://localhost' 
    }
    try:
        # NEU: Timeout hinzugefügt (10 Sekunden warten), sonst bricht es zu früh ab
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status() # Wirft Fehler bei HTTP Errors
        data = response.json()
        if data:
            return [float(data[0]["lat"]), float(data[0]["lon"])]
    except Exception as e:
        # NEU: Fehler im Log anzeigen, damit man weiß, warum es scheitert
        print(f"Fehler bei Geocoding für {address_string}: {e}")
        return None
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
    st.info("ℹ️ Kartenebenen können jetzt direkt in der Karte (Symbol oben rechts) gewechselt werden.")

# --- 6. HAUPTBEREICH ---
if schule_obj:
    adresse = schule_obj.get("address", "")
    
    with st.spinner("Suche Koordinaten..."):
        coords = get_coordinates(adresse)
    
    # Fallback Coordinates (Rathaus) mit Warnhinweis
    if not coords: 
        coords = [53.550, 9.992]
        st.warning(f"Konnte Adresse '{adresse}' nicht finden. Zeige Rathaus (Fallback).")

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
        # Karte initialisieren
        m = folium.Map(location=coords, zoom_start=19, tiles=None) # tiles=None damit wir volle Kontrolle haben

        # NEU: Layer 1 - Basis: Stadtplan (Grau) - Oft besser lesbar als OSM
        folium.WmsTileLayer(
            url=WMS_STADTPLAN,
            layers="stadtplan_grau",
            fmt="image/png",
            name="Stadtplan (Grau)",
            attr="Geoportal Hamburg",
            overlay=False, # Das ist ein "Base Layer"
            control=True
        ).add_to(m)

        # NEU: Layer 2 - Basis: Luftbild (DOP20)
        folium.WmsTileLayer(
            url=WMS_DOP,
            layers="DOP",
            fmt="image/jpeg",
            name="Luftbild (DOP20)",
            attr="Geoportal Hamburg",
            overlay=False, # Auch als Base Layer nutzbar (dann wechseln sie sich exklusiv ab)
            control=True
        ).add_to(m)

        # NEU: Layer 3 - Overlay: ALKIS (Grenzen & Nummern)
        folium.WmsTileLayer(
            url=WMS_ALKIS,
            layers="alkis_flurstuecke,alkis_bezeichnung,alkis_gebaeude", # Man kann Layer kommasepariert anfragen!
            fmt="image/png",
            transparent=True,
            name="Kataster (ALKIS)",
            attr="Geoportal Hamburg",
            overlay=True, # Legt sich drüber
            control=True
        ).add_to(m)

        # NEU: Layer 4 - Overlay: Bebauungspläne
        folium.WmsTileLayer(
            url=WMS_BPLAN,
            layers="festgestellt", # Layername für festgestellte B-Pläne
            fmt="image/png",
            transparent=True,
            name="Bebauungspläne",
            attr="Geoportal Hamburg",
            overlay=True,
            show=False, # Standardmäßig aus
            control=True
        ).add_to(m)

        # Marker
        folium.Marker(
            coords, 
            popup=schule_obj['name'],
            tooltip=schule_obj['name'],
            icon=folium.Icon(color="red", icon="home")
        ).add_to(m)

        # NEU: LayerControl - Das Zauberwerkzeug für Layer-Wechsel
        folium.LayerControl(collapsed=False).add_to(m)

        st_folium(m, height=600, use_container_width=True)

        # Info Box drunter
        st.caption("Nutzen Sie das Ebenen-Symbol oben rechts in der Karte, um zwischen Luftbild und Stadtplan zu wechseln.")


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
