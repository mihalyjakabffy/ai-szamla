import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import os
import time

st.set_page_config(page_title="AI Tömeges Számlafeldolgozó", page_icon="🧾", layout="wide")
st.title("🧾 AI Tömeges Számla- és Nyugtafeldolgozó")

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
    selected_model_name = st.sidebar.selectbox("Válassz modellt:", valid_models, index=valid_models.index('gemini-1.5-flash-latest') if 'gemini-1.5-flash-latest' in valid_models else 0)
    model = genai.GenerativeModel(selected_model_name)
except:
    st.error("Hiba az API kulccsal! Ellenőrizd a beírt adatot.")
    st.stop()

# --- FÁJL FELTÖLTÉS (Többszörös kijelölés engedélyezve) ---
uploaded_files = st.file_uploader("Húzd ide a számlákat (többet is kijelölhetsz egyszerre!)", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=True)

if uploaded_files and st.button("Összes fájl feldolgozása"):
    all_extracted_data = [] # Itt gyűjtjük a sorokat
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Végigmegyünk minden egyes feltöltött fájlon
    for index, uploaded_file in enumerate(uploaded_files):
        filename = uploaded_file.name
        status_text.text(f"Feldolgozás alatt ({index+1}/{len(uploaded_files)}): {filename}...")
        
        # Ideiglenes mentés
        temp_path = f"temp_{filename}"
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        try:
            # AI kérés összeállítása
            sample_file = genai.upload_file(path=temp_path)
            
            prompt = """
            Elemezd a csatolt számlát, és nyerd ki az adatokat JSON-ben. 
            Ha valamit nem találsz, írd be: "HIBA: Nem található".
            Formátum:
            {
              "Szállító": "...",
              "Számlaszám": "...",
              "Számla kelte": "YYYY-MM-DD",
              "Számla teljesítésének dátuma": "YYYY-MM-DD",
              "Fizetési határidő": "YYYY-MM-DD",
              "Teljesítés hónapja": "YYYY-MM",
              "Nettó": "...",
              "Áfa": "...",
              "Bruttó": "...",
              "Pénznem": "...",
              "Nettó huf": "...",
              "Áfa huf": "..."
            }
            Csak a JSON-t válaszold!
            """
            
            response = model.generate_content([sample_file, prompt])
            clean_json = response.text.replace('```json', '').replace('```', '').strip()
            data = json.loads(clean_json)
            
            # Hozzáadjuk a fájlnevet is az adatokhoz, hogy beazonosítható legyen
            data["Fájlnév"] = filename
            all_extracted_data.append(data)
            
        except Exception as e:
            # Hiba esetén egy üres sort adunk hozzá hibaüzenettel
            all_extracted_data.append({"Fájlnév": filename, "Szállító": f"HIBA: {str(e)}"})
        
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            # Progress bar frissítése
            progress_bar.progress((index + 1) / len(uploaded_files))
            # Egy pici szünet az API limitek miatt (opcionális)
            time.sleep(1)

    status_text.text("✅ Minden fájl feldolgozva!")

    # Összesített táblázat megjelenítése
    if all_extracted_data:
        full_df = pd.DataFrame(all_extracted_data)
        
        # Oszlopok sorrendjének beállítása (Fájlnév legyen az első)
        cols = ["Fájlnév"] + [c for c in full_df.columns if c != "Fájlnév"]
        full_df = full_df[cols]
        
        st.subheader("Összesített eredmények:")
        st.dataframe(full_df, use_container_width=True)
        
        # Egyetlen közös CSV letöltése
        csv = full_df.to_csv(index=False, sep=';', encoding='utf-8-sig')
        st.download_button(
            label="⬇️ Összesített táblázat letöltése (Excel CSV)",
            data=csv,
            file_name="osszesitett_szamlak.csv",
            mime="text/csv",)
