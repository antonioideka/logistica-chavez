import streamlit as st
import openai
import json
import gspread
import google.generativeai as genai
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

  /* Provider selector pills */
  .provider-row {
    display: flex;
    gap: 8px;
    margin-bottom: 16px;
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
  .meta-pill span strong { color: #1A1A18; }

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

  /* Product qty */
  .product-qty {
    font-family: 'DM Mono', monospace;
    font-size: 0.85rem;
    color: #555;
    text-align: right;
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

  /* Radio buttons — hide default and style as toggle pills */
  div[data-testid="stRadio"] > label { display: none; }
  div[data-testid="stRadio"] > div {
    display: flex;
    gap: 8px;
    flex-direction: row !important;
  }
  div[data-testid="stRadio"] > div > label {
    display: flex !important;
    align-items: center;
    gap: 6px;
    background: #EEECEA;
    border: 1.5px solid transparent;
    border-radius: 8px;
    padding: 7px 14px;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  div[data-testid="stRadio"] > div > label:has(input:checked) {
    background: #1A1A18;
    color: #F7F6F2;
    border-color: #1A1A18;
  }
  div[data-testid="stRadio"] > div > label > div:first-child { display: none; }

  /* Hide streamlit chrome */
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding-top: 2rem; max-width: 560px; }

  hr { border: none; border-top: 1.5px solid #E0DED9; margin: 20px 0; }
  .stAlert { border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# ─── CONSTANTS ───────────────────────────────────────────────────────────────────
CATEGORY_ORDER = ["Carnicería", "Frutería", "Abarrotes", "Insumos"]
CATEGORY_EMOJI = {
    "Carnicería": "🥩",
    "Frutería": "🥦",
    "Abarrotes": "🥫",
    "Insumos": "🧴",
}

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

# ─── AI CLIENTS ──────────────────────────────────────────────────────────────────
@st.cache_resource
def get_openai_client():
    return openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

@st.cache_resource
def get_gemini_client():
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    return genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            max_output_tokens=2000,
            response_mime_type="application/json",  # fuerza JSON nativo
        ),
        system_instruction=SYSTEM_PROMPT,
    )

# ─── PARSE ORDER ─────────────────────────────────────────────────────────────────
def parse_order_openai(text: str) -> dict:
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
    raw = re.sub(r"```json|```", "", raw).strip()
    return json.loads(raw)


def parse_order_gemini(text: str) -> dict:
    model = get_gemini_client()
    response = model.generate_content(f"Procesa este pedido:\n\n{text}")
    raw = response.text.strip()
    raw = re.sub(r"```json|```", "", raw).strip()
    return json.loads(raw)


def parse_order(text: str, provider: str) -> dict:
    if provider == "Gemini":
        return parse_order_gemini(text)
    return parse_order_openai(text)

# ─── GOOGLE SHEETS ────────────────────────────────────────────────────────────────
@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


def save_to_sheets(data: dict, checked: dict, provider: str):
    try:
        gc = get_gspread_client()
        sheet_name = st.secrets.get("SHEET_NAME", "Pedidos")
        spreadsheet_id = st.secrets["SPREADSHEET_ID"]
        sh = gc.open_by_key(spreadsheet_id)
        try:
            ws = sh.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=10)
            ws.append_row(["Fecha", "Tienda", "Emisor", "Categoría", "Producto",
                           "Cantidad", "Unidad", "Recogido", "IA"])

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
                provider,   # columna extra: qué modelo procesó el pedido
            ])
        ws.append_rows(rows)
        return True
    except Exception as e:
        st.error(f"Error al guardar en Google Sheets: {e}")
        return False

# ─── SESSION STATE ───────────────────────────────────────────────────────────────
for key, default in [
    ("parsed_data", None),
    ("checked", {}),
    ("saved", False),
    ("provider", "OpenAI"),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─── HEADER ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
  <span class="app-title">🛒 PedidOS</span>
  <span class="app-sub">Procesador de pedidos WhatsApp</span>
</div>
""", unsafe_allow_html=True)

# ─── SCREEN A: INPUT ─────────────────────────────────────────────────────────────
if st.session_state.parsed_data is None:

    # ── Provider selector ──
    st.markdown("<p style='color:#888;font-size:0.8rem;margin:0 0 4px 0'>Motor de IA</p>", unsafe_allow_html=True)
    provider = st.radio(
        label="Motor de IA",
        options=["OpenAI  (gpt-4o-mini)", "Gemini  (1.5 Flash)"],
        horizontal=True,
        label_visibility="collapsed",
        key="provider_radio",
    )
    # Normaliza a nombre corto
    provider_name = "OpenAI" if provider.startswith("OpenAI") else "Gemini"
    st.session_state.provider = provider_name

    st.markdown("<p style='color:#888;font-size:0.85rem;margin:14px 0 8px 0'>Pega el mensaje de WhatsApp y toca <strong>Generar Lista</strong></p>", unsafe_allow_html=True)

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

    btn_label = f"✨  Generar Lista  ({'GPT-4o mini' if provider_name == 'OpenAI' else 'Gemini 1.5 Flash'})"
    if st.button(btn_label, type="primary", use_container_width=True):
        if not whatsapp_text.strip():
            st.warning("Por favor pega un mensaje primero.")
        else:
            with st.spinner(f"Procesando con {provider_name}..."):
                try:
                    result = parse_order(whatsapp_text, provider_name)
                    st.session_state.parsed_data = result
                    st.session_state.checked = {i: False for i in range(len(result["productos"]))}
                    st.session_state.saved = False
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al procesar con {provider_name}: {e}")

# ─── SCREEN B: CHECKLIST ─────────────────────────────────────────────────────────
else:
    data     = st.session_state.parsed_data
    checked  = st.session_state.checked
    provider_name = st.session_state.provider
    total    = len(data["productos"])
    done     = sum(1 for v in checked.values() if v)

    # Meta pill  (muestra qué modelo procesó el pedido)
    tienda = data.get("tienda") or "—"
    emisor = data.get("emisor") or "—"
    model_badge = "GPT-4o mini" if provider_name == "OpenAI" else "Gemini 1.5 Flash"
    st.markdown(f"""
    <div class="meta-pill">
      <span>🏪 <strong>{tienda}</strong></span>
      <span>👤 <strong>{emisor}</strong></span>
      <span>📦 <strong>{done}/{total}</strong></span>
      <span>🤖 <strong>{model_badge}</strong></span>
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
    cats: dict = {}
    for idx, p in enumerate(data["productos"]):
        cats.setdefault(p["categoria"], []).append((idx, p))

    for cat in CATEGORY_ORDER:
        if cat not in cats:
            continue
        st.markdown(f'<div class="cat-header">{CATEGORY_EMOJI.get(cat,"")} {cat}</div>', unsafe_allow_html=True)

        for idx, p in cats[cat]:
            col1, col2 = st.columns([3, 1])
            is_checked = checked.get(idx, False)
            qty_str = ""
            if p["cantidad"] is not None:
                qty_str = str(p["cantidad"])
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
                st.markdown(f'<div class="product-qty" style="padding-top:8px">{qty_str}</div>',
                            unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    col_a, col_b = st.columns(2)

    with col_a:
        if st.button("🔄  Nuevo pedido", use_container_width=True):
            st.session_state.parsed_data = None
            st.session_state.checked     = {}
            st.session_state.saved       = False
            st.rerun()

    with col_b:
        if not st.session_state.saved:
            if st.button("✅  Finalizar pedido", type="primary", use_container_width=True):
                with st.spinner("Guardando en Google Sheets..."):
                    ok = save_to_sheets(data, checked, provider_name)
                    if ok:
                        st.session_state.saved = True
                        st.rerun()
        else:
            st.success("✓ Guardado en Sheets")
            if st.button("📋  Otro pedido", use_container_width=True):
                st.session_state.parsed_data = None
                st.session_state.checked     = {}
                st.session_state.saved       = False
                st.rerun()
