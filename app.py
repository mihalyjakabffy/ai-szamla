import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import os
import concurrent.futures
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Realign AI Táblázatkezelő", page_icon="📊", layout="wide")
st.title("🚀 Realign AI -> Google Sheets Integráció")

# --- BEÁLLÍTÁSOK ---
st.sidebar.header("⚙️ Beállítások")
API_KEY = st.sidebar.text_input("Gemini API kulcs:", type="password")
SHEET_NAME = st.sidebar.text_input("Google Táblázat pontos neve:", value="Könyvelés 2024")

if not API_KEY:
    st.warning("Kérlek, add meg az API kulcsodat a folytatáshoz!")
    st.stop()

# AI és Google Sheets inicializálás
genai.configure(api_key=API_KEY)

try:
    # Google Sheets csatlakozás (Kibővített jogosultságokkal)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    gc = gspread.authorize(creds)
    
    # Modell választó
    valid_models = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    selected_model_name = st.sidebar.selectbox("🤖 AI Modell:", valid_models, index=0)
    model = genai.GenerativeModel(selected_model_name)
except Exception as e:
    st.error(f"Hiba a csatlakozás során: {e}")
    st.stop()

# --- FELTÖLTÉS ---
uploaded_files = st.file_uploader("Számlák feltöltése (PDF, JPG, PNG)", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=True)

def process_invoice(uploaded_file, prompt, model):
    filename = uploaded_file.name
    temp_path = f"temp_{filename}"
    try:
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        sample_file = genai.upload_file(path=temp_path)
        response = model.generate_content([sample_file, prompt])
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_json)
    except Exception as e:
        return {"Szállító": f"HIBA: {filename}"}
    finally:
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except: pass

if uploaded_files and st.button("Feldolgozás és Mentés a Google Táblázatba"):
    prompt = """
    Elemezd a számlát és adj JSON választ:
    {
      "Szállító": "...", "Számlaszám": "...", "Számla kelte": "YYYY-MM-DD",
      "Teljesítés dátuma": "YYYY-MM-DD", "Fizetési határidő": "YYYY-MM-DD",
      "Kifizetés hónapja": "magyar hónapnév", "Nettó": "szám", "Áfa": "szám",
      "Bruttó": "szám", "Pénznem": "ISO", "Nettó HUF": "szám", "Áfa HUF": "szám", "EUR fx": "szám"
    }
    Szabály: "eufad37" kód esetén Áfa=0. Pénznem csak HUF/EUR.
    """
    
    all_results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(process_invoice, f, prompt, model) for f in uploaded_files]
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            all_results.append(future.result())
            progress_bar.progress((i + 1) / len(uploaded_files))
            status_text.text(f"Feldolgozva: {i+1}/{len(uploaded_files)} számla")

    # --- GOOGLE SHEETS ÍRÁS (ROBUSZTUS VERZIÓ) ---
    try:
        # Itt nyitjuk meg a táblázatot és a füleket!
        spreadsheet = gc.open(SHEET_NAME)
        ws_in = spreadsheet.worksheet("Bejövő")
        ws_out = spreadsheet.worksheet("Kimenő")

        for res in all_results:
            row = [
                res.get("Szállító"), res.get("Számlaszám"), res.get("Számla kelte"),
                res.get("Teljesítés dátuma"), res.get("Fizetési határidő"),
                res.get("Kifizetés hónapja"), res.get("Nettó"), res.get("Áfa"),
                res.get("Bruttó"), res.get("Pénznem"), res.get("Nettó HUF"),
                res.get("Áfa HUF"), res.get("EUR fx")
            ]
            
            # Cél fül kiválasztása a "Realign" név alapján
            target_ws = ws_out if "realign" in str(res.get("Szállító")).lower() else ws_in
            
            # Robusztus sorkeresés
            values = target_ws.get_all_values()
            next_row_index = len(values) + 1
            
            # Adat beillesztése
            target_ws.update(
                range_name=f"A{next_row_index}", 
                values=[row], 
                value_input_option='USER_ENTERED'
            )
        
        # Ide került a siker üzenet (a ciklusból ki)
        st.success(f"✅ Sikeresen rögzítve {len(all_results)} számla a Google Táblázatba!")
        st.balloons()
        
    except Exception as e:
        st.error(f"Hiba a táblázat írásakor: {e}")

    # Megjelenítés a weboldalon
    st.dataframe(pd.DataFrame(all_results))
