import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import folium
from streamlit_folium import st_folium

# --- KONFIGURATION AUS DEINEM XML ---
# Dienst für Adressen (aus dem XML File)
WFS_ADRESSEN = "https://geodienste.hamburg.de/HH_WFS_INSPIRE_Adressen"
# Dienst für Gebäude (ALKIS Vereinfacht - robuster)
WFS_GEBAEUDE = "https://geodienste.hamburg.de/WFS_HH_ALKIS_vereinfacht"

st.set_page_config(page_title="Gebäude-Detektiv", layout="wide")
st.title("🕵️‍♂️ Hamburger Gebäude-Detektiv")

# 1. EINGABE
col1, col2 = st.columns(2)
with col1:
    strasse = st.text_input("Straße", "Hochrad")
with col2:
    hausnr = st.text_input("Hausnummer", "2")

# --- FUNKTION 1: Amtliche Koordinate holen ---
def get_official_coordinate(str_name, hnr):
    # Wir nutzen Filter-Encoding für WFS, um exakt die Adresse zu finden
    # Das ist viel präziser als Nominatim!
    filter_xml = f"""
    <Filter>
        <And>
            <PropertyIsLike wildCard="*" singleChar="." escapeChar="!">
                <PropertyName>ad:thoroughfareName</PropertyName>
                <Literal>{str_name}</Literal>
            </PropertyIsLike>
            <PropertyIsEqualTo>
                <PropertyName>ad:locatorDesignator</PropertyName>
                <Literal>{hnr}</Literal>
            </PropertyIsEqualTo>
        </And>
    </Filter>
    """
    
    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": "ad:Address", 
        "FILTER": filter_xml.strip()
    }
    
    try:
        r = requests.get(WFS_ADRESSEN, params=params, timeout=10)
        if r.status_code == 200:
            # XML Parsen (INSPIRE liefert oft GML/XML zurück)
            root = ET.fromstring(r.content)
            # Namespaces sind in INSPIRE extrem nervig, wir suchen "quick & dirty" nach Koordinaten
            # Suche nach <gml:pos> oder ähnlichem
            text_content = r.text
            
            # Einfacher Parser für die Position im XML
            if "<gml:pos>" in text_content:
                start = text_content.find("<gml:pos>") + 9
                end = text_content.find("</gml:pos>")
                coords_str = text_content[start:end].strip().split()
                # INSPIRE liefert oft: Lat Lon (Nord Ost)
                return [float(coords_str[0]), float(coords_str[1])]
    except Exception as e:
        st.error(f"Fehler bei Adress-Suche: {e}")
    return None

# --- FUNKTION 2: Gebäude an Koordinate finden ---
def get_buildings_at_point(lat, lon):
    # Kleiner Radius um den Adresspunkt (100m)
    delta = 0.001
    bbox = f"{lat-delta},{lon-delta},{lat+delta},{lon+delta}"
    
    params = {
        "SERVICE": "WFS",
        "VERSION": "1.1.0", # 1.1.0 ist oft kompatibler
        "REQUEST": "GetFeature",
        "TYPENAME": "alkis_gebaeude",
        "OUTPUTFORMAT": "json",
        "SRSNAME": "EPSG:4326",
        "BBOX": f"{lon-delta},{lat-delta},{lon+delta},{lat+delta},EPSG:4326" # Versuche Lon/Lat
    }
    
    try:
        r = requests.get(WFS_GEBAEUDE, params=params, timeout=10)
        return r.json()
    except Exception as e:
        return str(e)


# --- MAIN LOGIC ---
if st.button("🔍 Adresse & Gebäude suchen"):
    with st.spinner("Frage amtliche Katasterämter ab..."):
        
        # A. Amtliche Koordinate
        coords = get_official_coordinate(strasse, hausnr)
        
        if coords:
            st.success(f"Amtliche Koordinate gefunden: {coords}")
            
            # B. Gebäude suchen
            geo_data = get_buildings_at_point(coords[0], coords[1])
            
            if isinstance(geo_data, dict) and "features" in geo_data:
                feats = geo_data["features"]
                st.info(f"Anzahl Gebäude im Umkreis: {len(feats)}")
                
                # C. Analyse & Karte
                col_list, col_map = st.columns([1, 2])
                
                with col_list:
                    st.subheader("📋 Gebäude-Liste (IDs)")
                    
                    data_rows = []
                    for f in feats:
                        props = f["properties"]
                        # Hier sind die IDs!!
                        gml_id = f.get("id") # Die ID, die du für APIs brauchst
                        nutzung = props.get("gebaeudefunktion_bezeichnung", "Unbekannt")
                        
                        data_rows.append({
                            "Nutzung": nutzung,
                            "GML-ID (API-Key)": gml_id
                        })
                    
                    df = pd.DataFrame(data_rows)
                    st.dataframe(df, use_container_width=True)
                    
                with col_map:
                    m = folium.Map(location=coords, zoom_start=18, tiles="cartodbpositron")
                    
                    # Roter Punkt: Die amtliche Adresse
                    folium.Marker(coords, popup="Amtliche Adresse", icon=folium.Icon(color="red")).add_to(m)
                    
                    # Blaue Gebäude
                    folium.GeoJson(
                        geo_data,
                        tooltip=folium.GeoJsonTooltip(fields=["gebaeudefunktion_bezeichnung"], aliases=["Typ:"]),
                        popup=folium.GeoJsonPopup(fields=["gebaeudefunktion_bezeichnung"]), # Zeigt ID im Popup fehlt hier noch, machen wir clean
                        style_function=lambda x: {'fillColor': 'blue', 'color': 'black', 'weight': 1, 'fillOpacity': 0.3}
                    ).add_to(m)
                    
                    st_folium(m, height=500, use_container_width=True)
                    
            else:
                st.warning("Keine Gebäude-Daten (JSON) erhalten. Evtl. WFS-Fehler.")
                st.write(geo_data) # Fehlermeldung zeigen
        else:
            st.error("Konnte Adresse im INSPIRE-Dienst nicht finden. Schreibweise prüfen (z.B. 'Strasse' vs 'Straße').")
