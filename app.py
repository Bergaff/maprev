import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw, HeatMap
import plotly.express as px
import plotly.graph_objects as go
import requests
import time
import hashlib
import numpy as np
from openai import OpenAI

st.set_page_config(
    page_title="Портрет квартала",
    page_icon="🏘️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ====================== API ======================
NVIDIA_API_KEY = "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"

nvidia_client = OpenAI(
    api_key=NVIDIA_API_KEY,
    base_url="https://integrate.api.nvidia.com/v1"
)

# ====================== СЕССИЯ ======================
if "organizations" not in st.session_state:
    st.session_state.organizations = []
if "portrait" not in st.session_state:
    st.session_state.portrait = ""
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "org_text" not in st.session_state:
    st.session_state.org_text = ""
if "scores" not in st.session_state:
    st.session_state.scores = {}
if "heatmap_data" not in st.session_state:
    st.session_state.heatmap_data = []
if "last_drawing" not in st.session_state:
    st.session_state.last_drawing = None
if "show_report" not in st.session_state:
    st.session_state.show_report = False
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_email" not in st.session_state:
    st.session_state.user_email = ""
if "users_db" not in st.session_state:
    st.session_state.users_db = {}

# ====================== БАЗА ЗНАНИЙ ======================
KNOWLEDGE_BASE = [
    "Принцип разнообразия Джейн Джекобс: район жив, когда смешаны функции — жильё, работа, торговля, досуг.",
    "Принцип 'глаза на улице': безопасность создаётся естественным наблюдением из окон, кафе и тротуаров.",
    "Короткие кварталы и много перекрёстков делают район живым.",
    "Принцип 'третьего места' Ольденбурга: людям нужны места кроме дома и работы (кофейни, парки, барбершопы).",
    "15-минутный город: всё необходимое должно быть в 15 минутах пешком.",
    "Активные фасады и витрины делают улицу безопасной и привлекательной.",
    "Высокая доля авторских заведений = сформированное комьюнити. Много сетевых = транзитный поток.",
]

# ====================== NVIDIA ЧАТ ======================
def ask_nvidia(prompt):
    try:
        response = nvidia_client.chat.completions.create(
            model="meta/llama-3.3-70b-instruct",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2500,
            temperature=0.7,
            top_p=0.9
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Ошибка NVIDIA: {str(e)[:80]}"

# ====================== RAG ======================
def find_relevant_knowledge(query, top_k=3):
    # Простая версия без эмбеддингов (чтобы не усложнять сейчас)
    relevant = [chunk for chunk in KNOWLEDGE_BASE if any(word in chunk.lower() for word in query.lower().split() if len(word)>3)]
    return "\n\n".join(relevant[:top_k]) or "Нет релевантных знаний."

# ====================== ОСНОВНЫЕ ФУНКЦИИ ======================
def query_overpass(bbox):
    servers = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"~"cafe|restaurant|bar|pharmacy|bank|clinic|gym|beauty|fast_food|pub|hotel|dentist|school|kindergarten"]({bbox});
      node["shop"]({bbox});
      node["leisure"~"fitness_centre|sports_centre|playground"]({bbox});
      node["tourism"]({bbox});
      node["office"]({bbox});
    );
    out body;
    """
    for server in servers:
        try:
            r = requests.get(server, params={"data": query}, timeout=25)
            if r.status_code == 200 and len(r.text) > 10:
                return r.json().get("elements", []), None
        except:
            continue
    return [], "Серверы карт недоступны"

def categorize(elements):
    cat_map = {
        "🍕 Еда и напитки": ["cafe","restaurant","fast_food","bar","pub"],
        "🛍️ Шопинг": ["clothes","shoes","jewelry","cosmetics","convenience","supermarket"],
        "💊 Здоровье": ["pharmacy","clinic","dentist","doctors"],
        "💅 Красота": ["beauty","hairdresser"],
        "🏦 Финансы": ["bank","atm"],
        "🏋️ Спорт": ["gym","fitness_centre"],
        "🎓 Образование": ["school","kindergarten"],
        "🏨 Гостиницы": ["hotel","hostel"],
        "🎭 Досуг": ["cinema","theatre","museum","playground","nightclub"],
        "🏪 Прочее": []
    }
    result = {k: 0 for k in cat_map}
    for el in elements:
        tags = el.get("tags", {})
        amenity = tags.get("amenity", tags.get("shop", tags.get("leisure", "")))
        found = False
        for name, keys in cat_map.items():
            if amenity in keys:
                result[name] += 1
                found = True
                break
        if not found:
            result["🏪 Прочее"] += 1
    return {k:v for k,v in result.items() if v > 0}

def calculate_scores(elements, bbox):
    parts = [float(x) for x in bbox.split(",")]
    area_km2 = max((parts[2]-parts[0])*111 * (parts[3]-parts[1])*111*0.6, 0.01)
    total = len(elements)
    cats = categorize(elements)
    food = cats.get("🍕 Еда и напитки", 0)

    density = min(100, int((total / area_km2) / 150 * 100))
    food_score = min(100, int(food / max(total,1) * 280))
    health_score = min(100, int(cats.get("💊 Здоровье",0) / area_km2 / 5 * 100))
    sport_score = min(100, int(cats.get("🏋️ Спорт",0) / area_km2 / 3 * 100))
    education_score = min(100, int(cats.get("🎓 Образование",0) / area_km2 / 2 * 100))
    shopping_score = min(100, int(cats.get("🛍️ Шопинг",0) / max(total,1) * 220))
    diversity = min(100, int(len(cats)/10*100))

    overall = int(density*0.2 + food_score*0.2 + health_score*0.15 + 
                  sport_score*0.1 + education_score*0.1 + shopping_score*0.15 + diversity*0.1)

    return {"overall": overall, "density": density, "food": food_score, "health": health_score,
            "sport": sport_score, "education": education_score, "shopping": shopping_score,
            "diversity": diversity, "area_km2": round(area_km2,3), "total_places": total}

# ====================== ИНТЕРФЕЙС ======================
st.title("🏘️ Портрет квартала")
st.markdown("Обведите область → нажмите «Анализировать»")

col_map, col_chat = st.columns([3, 1.1])

with col_map:
    m = folium.Map(location=[55.7558, 37.6173], zoom_start=13, tiles="OpenStreetMap")
    Draw(
        export=False,
        draw_options={
            "polyline": False, "circle": False, "circlemarker": False, "marker": False,
            "polygon": {"allowIntersection": False, "shapeOptions": {"color": "#ff6b6b", "fillOpacity": 0.25}},
            "rectangle": {"shapeOptions": {"color": "#ff6b6b", "fillOpacity": 0.25}}
        }
    ).add_to(m)

    if st.session_state.heatmap_data:
        HeatMap(st.session_state.heatmap_data, radius=18, blur=12,
                gradient={0.2:'blue',0.5:'lime',0.7:'yellow',1:'red'}).add_to(m)

    if st.session_state.organizations:
        for el in st.session_state.organizations:
            if "lat" in el and "lon" in el:
                name = el.get("tags",{}).get("name","")
                folium.Marker([el["lat"], el["lon"]], tooltip=name).add_to(m)

    map_data = st_folium(m, width=None, height=620, key="map_key")

with col_chat:
    st.subheader("💬 AI-урбанист")

    if map_data and map_data.get("last_active_drawing"):
        drawing = map_data["last_active_drawing"]
        st.session_state.last_drawing = drawing

        coords = drawing["geometry"]["coordinates"][0]
        lats = [p[1] for p in coords]
        lons = [p[0] for p in coords]
        bbox = f"{min(lats)},{min(lons)},{max(lats)},{max(lons)}"

        if st.button("🔍 Анализировать район", type="primary", use_container_width=True):
            with st.spinner("Анализируем район..."):
                elements, err = query_overpass(bbox)
                if elements:
                    st.session_state.organizations = elements
                    st.session_state.scores = calculate_scores(elements, bbox)
                    st.session_state.heatmap_data = [[el["lat"], el["lon"]] for el in elements if "lat" in el and "lon" in el]
                    
                    lines = [f"- {el.get('tags',{}).get('name','Без названия')}: {el.get('tags',{}).get('amenity','—')}" 
                            for el in elements]
                    st.session_state.org_text = "\n".join(lines)
                    st.session_state.portrait = ""
                    st.session_state.chat_history = []
                    st.rerun()
                else:
                    st.error(err or "Ничего не найдено")

    # Показываем оценки
    if st.session_state.scores:
        s = st.session_state.scores
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:16px;border-radius:16px;text-align:center">
            <div style="font-size:42px;font-weight:bold">{s['overall']}/100</div>
            <div>ИНДЕКС РАЙОНА</div>
        </div>""", unsafe_allow_html=True)

        if st.button("📋 Полный отчёт", use_container_width=True):
            st.session_state.show_report = True
            if not st.session_state.portrait:
                with st.spinner("Генерируем отчёт..."):
                    st.session_state.portrait = ask_nvidia(f"""Напиши подробный портрет квартала. Используй следующие данные:
Оценка: {s['overall']}/100
Еда: {s['food']}, Здоровье: {s['health']}, Шопинг: {s['shopping']}
Организации:\n{st.session_state.org_text}""")
            st.rerun()

    # Чат
    if st.session_state.organizations:
        for msg in st.session_state.chat_history:
            st.chat_message(msg["role"]).write(msg["content"])

        if prompt := st.chat_input("Спросите про район..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            st.chat_message("user").write(prompt)

            with st.spinner("Думаю..."):
                answer = ask_nvidia(f"""Ты — эксперт по урбанистике. Используй данные квартала и отвечай на русском.
Данные квартала: {st.session_state.org_text}
Оценка: {st.session_state.scores.get('overall', '?')}/100

Вопрос: {prompt}
Ответ:""")
            
            st.session_state.chat_history.append({"role": "assistant", "content": answer})
            st.rerun()

if st.session_state.show_report and st.session_state.portrait:
    st.markdown("---")
    st.subheader("📊 Полный отчёт")
    st.markdown(st.session_state.portrait)
    if st.button("Закрыть отчёт"):
        st.session_state.show_report = False
        st.rerun()
