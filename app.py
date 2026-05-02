import streamlit as st
import openai
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

# ─── CUSTOM CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');

  html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    background-color: #F7F6F2;
    color: #1A1A18;
  }

  /* Header */
  .app-header {
    display: flex;
    align-items: baseline;
    gap: 10px;
    margin-bottom: 8px;
  }
  .app-title {
    font-family: 'DM Mono', monospace;
    font-size: 2rem;
    font-weight: 500;
    letter-spacing: -1px;
    color: #1A1A18;
  }
  .app-sub {
    font-size: 0.85rem;
    color: #888;
    font-weight: 300;
  }

  /* Meta info pill */
  .meta-pill {
    display: inline-flex;
    gap: 18px;
    background: #EEECEA;
    border-radius: 8px;
    padding: 10px 16px;
    margin-bottom: 16px;
    font-size: 0.82rem;
    color: #555;
    font-family: 'DM Mono', monospace;
  }
  .meta-pill span strong {
    color: #1A1A18;
  }

  /* Category headers */
  .cat-header {
    font-family: 'DM Mono', monospace;
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: #999;
    margin: 20px 0 6px 0;
    border-bottom: 1px solid #E0DED9;
    padding-bottom: 4px;
  }

  /* Product rows */
  .product-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px dashed #EEECEA;
  }
  .product-name {
    flex: 2;
    font-weight: 500;
    font-size: 0.95rem;
  }
  .product-qty {
    flex: 1;
    font-family: 'DM Mono', monospace;
    font-size: 0.85rem;
    color: #555;
    text-align: right;
  }
  .product-done {
    text-decoration: line-through;
    color: #BBB !important;
  }

  /* Buttons */
  .stButton > button {
    font-family: 'DM Sans', sans-serif;
    font-weight: 500;
    border-radius: 10px;
    border: none;
    padding: 14px 24px;
    font-size: 1rem;
    cursor: pointer;
    transition: all 0.15s ease;
    width: 100%;
  }
  .stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.12);
  }

  /* Textarea */
  .stTextArea textarea {
    font-family: 'DM Mono', monospace;
    font-size: 0.85rem;
    background: #FFFFFF;
    border: 1.5px solid #E0DED9;
    border-radius: 10px;
    color: #1A1A18;
    line-height: 1.6;
  }
  .stTextArea textarea:focus {
    border-color: #1A1A18 !important;
    box-shadow: none !important;
  }

  /* Progress bar */
  .progress-wrap {
    background: #E0DED9;
    border-radius: 99px;
    height: 6px;
    margin: 10px 0 20px 0;
    overflow: hidden;
  }
  .progress-bar {
    height: 6px;
    border-radius: 99px;
    background: #1A1A18;
    transition: width 0.3s ease;
  }

  /* Hide streamlit chrome */
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding-top: 2rem; max-width: 560px; }

  /* Divider */
  hr { border: none; border-top: 1.5px solid #E0DED9; margin: 20px 0; }

  /* Error / info */
  .stAlert { border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# ─── OPENAI CLIENT ───────────────────────────────────────────────────────────────
@st.cache_resource
def get_openai_client():
    return openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ─── GOOGLE SHEETS CLIENT ────────────────────────────────────────────────────────
@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

# ─── AI PROCESSING ───────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
Eres un asistente especializado en procesar pedidos de abarrotes enviados por WhatsApp.

REGLAS DE MAPEO ESPECIALES:
- "br7" → "Bisteck del 7"
- "br0" o "br00" → "Bisteck del cero"
- "p" (como conector) → "para"
- Abreviaturas de unidades: "k" o "kg" → "kg", "pz" o "pza" → "pza", "lt" o "l" → "lt", "gr" → "gr", "cj" → "caja", "bl" → "bolsa"

CATEGORÍAS DISPONIBLES:
- Carnicería: carnes, bisteck, pollo, cerdo, res, etc.
- Frutería: frutas, verduras, vegetales, etc.
- Abarrotes: enlatados, granos, cereales, bebidas, lácteos, etc.
- Insumos: papel, bolsas, desechables, limpieza, etc.

INSTRUCCIONES:
1. Extrae el número de tienda (puede ser un número como #5, tienda 3, etc.)
2. Extrae el nombre del emisor (quien envió el pedido)
3. Para cada producto, identifica: nombre limpio, cantidad numérica, unidad
4. Si dice "6 k 0944", el producto es "0944", cantidad 6, unidad kg
5. Asigna la categoría más apropiada a cada producto
6. Si no puedes determinar cantidad o unidad, usa null

Responde ÚNICAMENTE con JSON válido, sin markdown ni texto extra:
{
  "tienda": "string o null",
  "emisor": "string o null",
  "productos": [
    {
      "categoria": "Carnicería|Frutería|Abarrotes|Insumos",
      "producto": "nombre limpio del producto",
      "cantidad": número o null,
      "unidad": "kg|pza|lt|gr|caja|bolsa|null"
    }
  ]
}
"""

def parse_order(text: str) -> dict:
    client = get_openai_client()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Procesa este pedido:\n\n{text}"},
        ],
        temperature=0.1,
        max_tokens=2000,
    )
    raw = response.choices[0].message.content.strip()
    # Limpia posibles backticks
    raw = re.sub(r"```json|```", "", raw).strip()
    return json.loads(raw)

# ─── GOOGLE SHEETS SAVE ──────────────────────────────────────────────────────────
CATEGORY_ORDER = ["Carnicería", "Frutería", "Abarrotes", "Insumos"]
CATEGORY_EMOJI = {
    "Carnicería": "🥩",
    "Frutería": "🥦",
    "Abarrotes": "🥫",
    "Insumos": "🧴",
}

def save_to_sheets(data: dict, checked: dict):
    try:
        gc = get_gspread_client()
        sheet_name = st.secrets.get("SHEET_NAME", "Pedidos")
        spreadsheet_id = st.secrets["SPREADSHEET_ID"]
        sh = gc.open_by_key(spreadsheet_id)
        try:
            ws = sh.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=10)
            ws.append_row(["Fecha", "Tienda", "Emisor", "Categoría", "Producto", "Cantidad", "Unidad", "Recogido"])

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        rows = []
        for idx, p in enumerate(data["productos"]):
            rows.append([
                now,
                data.get("tienda") or "",
                data.get("emisor") or "",
                p["categoria"],
                p["producto"],
                str(p["cantidad"]) if p["cantidad"] is not None else "",
                p["unidad"] or "",
                "Sí" if checked.get(idx, False) else "No",
            ])
        ws.append_rows(rows)
        return True
    except Exception as e:
        st.error(f"Error al guardar en Google Sheets: {e}")
        return False

# ─── SESSION STATE INIT ──────────────────────────────────────────────────────────
if "parsed_data" not in st.session_state:
    st.session_state.parsed_data = None
if "checked" not in st.session_state:
    st.session_state.checked = {}
if "saved" not in st.session_state:
    st.session_state.saved = False

# ─── HEADER ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
  <span class="app-title">🛒 PedidOS</span>
  <span class="app-sub">Procesador de pedidos WhatsApp</span>
</div>
""", unsafe_allow_html=True)

# ─── SCREEN A: INPUT ─────────────────────────────────────────────────────────────
if st.session_state.parsed_data is None:
    st.markdown("<p style='color:#888;font-size:0.85rem;margin-bottom:12px'>Pega el mensaje de WhatsApp y toca <strong>Generar Lista</strong></p>", unsafe_allow_html=True)

    sample = """Tienda #7 - Juan Pérez
br7 3 k
br0 5 k
0944 6 k
jitomate 4 k
aguacate 2 k
frijol negro 3 k
aceite 2 lt
papel de baño 2 cj"""

    whatsapp_text = st.text_area(
        label="Mensaje de WhatsApp",
        placeholder=sample,
        height=220,
        label_visibility="collapsed",
    )

    if st.button("✨  Generar Lista", type="primary", use_container_width=True):
        if not whatsapp_text.strip():
            st.warning("Por favor pega un mensaje primero.")
        else:
            with st.spinner("Procesando con IA..."):
                try:
                    result = parse_order(whatsapp_text)
                    st.session_state.parsed_data = result
                    st.session_state.checked = {i: False for i in range(len(result["productos"]))}
                    st.session_state.saved = False
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al procesar: {e}")

# ─── SCREEN B: CHECKLIST ─────────────────────────────────────────────────────────
else:
    data = st.session_state.parsed_data
    checked = st.session_state.checked
    total = len(data["productos"])
    done = sum(1 for v in checked.values() if v)

    # Meta pill
    tienda = data.get("tienda") or "—"
    emisor = data.get("emisor") or "—"
    st.markdown(f"""
    <div class="meta-pill">
      <span>🏪 Tienda <strong>{tienda}</strong></span>
      <span>👤 <strong>{emisor}</strong></span>
      <span>📦 <strong>{done}/{total}</strong></span>
    </div>
    """, unsafe_allow_html=True)

    # Progress bar
    pct = int(done / total * 100) if total > 0 else 0
    st.markdown(f"""
    <div class="progress-wrap">
      <div class="progress-bar" style="width:{pct}%"></div>
    </div>
    """, unsafe_allow_html=True)

    # Group by category
    cats = {}
    for idx, p in enumerate(data["productos"]):
        cat = p["categoria"]
        cats.setdefault(cat, []).append((idx, p))

    for cat in CATEGORY_ORDER:
        if cat not in cats:
            continue
        emoji = CATEGORY_EMOJI.get(cat, "")
        st.markdown(f'<div class="cat-header">{emoji} {cat}</div>', unsafe_allow_html=True)

        for idx, p in cats[cat]:
            col1, col2 = st.columns([3, 1])
            is_checked = checked.get(idx, False)
            style = "product-done" if is_checked else ""
            qty_str = ""
            if p["cantidad"] is not None:
                qty_str = f"{p['cantidad']}"
                if p["unidad"] and p["unidad"] != "null":
                    qty_str += f" {p['unidad']}"

            with col1:
                new_val = st.checkbox(
                    label=p["producto"],
                    value=is_checked,
                    key=f"chk_{idx}",
                )
                if new_val != is_checked:
                    st.session_state.checked[idx] = new_val
                    st.rerun()

            with col2:
                st.markdown(f'<div class="product-qty" style="padding-top:8px">{qty_str}</div>', unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # Action buttons
    col_a, col_b = st.columns(2)

    with col_a:
        if st.button("🔄  Nuevo pedido", use_container_width=True):
            st.session_state.parsed_data = None
            st.session_state.checked = {}
            st.session_state.saved = False
            st.rerun()

    with col_b:
        if not st.session_state.saved:
            if st.button("✅  Finalizar pedido", type="primary", use_container_width=True):
                with st.spinner("Guardando en Google Sheets..."):
                    ok = save_to_sheets(data, checked)
                    if ok:
                        st.session_state.saved = True
                        st.rerun()
        else:
            st.success("✓ Guardado en Sheets")
            if st.button("📋  Otro pedido", use_container_width=True):
                st.session_state.parsed_data = None
                st.session_state.checked = {}
                st.session_state.saved = False
                st.rerun()
