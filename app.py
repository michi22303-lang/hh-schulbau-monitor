import streamlit as st
import requests
import pandas as pd

# --- KONFIGURATION ---
API_URL = "https://suche.transparenz.hamburg.de/api/3/action/package_search"

# --- FUNKTIONEN ---

def query_transparenzportal(search_term, limit=5):
    """
    Fragt die CKAN API des Hamburger Transparenzportals ab.
    """
    params = {
        "q": search_term,
        "rows": limit,
        "sort": "score desc, metadata_modified desc" # Relevanz + Aktualität
    }
    
    try:
        response = requests.get(API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data["success"]:
            return data["result"]["results"]
        else:
            return []
    except Exception as e:
        st.error(f"Fehler bei der API-Abfrage: {e}")
        return []

def extract_key_info(results):
    """
    Wandelt die JSON-Antwort in eine saubere Liste für die Anzeige um.
    """
    cleaned_data = []
    for item in results:
        # Link zum Dokument finden (PDFs bevorzugt)
        resources = item.get("resources", [])
        pdf_link = None
        web_link = item.get("url", "") # Fallback auf Portal-Link
        
        for res in resources:
            if res.get("format", "").lower() == "pdf":
                pdf_link = res.get("url")
                break
        
        link = pdf_link if pdf_link else web_link
        
        cleaned_data.append({
            "Titel": item.get("title"),
            "Datum": item.get("metadata_modified", "")[:10], # Nur YYYY-MM-DD
            "Behörde": item.get("author", "Unbekannt"),
            "Link": link
        })
    return cleaned_data

# --- STREAMLIT UI ---

st.set_page_config(page_title="HH Schulbau Monitor", layout="wide")

st.title("🏫 Hamburger Schulbau-Monitor")
st.markdown("Automatisierte Recherche im Transparenzportal der FHH für Immobilien-Checkups.")

# Sidebar für Eingaben
with st.sidebar:
    st.header("Projektdaten")
    schul_name = st.text_input("Name der Schule", "Ida-Ehre-Schule")
    bezirk = st.selectbox("Bezirk / Stadtteil", ["Eimsbüttel", "Altona", "Hamburg-Nord", "Wandsbek", "Bergedorf", "Harburg", "Mitte"])
    strasse = st.text_input("Straßenname (optional)", "Bogenstraße")
    
    start_search = st.button("Recherche starten")

# Hauptbereich
if start_search:
    st.divider()
    
    # Wir definieren unsere Such-Strategie (wie im Prompt besprochen)
    search_scenarios = [
        {
            "Topic": "📜 Strategische Planung (SEPL)",
            "Query": f'Schulentwicklungsplan "{bezirk}"',
            "Info": "Sucht nach Schulentwicklungsplänen im Bezirk für Schülerzahlenprognosen."
        },
        {
            "Topic": "🏗️ Baurecht & B-Pläne",
            "Query": f'Bebauungsplan {strasse}' if strasse else f'Bebauungsplan "{bezirk}"',
            "Info": "Prüft Baurecht und Festsetzungen für das Grundstück."
        },
        {
            "Topic": "🏛️ Politische Beschlüsse & Sanierung",
            "Query": f'"{schul_name}" Sanierung OR Neubau OR Drucksache',
            "Info": "Sucht nach Senatsdrucksachen, Budgetfreigaben oder politischen Anträgen."
        },
        {
            "Topic": "☔ Umwelt & Risiken (Geodaten)",
            "Query": f'Starkregengefahrenhinweiskarte OR Lärmkarte "{bezirk}"',
            "Info": "Prüft auf Umweltfaktoren wie Starkregen oder Lärm."
        }
    ]

    # Iteration durch die Szenarien
    for scenario in search_scenarios:
        st.subheader(scenario["Topic"])
        st.caption(f"Suchlogik: `{scenario['Query']}` | {scenario['Info']}")
        
        raw_results = query_transparenzportal(scenario["Query"])
        
        if raw_results:
            df = pd.DataFrame(extract_key_info(raw_results))
            
            # Wir bauen eine klickbare Tabelle (Data Editor ist interaktiv)
            st.dataframe(
                df,
                column_config={
                    "Link": st.column_config.LinkColumn("Dokument öffnen")
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.warning("Keine direkten Treffer gefunden.")
            
    st.success("Recherche abgeschlossen.")

else:
    st.info("Bitte geben Sie links die Daten ein und klicken Sie auf 'Recherche starten'.")
