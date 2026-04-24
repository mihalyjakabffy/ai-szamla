import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import os
import concurrent.futures

st.set_page_config(page_title="AI Tömeges Számlafeldolgozó", page_icon="⚡", layout="wide")
st.title("⚡ AI Tömeges Számla- és Nyugtafeldolgozó (Turbó mód)")

# --- API KULCS BEKÉRÉSE ---
st.sidebar.header("Beállítások")
API_KEY = st.sidebar.text_input("Gemini API kulcs:", type="password")

if not API_KEY:
    st.warning("Kérlek, add meg az API kulcsodat a bal oldali menüsávban!")
    st.stop()

genai.configure(api_key=API_KEY)

# --- MODELL VÁLASZTÓ ---
try:
    valid_models = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    if valid_models:
        alap_index = valid_models.index('gemini-1.5-flash-latest') if 'gemini-1.5-flash-latest' in valid_models else 0
        selected_model_name = st.sidebar.selectbox("Válassz modellt:", valid_models, index=alap_index)
        model = genai.GenerativeModel(selected_model_name)
    else:
        st.error("Nincs engedélyezett modell.")
        st.stop()
except Exception:
    st.error("Hiba az API kulccsal! Ellenőrizd a beírt adatot.")
    st.stop()

# --- FÜGGVÉNY EGYETLEN SZÁMLA FELDOLGOZÁSÁHOZ ---
# Ezt fogja a gép egyszerre több szálon futtatni
def process_single_invoice(uploaded_file, prompt, model):
    filename = uploaded_file.name
    temp_path = f"temp_{filename}"
    
    try:
        # Fájl kimentése
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        # Küldés az AI-nak
        sample_file = genai.upload_file(path=temp_path)
        response = model.generate_content([sample_file, prompt])
        
        # JSON tisztítás
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(clean_json)
        data["Fájlnév"] = filename
        return data
        
    except Exception as e:
        return {"Fájlnév": filename, "Szállító": f"HIBA: {str(e)}"}
        
    finally:
        # Takarítás: töröljük a fájlt, amint végzett vele
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

# --- FÁJL FELTÖLTÉS ---
uploaded_files = st.file_uploader("Húzd ide a számlákat (többet is kijelölhetsz egyszerre!)", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=True)

if uploaded_files and st.button("Összes fájl feldolgozása"):
    all_extracted_data = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    prompt = """
    Elemezd a csatolt számlát, és nyerd ki az adatokat JSON-ben. 
    Ha valamit nem találsz, írd be: "HIBA: Nem található".
    Formátum:
    {
      "Szállító": "...", "Számlaszám": "...", "Számla kelte": "YYYY-MM-DD",
      "Számla teljesítésének dátuma": "YYYY-MM-DD", "Fizetési határidő": "YYYY-MM-DD",
      "Teljesítés hónapja": "YYYY-MM", "Nettó": "...", "Áfa": "...",
      "Bruttó": "...", "Pénznem": "...", "Nettó huf": "...", "Áfa huf": "..."
    }
    Csak a JSON-t válaszold!
    """
    
    status_text.text("🚀 Párhuzamos feldolgozás indítása...")
    
    # --- PÁRHUZAMOSÍTÁS (MULTITHREADING) ---
    # max_workers=3 : Egyszerre 3 fájlt dolgoz fel. Ezt ne vedd sokkal feljebb az ingyenes limit miatt!
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        # Elindítjuk az összes feladatot a háttérben
        jovabagyott_feladatok = {executor.submit(process_single_invoice, file, prompt, model): file for file in uploaded_files}
        
        kesz_darab = 0
        # Ahogy egy-egy szál végez, egyből frissítjük a felületet
        for future in concurrent.futures.as_completed(jovabagyott_feladatok):
            eredmeny = future.result()
            all_extracted_data.append(eredmeny)
            
            kesz_darab += 1
            progress_bar.progress(kesz_darab / len(uploaded_files))
            status_text.text(f"Feldolgozva: {kesz_darab}/{len(uploaded_files)} fájl...")

    status_text.text("✅ Minden fájl feldolgozva!")

    # --- ÖSSZESÍTÉS ÉS LETÖLTÉS ---
    if all_extracted_data:
        full_df = pd.DataFrame(all_extracted_data)
        cols = ["Fájlnév"] + [c for c in full_df.columns if c != "Fájlnév"]
        full_df = full_df[cols]
        
        st.subheader("Összesített eredmények:")
        st.dataframe(full_df, use_container_width=True)
        
        csv = full_df.to_csv(index=False, sep=';', encoding='utf-8-sig')
        st.download_button(
            label="⬇️ Összesített táblázat letöltése (Excel CSV)",
            data=csv,
            file_name="osszesitett_szamlak_turbo.csv",
            mime="text/csv",
        )
