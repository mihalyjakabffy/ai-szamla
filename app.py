import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import os
import concurrent.futures
import io

st.set_page_config(page_title="Számla Mester Pro", page_icon="🧾", layout="wide")
st.title("Realign-Számlafeldolgozó (Export Verzió)")

# --- BEÁLLÍTÁSOK ÉS MODELLVÁLASZTÓ ---
st.sidebar.header("⚙️ Beállítások")
API_KEY = st.sidebar.text_input("Gemini API kulcs:", type="password")

if not API_KEY:
    st.warning("Kérlek, add meg az API kulcsodat a bal oldali menüsávban!")
    st.stop()

genai.configure(api_key=API_KEY)

# --- VISSZATETT MODELLVÁLASZTÓ ---
try:
    valid_models = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    alap_index = valid_models.index('gemini-1.5-flash-latest') if 'gemini-1.5-flash-latest' in valid_models else 0
    selected_model_name = st.sidebar.selectbox("🤖 AI Modell:", valid_models, index=alap_index)
    model = genai.GenerativeModel(selected_model_name)
except Exception as e:
    st.error("Hiba az API kulccsal! Ellenőrizd a beírt adatot.")
    st.stop()

# --- FELTÖLTÉS ---
st.info("💡 A program szétválogatja a számlákat, a letöltött Excelből pedig egy mozdulattal átmásolhatod az adatokat a saját könyvelési táblázatodba.")
uploaded_files = st.file_uploader("Számlák feltöltése", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=True)

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

if uploaded_files and st.button("Feldolgozás Indítása"):
    all_new_rows = []
    prompt = """
    Elemezd a számlát és adj JSON választ. Ha valami hiányzik: "HIBA: Nem található".
    Mezők:
    {
      "Szállító": "...", "Számlaszám": "...", "Számla kelte": "YYYY-MM-DD",
      "Teljesítés dátuma": "YYYY-MM-DD", "Fizetési határidő": "YYYY-MM-DD",
      "Kifizetés hónapja": "magyar hónapnév kisbetűvel", "Nettó": "szám", "Áfa": "szám",
      "Bruttó": "szám", "Pénznem": "3 betűs ISO (HUF/EUR)", "Nettó HUF": "szám", "Áfa HUF": "szám",
      "EUR fx": "szám"
    }
    Szabályok: 
    1. Teljesítés hónapja csak a hónap neve (pl. január). 
    2. Pénznem: HUF vagy EUR.
    3. Ha "eufad37" kód van, Áfa és Áfa huf = 0.
    4. EUR fx: MNB árfolyam ha van.
    """
    
    with st.spinner("Számlák elemzése folyamatban..."):
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(process_invoice, f, prompt, model) for f in uploaded_files]
            all_new_rows = [f.result() for f in concurrent.futures.as_completed(futures)]

    # DataFrame létrehozása
    final_df = pd.DataFrame(all_new_rows)

    # Szétválogatás a Realign kft. alapján
    is_outgoing = final_df['Szállító'].str.contains('Realign', case=False, na=False)
    outgoing_df = final_df[is_outgoing]
    incoming_df = final_df[~is_outgoing]

    st.success("Feldolgozás kész!")
    
    # Képernyős megjelenítés
    tab1, tab2 = st.tabs(["📥 Bejövő számlák", "📤 Kimenő számlák (Realign)"])
    with tab1:
        st.dataframe(incoming_df, use_container_width=True)
    with tab2:
        st.dataframe(outgoing_df, use_container_width=True)

    # Excel generálása memóriába
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if not incoming_df.empty:
            incoming_df.to_excel(writer, index=False, sheet_name='Bejövő')
        if not outgoing_df.empty:
            outgoing_df.to_excel(writer, index=False, sheet_name='Kimenő')

    # Letöltés gomb
    st.download_button(
        label="⬇️ Beillesztésre kész Excel letöltése",
        data=output.getvalue(),
        file_name="feldolgozott_szamlak.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
