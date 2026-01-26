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

# --- 3. HELFER ---
@st.cache_data(show_spinner=False)
def get_coordinates(address_string):
    if not address_string: return None
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address_string, "format": "json", "limit": 1}
    headers = {'User-Agent': 'HH-Schulbau-Monitor-Debug/1.0'}
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
    coords = get_coordinates(adresse)
    
    # DEBUG-Info: Sehen wir überhaupt Koordinaten?
    if coords:
        st.success(f"Koordinaten gefunden: {coords}")
    else:
        coords = [53.550, 9.992]
        st.error(f"Keine Koordinaten für '{adresse}' gefunden. Zeige Rathaus.")

    col1, col2, col3 = st.columns(3)
    col1.metric("Schülerzahl", schule_obj.get('students', '-'))
    col2.metric("Adresse", adresse)
    
    st.markdown("---")
    
    # --- KARTE JETZT AUSSERHALB DER TABS ---
    st.subheader("🗺️ Lage & Kataster")
    
    # 1. Grundkarte mit Standard-Tiles (damit man immer WAS sieht)
    m = folium.Map(location=coords, zoom_start=19, tiles="OpenStreetMap")

    # 2. Hamburger Luftbilder (DOP)
    folium.WmsTileLayer(
        url=WMS_DOP,
        layers="DOP",
        fmt="image/jpeg",
        name="Hamburg Luftbild",
        attr="Geoportal Hamburg",
        overlay=False, # Als Basis-Layer (umschaltbar)
        control=True
    ).add_to(m)

    # 3. ALKIS (Kataster)
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

    folium.Marker(coords, popup=schule_obj['name'], icon=folium.Icon(color="red", icon="home")).add_to(m)
    folium.LayerControl().add_to(m)

    # WICHTIG: width=100% kann manchmal Probleme machen, use_container_width=True ist besser
    st_folium(m, height=500, use_container_width=True)

    # --- DOKUMENTE ---
    st.subheader("📂 Dokumente")
    schul_query = f'"{schule_obj["name"]}" OR "{schule_obj["id"]}"'
    
    if st.button("Dokumente suchen"):
        with st.spinner("Suche..."):
            raw = query_transparenzportal(schul_query)
            if raw:
                st.dataframe(pd.DataFrame(extract_docs(raw)), use_container_width=True)
            else:
                st.warning("Keine Dokumente gefunden.")
