import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import os

st.set_page_config(page_title="AI Számla Feldolgozó", page_icon="🧾", layout="wide")
st.title("🧾 AI Számla- és Nyugtafeldolgozó")

st.info("A használathoz szükség van egy Google Gemini API kulcsra.")
API_KEY = st.text_input("Írd be az API kulcsodat:", type="password")

if not API_KEY:
    st.warning("Kérlek, add meg az API kulcsodat a folytatáshoz!")
    st.stop()

# --- AI Konfiguráció és Modell Választó ---
genai.configure(api_key=API_KEY)

try:
    valid_models = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    if valid_models:
        alap_index = valid_models.index('gemini-1.5-flash-latest') if 'gemini-1.5-flash-latest' in valid_models else 0
        selected_model = st.selectbox("🤖 Elérhető AI modellek a fiókodban:", valid_models, index=alap_index)
        model = genai.GenerativeModel(selected_model)
    else:
        st.error("Nem található engedélyezett modell ehhez az API kulcshoz!")
        st.stop()
except Exception as e:
    st.error("❌ Érvénytelen API kulcs! Kérlek, ellenőrizd, hogy helyesen másoltad-e be.")
    st.stop()

# --- Fájl feltöltés ---
uploaded_file = st.file_uploader("Húzd ide a számlát (PDF, JPG, PNG)", type=["pdf", "jpg", "jpeg", "png"])

if uploaded_file and st.button("Adatok kinyerése"):
    with st.spinner("AI elemzés folyamatban..."):
        temp_path = f"temp_{uploaded_file.name}"
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        try:
            sample_file = genai.upload_file(path=temp_path)
            
            # --- ÚJ, RÉSZLETES PROMPT ---
            prompt = """
            Elemezd a csatolt számlát, és nyerd ki belőle a következő adatokat pontosan ebben a JSON formátumban:
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
            
            Szigorú szabályok:
            1. Csak és kizárólag a tisztított JSON objektumot válaszold, semmi más magyarázatot!
            2. Ha egy adat egyértelműen NEM szerepel a számlán (nem látod), akkor az értékhez írd be pontosan ezt: "HIBA: Nem található". Kérlek, ne találgass!
            3. A számoknál tizedespontot használj, és a számok mellé ne írj pénznemet (azt kizárólag a 'Pénznem' mezőbe tedd).
            """
            
            response = model.generate_content([sample_file, prompt])
            
            # Tisztítás és betöltés
            clean_json = response.text.replace('```json', '').replace('```', '').strip()
            adatok = json.loads(clean_json)
            
            # Táblázat generálása
            df = pd.DataFrame([adatok])
            
            st.subheader("Kinyert adatok:")
            st.dataframe(df, use_container_width=True)
            
            # CSV Letöltés gomb
            csv = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
            st.download_button(
                label="⬇️ Részletes CSV letöltése Excelhez",
                data=csv,
                file_name="reszletes_szamla_adatok.csv",
                mime="text/csv",
            )
            
        except json.JSONDecodeError:
            st.error("❌ Az AI nem megfelelő formátumban adta vissza az adatokat. Próbáld újra!")
        except Exception as e:
            st.error(f"❌ Hiba történt a feldolgozás során: {e}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
