import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import os

st.set_page_config(page_title="AI Számla Feldolgozó", page_icon="🧾")
st.title("🧾 AI Számla- és Nyugtafeldolgozó")

# --- BIZTONSÁG: API kulcs bekérése ---
st.info("A használathoz szükség van egy Google Gemini API kulcsra. Ezt a kulcsot a rendszer sehol nem menti el, csak a jelenlegi munkamenetben használja.")
API_KEY = st.text_input("Írd be az API kulcsodat:", type="password")

if not API_KEY:
    st.warning("Kérlek, add meg az API kulcsodat a folytatáshoz!")
    st.stop() # Itt megállítjuk a programot, amíg nincs kulcs

# --- AI Konfiguráció ---
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-flash-latest')

# --- Fájl feltöltés ---
uploaded_file = st.file_uploader("Húzd ide a számlát (PDF, JPG, PNG)", type=["pdf", "jpg", "jpeg", "png"])

if uploaded_file and st.button("Adatok kinyerése"):
    with st.spinner("AI elemzés folyamatban..."):
        temp_path = f"temp_{uploaded_file.name}"
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        try:
            # AI Elemzés
            sample_file = genai.upload_file(path=temp_path)
            prompt = """
            Elemezd a csatolt számlát, és nyerd ki belőle a következő adatokat JSON formátumban:
            {"szamlaszam": "...", "kiallitas_datuma": "YYYY-MM-DD", "szallito_neve": "...", "brutto_osszeg": 0}
            Csak a JSON objektumot válaszd! Számoknál ne használj pénznemet.
            """
            response = model.generate_content([sample_file, prompt])
            
            clean_json = response.text.replace('```json', '').replace('```', '').strip()
            adatok = json.loads(clean_json)
            
            # Táblázat generálása
            df = pd.DataFrame([adatok])
            st.subheader("Kinyert adatok:")
            st.dataframe(df)
            
            # CSV Letöltés gomb
            csv = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
            st.download_button(
                label="⬇️ CSV letöltése Excelhez",
                data=csv,
                file_name="szamla_adatok.csv",
                mime="text/csv",
            )
            
        except Exception as e:
            st.error(f"Hiba történt. Ellenőrizd az API kulcsot! Részletek: {e}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
