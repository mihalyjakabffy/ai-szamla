import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import os
import concurrent.futures
import io

st.set_page_config(page_title="Számla Mester", page_icon="🚀", layout="wide")
st.title("Realign-Számlafeldolgozó")

# --- OLDALSÁV: BEÁLLÍTÁSOK ---
st.sidebar.header("⚙️ Beállítások")
API_KEY = st.sidebar.text_input("Gemini API kulcs:", type="password")

if not API_KEY:
    st.warning("Kérlek, add meg az API kulcsodat a bal oldali menüsávban!")
    st.stop()

genai.configure(api_key=API_KEY)

# Modell választó
try:
    valid_models = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    alap_index = valid_models.index('gemini-1.5-flash-latest') if 'gemini-1.5-flash-latest' in valid_models else 0
    selected_model_name = st.sidebar.selectbox("AI Modell:", valid_models, index=alap_index)
    model = genai.GenerativeModel(selected_model_name)
except:
    st.error("Hiba az API kulccsal! Ellenőrizd a beírt adatot.")
    st.stop()

# --- FŐOLDAL LÉPÉSEI ---

# 1. LÉPÉS: Mester fájl (Opcionális)
st.subheader("1. Lépés: Meglévő táblázat betöltése (Opcionális)")
master_file = st.file_uploader("A meglévő könyvelési táblázatod itt töltsd fel (.xlsx)", type=["xlsx"])
if master_file:
    st.success("Mester táblázat betöltve. Az új számlák ennek az aljára fognak kerülni.")

# 2. LÉPÉS: Új számlák
st.subheader("2. Lépés: Új számlák feltöltése")
uploaded_files = st.file_uploader("Húzd ide az új számlákat (akár többet is egyszerre)", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=True)

# --- FELDOLGOZÓ FÜGGVÉNY (PÁRHUZAMOS FUTTATÁSHOZ) ---
def process_invoice(uploaded_file, prompt, model):
    filename = uploaded_file.name
    temp_path = f"temp_{filename}"
    try:
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        sample_file = genai.upload_file(path=temp_path)
        response = model.generate_content([sample_file, prompt])
        
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(clean_json)
        data["Fájlnév"] = filename
        return data
    except Exception as e:
        return {"Fájlnév": filename, "Szállító": f"HIBA: {str(e)}"}
    finally:
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except: pass

# --- INDÍTÁS ---
if uploaded_files and st.button("Feldolgozás és Összefűzés indítása"):
    all_new_rows = []
    
    prompt = """
    Elemezd a számlát és adj JSON választ. Ha valami hiányzik: "HIBA: Nem található".
    Mezők:
    {
      "Szállító": "...", "Számlaszám": "...", "Számla kelte": "YYYY-MM-DD",
      "Számla teljesítésének dátuma": "YYYY-MM-DD", "Fizetési határidő": "YYYY-MM-DD",
      "Teljesítés hónapja": "magyar hónapnév kisbetűvel", "Nettó": "szám", "Áfa": "szám",
      "Bruttó": "szám", "Pénznem": "3 betűs ISO (HUF/EUR)", "Nettó huf": "szám", "Áfa huf": "szám"
    }
    Szabályok: Teljesítés hónapja csak a hónap neve legyen (pl. január). Pénznemnél tilos a Ft/€ jel, csak HUF/EUR.
    """
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Turbó mód: egyszerre 3 szálon
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_invoice, f, prompt, model): f for f in uploaded_files}
        
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            result = future.result()
            all_new_rows.append(result)
            progress_bar.progress((i + 1) / len(uploaded_files))
            status_text.text(f"Kész: {i+1}/{len(uploaded_files)} fájl")

    # ADATOK ÖSSZEFŰZÉSE
    new_df = pd.DataFrame(all_new_rows)
    # Oszlopok sorrendje
    cols = ["Fájlnév"] + [c for c in new_df.columns if c != "Fájlnév"]
    new_df = new_df[cols]

    if master_file:
        try:
            old_df = pd.read_excel(master_file)
            final_df = pd.concat([old_df, new_df], ignore_index=True)
            st.info("Az új adatokat hozzáfűztük a feltöltött mester táblázathoz.")
        except Exception as e:
            st.error(f"Hiba a mester fájl beolvasásakor: {e}")
            final_df = new_df
    else:
        final_df = new_df
        st.warning("Nem töltöttél fel mester fájlt, így csak az új adatokat tartalmazza a táblázat.")

    # MEGJELENÍTÉS
    st.subheader("📊 Összesített táblázat")
    st.dataframe(final_df, use_container_width=True)

    # EXCEL GENERÁLÁS (XLSX)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        final_df.to_excel(writer, index=False, sheet_name='Számlák')
    
    st.download_button(
        label="⬇️ Frissített Mester Excel letöltése (.xlsx)",
        data=output.getvalue(),
        file_name="frissitett_konyveles.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    st.success("Kész! Töltsd le a fájlt és nyisd meg Excelben.")
