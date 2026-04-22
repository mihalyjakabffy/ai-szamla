import streamlit as st
import google.generativeai as genai
import json
import pandas as pd

# --- Konfiguráció ---
API_KEY = "AIzaSyCWueguN9IHgoDq06T2HakkXw9A68BL6jU" # Ezt pótold!
genai.configure(api_key=API_KEY)

# --- DINAMIKUS MODELL LEKÉRDEZÉS ---
# Lekérjük az összes modellt, amit a te kulcsoddal használni lehet
valid_models = []
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        # A 'models/' előtagot levágjuk, hogy szebben mutasson a weblapon
        valid_models.append(m.name.replace('models/', ''))

# --- Felület beállításai ---
st.set_page_config(page_title="AI Számlafeldolgozó", page_icon="🧾")
st.title("🧾 AI Számla- és Nyugtafeldolgozó")

# ÚJ FUNKCIÓ: Legördülő menü a weboldalon a választható modellekkel
if valid_models:
    selected_model = st.selectbox("🤖 Elérhető AI modellek a fiókodban:", valid_models)
    model = genai.GenerativeModel(selected_model)
else:
    st.error("Nem található engedélyezett modell ehhez az API kulcshoz!")

st.write("Töltsd fel a számládat, és a rendszer automatikusan kinyeri az adatokat CSV formátumba!")

# --- Fájl feltöltő (Drag & Drop) ---
uploaded_file = st.file_uploader("Húzd ide a számlát (PDF, JPG, PNG)", type=["pdf", "jpg", "jpeg", "png"])
if uploaded_file is not None:
    st.success("Fájl sikeresen feltöltve!")
    
    if st.button("Adatok kinyerése"):
        with st.spinner("Az AI elemzi a számlát. Kérlek várj..."):
            
            # Fájl elmentése ideiglenesen
            temp_path = f"temp_{uploaded_file.name}"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
                
            # Fájl küldése az AI-nak
            try:
                sample_file = genai.upload_file(path=temp_path)
                
                prompt = """
                Te egy profi könyvelő asszisztens vagy. Kérlek, elemezd a csatolt számlát, 
                és nyerd ki belőle a következő adatokat pontosan ebben a JSON formátumban:
                {
                    "szamlaszam": "...",
                    "kiallitas_datuma": "YYYY-MM-DD",
                    "hatarido": "YYYY-MM-DD",
                    "szallito_neve": "...",
                    "netto_osszeg": 0,
                    "afa_osszeg": 0,
                    "brutto_osszeg": 0
                }
                Csak a JSON-t add vissza! Számoknál ne használj pénznemet.
                """
                
                response = model.generate_content([sample_file, prompt])
                response_text = response.text.replace('```json', '').replace('```', '').strip()
                
                # JSON konvertálása Táblázattá (Pandas DataFrame)
                invoice_data = json.loads(response_text)
                df = pd.DataFrame([invoice_data])
                
                st.subheader("Kinyert adatok:")
                st.dataframe(df) # Megjelenítjük a táblázatot a weblapon
                
                # CSV letöltés gomb generálása
                csv = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
                st.download_button(
                    label="⬇️ CSV letöltése Excelhez",
                    data=csv,
                    file_name="szamla_adatok.csv",
                    mime="text/csv",
                )
                
            except Exception as e:
                st.error(f"Hiba történt a feldolgozás során: {e}")
            
            finally:
                import os
                if os.path.exists(temp_path):
                    os.remove(temp_path)