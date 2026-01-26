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
WMS_DOP = "https://geodienste.hamburg.de/HH_WMS_DOP" 
WMS_STADTPLAN = "https://geodienste.hamburg.de/HH_WMS_Stadtplan"

# --- 3. HELFER ---
@st.cache_data(show_spinner=False)
def get_coordinates(address_string):
    if not address_string: return None
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address_string, "format": "json", "limit": 1}
    headers = {'User-Agent': 'HH-Schulbau-Monitor-App/1.0'}
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

# --- 4. UI ---
st.set_page_config(page_title="HH Schulbau Monitor V5", layout="wide")
st.title("🏫 Hamburger Schulbau-Monitor")

# Sidebar
with st.sidebar:
    st.header("Standort")
    bezirke = list(SCHUL_DATEN.keys())
    selected_bezirk = st.selectbox("1. Bezirk", bezirke)
    stadtteile = list(SCHUL_DATEN[selected_bezirk].keys())
    selected_stadtteil = st.selectbox("2. Stadtteil", stadtteile)
    schulen_liste = SCHUL_DATEN[selected_bezirk][selected_stadtteil]
    schule_obj = st.selectbox("3. Schule", schulen_liste, format_func=lambda x: f"{x['name']} ({x['id']})")

# MAIN
if schule_obj:
    adresse = schule_obj.get("address", "")
    
    # Koordinaten holen
    coords = get_coordinates(adresse)
    if not coords:
        coords = [53.550, 9.992] # Fallback Rathaus
        st.sidebar.warning("Adresse nicht gefunden. Zeige Fallback (Rathaus).")

    # Header Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Bezirk / Stadtteil", f"{selected_bezirk} / {selected_stadtteil}")
    col2.metric("Kennziffer", schule_obj.get('id', '-'))
    col3.metric("Schülerzahl", schule_obj.get('students', '-'))
    col4.metric("Adresse", adresse)
    
    st.markdown("---")

    # TABS WIEDERHERGESTELLT
    tab_map, tab_docs = st.tabs(["🗺️ Kataster & Luftbild", "📂 Dokumente & Planung"])

    # --- TAB 1: KARTE ---
    with tab_map:
        col_map, col_info = st.columns([3, 1])
        
        with col_map:
            # Karte initialisieren
            m = folium.Map(location=coords, zoom_start=19, tiles="OpenStreetMap")

            # 1. Stadtplan (Grau) - Oft klarer als OSM
            folium.WmsTileLayer(
                url=WMS_STADTPLAN,
                layers="stadtplan_grau",
                fmt="image/png",
                name="Stadtplan (Grau)",
                attr="Geoportal Hamburg",
                overlay=False,
                control=True
            ).add_to(m)

            # 2. Luftbild (KORRIGIERT: Layer Name angepasst!)
            folium.WmsTileLayer(
                url=WMS_DOP,
                layers="dop_zeitreihe_belaubt", # <--- Das ist der korrekte Layer-Name für "Bilder"
                fmt="image/jpeg",
                name="Luftbild (Sommer)",
                attr="Geoportal Hamburg",
                overlay=False,
                control=True
            ).add_to(m)

            # 3. ALKIS (Kataster Overlay)
            folium.WmsTileLayer(
                url=WMS_ALKIS,
                layers="alkis_flurstuecke,alkis_bezeichnung,alkis_gebaeude",
                fmt="image/png",
                transparent=True,
                name="ALKIS Kataster",
                attr="Geoportal Hamburg",
                overlay=True,
                control=True
            ).add_to(m)

            # Marker und Controls
            folium.Marker(coords, popup=schule_obj['name'], icon=folium.Icon(color="red", icon="home")).add_to(m)
            folium.LayerControl().add_to(m)

            # Karte anzeigen
            st_folium(m, height=600, use_container_width=True)

        with col_info:
            st.info("ℹ️ **Ebenen steuern**")
            st.markdown("""
            Nutzen Sie das **Layer-Symbol** (oben rechts in der Karte), um zwischen:
            * Stadtplan
            * Luftbild
            
            umzuschalten. ALKIS (schwarze Linien) liegt transparent darüber.
            """)
            st.link_button("↗️ Zu Geo-Online Hamburg", "https://geoportal-hamburg.de/geo-online/")

    # --- TAB 2: DOKUMENTE ---
    with tab_docs:
        schul_query = f'"{schule_obj["name"]}" OR "{schule_obj["id"]}"'
        search_scenarios = [
            {"Icon": "📜", "Topic": "SEPL", "Query": f'Schulentwicklungsplan "{selected_bezirk}"'},
            {"Icon": "🏗️", "Topic": "Bau & Drucksachen", "Query": f'{schul_query} Neubau OR Sanierung OR Drucksache'},
            {"Icon": "⚖️", "Topic": "B-Pläne", "Query": f'Bebauungsplan "{selected_stadtteil}"'}
        ]

        st.caption(f"Suche nach Dokumenten für: **{schule_obj['name']}**")
        
        for scenario in search_scenarios:
            with st.expander(f"{scenario['Icon']} {scenario['Topic']}", expanded=False):
                # Button verhindert automatische (teure) Suche bei jedem Klick, wenn man will
                # Hier direktes Laden beim Öffnen des Expanders simulieren wir einfach durch Ausführen:
                with st.spinner("Lade Daten..."):
                    raw = query_transparenzportal(scenario['Query'])
                
                if raw:
                    df = pd.DataFrame(extract_docs(raw))
                    st.dataframe(
                        df, 
                        column_config={"Link": st.column_config.LinkColumn("PDF Download")}, 
                        hide_index=True, 
                        use_container_width=True
                    )
                else:
                    st.warning("Keine Dokumente im Transparenzportal gefunden.")
