import streamlit as st
import google.generativeai as genai  # <--- CAMBIADO
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import re

# ─── PAGE CONFIG ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PedidOS",
    page_icon="🛒",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ─── CUSTOM CSS (Se mantiene igual para no perder el diseño) ───────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');
  html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; background-color: #F7F6F2; color: #1A1A18; }
  .app-header { display: flex; align-items: baseline; gap: 10px; margin-bottom: 8px; }
  .app-title { font-family: 'DM Mono', monospace; font-size: 2rem; font-weight: 500; letter-spacing: -1px; color: #1A1A18; }
  .app-sub { font-size: 0.85rem; color: #888; font-weight: 300; }
  .meta-pill { display: inline-flex; gap: 18px; background: #EEECEA; border-radius: 8px; padding: 10px 16px; margin-bottom: 16px; font-size: 0.82rem; color: #555; font-family: 'DM Mono', monospace; }
  .cat-header { font-family: 'DM Mono', monospace; font-size: 0.72rem; font-weight: 500; letter-spacing: 2px; text-transform: uppercase; color: #999; margin: 20px 0 6px 0; border-bottom: 1px solid #E0DED9; padding-bottom: 4px; }
  .product-qty { font-family: 'DM Mono', monospace; font-size: 0.85rem; color: #555; text-align: right; }
  .stButton > button { font-family: 'DM Sans', sans-serif; font-weight: 500; border-radius: 10px; border: none; padding: 14px 24px; width: 100%; }
  .stTextArea textarea { font-family: 'DM Mono', monospace; font-size: 0.85rem; border-radius: 10px; }
  .progress-wrap { background: #E0DED9; border-radius: 99px; height: 6px; margin: 10px 0 20px 0; overflow: hidden; }
  .progress-bar { height: 6px; border-radius: 99px; background: #1A1A18; transition: width 0.3s ease; }
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding-top: 2rem; max-width: 560px; }
</style>
""", unsafe_allow_html=True)

# ─── GEMINI CLIENT (REEMPLAZA A OPENAI) ─────────────────────────────────────────
@st.cache_resource
def get_gemini_model():
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    return genai.GenerativeModel('gemini-1.5-flash')

# ─── GOOGLE SHEETS CLIENT ────────────────────────────────────────────────────────
@st.cache_resource
def get_gspread_client():
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # Usamos el nombre de secreto que ya tienes configurado
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

# ─── AI PROCESSING CON GEMINI ─────────────────────────────────────────────────────
SYSTEM_PROMPT = """
Eres un asistente especializado en procesar pedidos de WhatsApp.
Responde ÚNICAMENTE con JSON válido:
{
  "tienda": "string",
  "emisor": "string",
  "productos": [
    {"categoria": "Carnicería|Frutería|Abarrotes|Insumos", "producto": "nombre", "cantidad": número, "unidad": "kg|pza|lt|gr|caja|bolsa"}
  ]
}
"""

def parse_order(text: str) -> dict:
    model = get_gemini_model()
    # Enviamos el prompt y el texto
    response = model.generate_content(f"{SYSTEM_PROMPT}\n\nProcesa este pedido:\n{text}")
    
    raw = response.text.strip()
    # Limpia el markdown si la IA lo incluye
    raw = re.sub(r"```json|```", "", raw).strip()
    return json.loads(raw)

# ─── EL RESTO DEL CÓDIGO (SAVE_TO_SHEETS Y PANTALLAS) SE MANTIENE IGUAL ─────────
# (Esto asegura que tu diseño de Checklist y Progress Bar siga funcionando)

CATEGORY_ORDER = ["Carnicería", "Frutería", "Abarrotes", "Insumos"]
CATEGORY_EMOJI = {"Carnicería": "🥩", "Frutería": "🥦", "Abarrotes": "🥫", "Insumos": "🧴"}

def save_to_sheets(data: dict, checked: dict):
    try:
        gc = get_gspread_client()
        spreadsheet_id = st.secrets["SPREADSHEET_ID"]
        sh = gc.open_by_key(spreadsheet_id)
        sheet_name = st.secrets.get("SHEET_NAME", "Pedidos")
        
        try:
            ws = sh.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=10)
            ws.append_row(["Fecha", "Tienda", "Emisor", "Categoría", "Producto", "Cantidad", "Unidad", "Recogido"])

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        rows = [[now, data.get("tienda") or "", data.get("emisor") or "", p["categoria"], p["producto"], str(p["cantidad"]), p["unidad"] or "", "Sí" if checked.get(idx, False) else "No"] for idx, p in enumerate(data["productos"])]
        ws.append_rows(rows)
        return True
    except Exception as e:
        st.error(f"Error al guardar: {e}")
        return False

# Lógica de estados y pantallas
if "parsed_data" not in st.session_state: st.session_state.parsed_data = None
if "checked" not in st.session_state: st.session_state.checked = {}
if "saved" not in st.session_state: st.session_state.saved = False

st.markdown('<div class="app-header"><span class="app-title">🛒 PedidOS</span><span class="app-sub">Procesador WhatsApp</span></div>', unsafe_allow_html=True)

if st.session_state.parsed_data is None:
    whatsapp_text = st.text_area("Mensaje de WhatsApp", height=220, label_visibility="collapsed")
    if st.button("✨  Generar Lista", type="primary", use_container_width=True):
        if whatsapp_text.strip():
            with st.spinner("IA procesando gratis..."):
                result = parse_order(whatsapp_text)
                st.session_state.parsed_data = result
                st.session_state.checked = {i: False for i in range(len(result["productos"]))}
                st.rerun()
else:
    # (Aquí va la lógica de la Checklist que ya tenías, se mantiene íntegra)
    data = st.session_state.parsed_data
    checked = st.session_state.checked
    total = len(data["productos"])
    done = sum(1 for v in checked.values() if v)
    
    st.markdown(f'<div class="meta-pill"><span>🏪 Tienda <strong>{data.get("tienda") or "—"}</strong></span><span>👤 <strong>{data.get("emisor") or "—"}</strong></span><span>📦 <strong>{done}/{total}</strong></span></div>', unsafe_allow_html=True)
    
    pct = int(done / total * 100) if total > 0 else 0
    st.markdown(f'<div class="progress-wrap"><div class="progress-bar" style="width:{pct}%"></div></div>', unsafe_allow_html=True)

    cats = {}
    for idx, p in enumerate(data["productos"]): cats.setdefault(p["categoria"], []).append((idx, p))

    for cat in CATEGORY_ORDER:
        if cat in cats:
            st.markdown(f'<div class="cat-header">{CATEGORY_EMOJI.get(cat, "")} {cat}</div>', unsafe_allow_html=True)
            for idx, p in cats[cat]:
                col1, col2 = st.columns([3, 1])
                with col1:
                    if st.checkbox(p["producto"], value=checked.get(idx, False), key=f"c_{idx}"):
                        st.session_state.checked[idx] = True
                with col2:
                    st.markdown(f'<div class="product-qty">{p["cantidad"] or ""} {p["unidad"] or ""}</div>', unsafe_allow_html=True)

    if st.button("✅ Finalizar y Guardar", type="primary"):
        if save_to_sheets(data, st.session_state.checked):
            st.success("Guardado!")
            st.session_state.parsed_data = None
            st.rerun()
