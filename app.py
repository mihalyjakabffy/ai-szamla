import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import os
import concurrent.futures
import gspread
import re
import uuid
from google.oauth2.service_account import Credentials
from google.api_core.exceptions import GoogleAPIError
import google.auth.exceptions

st.set_page_config(page_title="Realign AI Számlakezelő", page_icon="📊", layout="wide")
st.title("🚀 Realign Számlakezelő AI -> Google Sheets Integráció")

# --- BEÁLLÍTÁSOK ---
st.sidebar.header("⚙️ Beállítások")
API_KEY = st.sidebar.text_input("Gemini API kulcs:", type="password")

if not API_KEY:
    st.warning("Kérlek, add meg az API kulcsodat a folytatáshoz!")
    st.stop()

# AI inicializálás
genai.configure(api_key=API_KEY)

# --- GOOGLE SHEETS CSATLAKOZÁS ÉS FÁJLLISTA ---
try:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    gc = gspread.authorize(creds)
    
    # Elérhető táblázatok lekérése a legördülő menühöz
    available_sheets = gc.list_spreadsheet_files()
    sheet_names = [s['name'] for s in available_sheets]
    
    if not sheet_names:
        st.sidebar.error("Nem található megosztott táblázat a Service Accounttal!")
        st.stop()
    
    SHEET_NAME = st.sidebar.selectbox("📁 Válaszd ki a Google Táblázatot:", sheet_names)

    # --- ENGINE (MODELL) VÁLASZTÓ ---
    valid_models = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    alap_index = valid_models.index('gemini-1.5-flash-latest') if 'gemini-1.5-flash-latest' in valid_models else 0
    selected_model_name = st.sidebar.selectbox("🤖 AI Modell (Engine):", valid_models, index=alap_index)
    model = genai.GenerativeModel(selected_model_name)

except google.auth.exceptions.GoogleAuthError as e:
    st.error(f"Hitelesítési hiba a Google felé. Ellenőrizd a JSON kulcsot! (Részletek: {e})")
    st.stop()
except gspread.exceptions.APIError as e:
    st.error(f"Google API Hiba (pl. nincs engedélyezve a Drive/Sheets API a Cloud Console-ban): {e}")
    st.stop()
except Exception as e:
    st.error(f"Váratlan hiba a Google-kapcsolat vagy a fájllista lekérése során: {e}")
    st.stop()

# --- FELTÖLTÉS ---
uploaded_files = st.file_uploader("Számlák feltöltése (PDF, JPG, PNG)", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=True)

# --- ADATTÍPUS TISZTÍTÓ FÜGGVÉNY ---
def clean_number(val, to_float=False):
    """Megtisztítja a szöveges számokat (pl. '10 000 Ft', '1.234,50', '€ 100') igazi számmá."""
    if val is None:
        return ""
    val_str = str(val).strip()
    if not val_str or val_str.upper() in ["HIBA: NEM TALÁLHATÓ", "NONE", "NULL", "-", "HIBA"]:
        return ""
    
    # JAVÍTÁS: Szigorú szűrés, csak a számjegyeket, pontot, vesszőt és mínuszt hagyjuk meg.
    # Ez eltüntet minden valutajelet (Ft, EUR, $, €) és rejtett szóközt is.
    val_str = re.sub(r'[^\d.,-]', '', val_str)
    
    # Okos tizedesjel felismerés
    if '.' in val_str and ',' in val_str:
        if val_str.rfind(',') > val_str.rfind('.'): # pl. 1.234,56
            val_str = val_str.replace('.', '').replace(',', '.')
        else: # pl. 1,234.56
            val_str = val_str.replace(',', '')
    elif ',' in val_str:
        parts = val_str.split(',')
        if len(parts) == 2 and len(parts[1]) == 3: # valószínűleg ezres elválasztó (pl 123,456)
            val_str = val_str.replace(',', '')
        else:
            val_str = val_str.replace(',', '.') # tizedesvessző
            
    try:
        num = float(val_str)
        if to_float:
            return num
        else:
            return int(round(num)) # Egész számra kerekítjük az összegeket
    except ValueError:
        return val # Ha valamiért mégis szöveg maradna, visszaadjuk eredetiben

# --- BIZTONSÁGOS FELDOLGOZÓ FÜGGVÉNY ---
def process_invoice(uploaded_file, prompt, model):
    filename = uploaded_file.name
    # JAVÍTÁS: Egyedi azonosító generálása a versenyhelyzet (race condition) elkerülésére
    unique_id = uuid.uuid4().hex[:8]
    temp_path = f"temp_{unique_id}_{filename}"
    sample_file = None 
    
    try:
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        sample_file = genai.upload_file(path=temp_path)
        
        # --- BIZTONSÁGOS JSON KIKÉNYSZERÍTÉS API SZINTEN ---
        response = model.generate_content(
            [sample_file, prompt],
            generation_config={"response_mime_type": "application/json"}
        )
        
        try:
            return json.loads(response.text)
        except json.JSONDecodeError:
            return {"Szállító": f"HIBA: Érvénytelen JSON formátumot küldött az AI. Fájl: {filename}"}
        except GoogleAPIError as api_err:
            return {"Szállító": f"HIBA: AI szolgáltatás hiba (pl. túlterheltség). Fájl: {filename} - {api_err}"}
        except OSError as os_err:
            return {"Szállító": f"HIBA: Fájl írási/olvasási hiba. Fájl: {filename} - {os_err}"}
            
    except Exception as e:
        return {"Szállító": f"HIBA (Váratlan): {filename} - {str(e)}"}
        
    finally:
        # Helyi és felhős takarítás
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except: pass
        if sample_file:
            try: genai.delete_file(sample_file.name)
            except: pass

if uploaded_files and st.button("Feldolgozás és Mentés a Google Táblázatba"):
    prompt = """
    Elemezd a számlát és adj JSON választ:
    {
      "Szállító": "...", "Vevő": "...", "Számlaszám": "...", "Számla kelte": "YYYY-MM-DD",
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

    # --- KÖTEGELT (BATCH) GOOGLE SHEETS ÍRÁS TISZTÍTOTT ADATOKKAL ---
    try:
        spreadsheet = gc.open(SHEET_NAME)
        ws_in = spreadsheet.worksheet("Bejövő")
        ws_out = spreadsheet.worksheet("Kimenő")

        incoming_rows = []
        outgoing_rows = []

        # 1. Adatok tisztítása és szétválogatása
        for res in all_results:
            is_outgoing = "realign" in str(res.get("Szállító", "")).lower()
            
            # Tisztítjuk a numerikus mezőket
            netto = clean_number(res.get("Nettó"))
            afa = clean_number(res.get("Áfa"))
            brutto = clean_number(res.get("Bruttó"))
            netto_huf = clean_number(res.get("Nettó HUF"))
            afa_huf = clean_number(res.get("Áfa HUF"))
            eur_fx = clean_number(res.get("EUR fx"), to_float=True)
            
            if is_outgoing:
                row = [
                    "", "", "", "", res.get("Vevő", ""), res.get("Számlaszám", ""), 
                    "", res.get("Számla kelte", ""), res.get("Teljesítés dátuma", ""), 
                    res.get("Fizetési határidő", ""), "", "", res.get("Kifizetés hónapja", ""), 
                    netto, afa, brutto, res.get("Pénznem", ""), netto_huf, afa_huf, 
                    "", eur_fx
                ]
                outgoing_rows.append(row)
            else:
                row = [
                    "", "", "", "", res.get("Szállító", ""), res.get("Számlaszám", ""), 
                    "", "", res.get("Számla kelte", ""), res.get("Teljesítés dátuma", ""), 
                    res.get("Fizetési határidő", ""), "", "", res.get("Kifizetés hónapja", ""), 
                    netto, afa, brutto, res.get("Pénznem", ""), netto_huf, afa_huf, 
                    "", eur_fx
                ]
                incoming_rows.append(row)

        # JAVÍTÁS: get_all_values() helyett col_values(1) használata a villámgyors és memóriakímélő futásért
        # 2. Bejövő adatok EGYBEN történő kiírása
        if incoming_rows:
            next_row_index_in = len(ws_in.col_values(1)) + 1
            ws_in.update(
                range_name=f"A{next_row_index_in}", 
                values=incoming_rows, 
                value_input_option='USER_ENTERED'
            )

        # 3. Kimenő adatok EGYBEN történő kiírása
        if outgoing_rows:
            next_row_index_out = len(ws_out.col_values(1)) + 1
            ws_out.update(
                range_name=f"A{next_row_index_out}", 
                values=outgoing_rows, 
                value_input_option='USER_ENTERED'
            )
        
        st.success(f"✅ Sikeresen rögzítve {len(all_results)} számla a '{SHEET_NAME}' táblázatba!")
        st.balloons()
        
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Hiba: A '{SHEET_NAME}' nevű táblázat nem található! Ellenőrizd a megosztást a Service Accounttal.")
    except gspread.exceptions.WorksheetNotFound as e:
        st.error(f"Hiba: Hiányzó munkalap! A táblázatban lennie kell 'Bejövő' és 'Kimenő' fülnek. (Részletek: {e})")
    except gspread.exceptions.APIError as e:
        st.error(f"Google Sheets API hiba írás közben (pl. túl sok kérés vagy kvóta túllépés): {e}")
    except Exception as e:
        st.error(f"Váratlan hiba a táblázat írásakor: {e}")

    # Megjelenítés a weboldalon
    st.dataframe(pd.DataFrame(all_results))
