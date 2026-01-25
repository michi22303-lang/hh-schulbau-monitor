import streamlit as st
import requests
import pandas as pd

# --- DATENBASIS (Musterdaten) ---
# Struktur: Bezirk -> Stadtteil -> Liste von Schulen (Name, Kennziffer/Schülerzahl)
# In einer echten App würde das aus einer CSV oder Datenbank kommen.
SCHUL_DATEN = {
    "Altona": {
        "Othmarschen": [
            {"name": "Gymnasium Hochrad", "id": "5887", "students": "ca. 950"} 
        ]
    },
    "Bergedorf": {
        "Kirchwerder": [
            {"name": "Schule Zollenspieker", "id": "5648", "students": "ca. 230"}
        ]
    },
    "Mitte": {
        "Billstedt": [
            {"name": "Grundschule Mümmelmannsberg", "id": "5058", "students": "ca. 340"}
        ]
    }
}

# --- KONFIGURATION ---
API_URL = "https://suche.transparenz.hamburg.de/api/3/action/package_search"

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
        response.raise_for_status()
        data = response.json()
        return data["result"]["results"] if data["success"] else []
    except Exception as e:
        st.error(f"API-Fehler: {e}")
        return []

def extract_docs(results):
    """Extrahiert Titel und Links aus den Ergebnissen."""
    cleaned = []
    for item in results:
        resources = item.get("resources", [])
        # Versuche PDF zu finden, sonst nimm den Hauptlink
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
st.set_page_config(page_title="HH Schulbau Monitor V2", layout="wide")

st.title("🏫 Hamburger Schulbau-Monitor")
st.markdown("Recherche-Tool für Schulimmobilien mit Standort-Drilldown.")

# --- SIDEBAR: KASKADIERENDE AUSWAHL ---
with st.sidebar:
    st.header("Standort-Auswahl")

    # 1. Ebene: Bezirk
    bezirke = list(SCHUL_DATEN.keys())
    selected_bezirk = st.selectbox("1. Bezirk wählen", bezirke)

    # 2. Ebene: Stadtteil (abhängig von Bezirk)
    stadtteile = list(SCHUL_DATEN[selected_bezirk].keys())
    selected_stadtteil = st.selectbox("2. Stadtteil wählen", stadtteile)

    # 3. Ebene: Schule (abhängig von Stadtteil)
    # Wir holen die Liste der Schul-Dictionaries
    schulen_liste = SCHUL_DATEN[selected_bezirk][selected_stadtteil]
    # Für die Selectbox zeigen wir nur den Namen an
    schule_obj = st.selectbox(
        "3. Schule wählen", 
        schulen_liste, 
        format_func=lambda x: f"{x['name']} ({x['id']})"
    )

    st.divider()
    start_search = st.button("Recherche starten", type="primary")

# --- HAUPTBEREICH ---
if start_search and schule_obj:
    
    # 1. KEY INFO BLOCK (Stammdaten anzeigen)
    st.subheader(f"Dossier: {schule_obj['name']}")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Bezirk", selected_bezirk)
    col2.metric("Stadtteil", selected_stadtteil)
    # Hier simulieren wir die 'Key Information' aus unserer Datenbank
    col3.metric("Kennziffer / ID", schule_obj['id'], delta_color="off")
    
    st.info(f"📍 **Standort-Info:** Suchfokus liegt auf **{schule_obj['name']}** (ID: {schule_obj['id']}).")
    
    st.divider()

    # 2. AUTOMATISIERTE SUCHE
    # Wir nutzen Name UND ID für präzisere Ergebnisse
    schul_query = f'"{schule_obj["name"]}" OR "{schule_obj["id"]}"'

    search_scenarios = [
        {
            "Icon": "📜",
            "Topic": "Entwicklungsplanung (SEPL)",
            # Suche nach SEPL im Bezirk, aber filtere gedanklich nach Relevanz
            "Query": f'Schulentwicklungsplan "{selected_bezirk}"', 
            "Help": "Zeigt generelle Planungen für den Bezirk."
        },
        {
            "Icon": "🏗️",
            "Topic": "Objektbezogene Drucksachen & Bau",
            # Hier ist die Schulkennziffer (ID) oft Gold wert in Drucksachen
            "Query": f'{schul_query} Neubau OR Sanierung OR Drucksache', 
            "Help": "Spezifische Beschlüsse zu dieser Schule."
        },
        {
            "Icon": "🗺️",
            "Topic": "Lage & Bebauungspläne",
            "Query": f'Bebauungsplan "{selected_stadtteil}"',
            "Help": "Baurecht im Stadtteil."
        }
    ]

    # Anzeige der Ergebnisse
    for scenario in search_scenarios:
        with st.expander(f"{scenario['Icon']} {scenario['Topic']}", expanded=True):
            st.caption(f"Suchbefehl: `{scenario['Query']}`")
            
            raw_results = query_transparenzportal(scenario['Query'])
            
            if raw_results:
                df = pd.DataFrame(extract_docs(raw_results))
                st.dataframe(
                    df,
                    column_config={
                        "Link": st.column_config.LinkColumn("PDF öffnen")
                    },
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.warning("Keine Dokumente im Transparenzportal gefunden.")

elif not start_search:
    st.info("👈 Bitte wählen Sie links einen Standort aus.")
