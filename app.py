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

# =============================================
# НАСТРОЙКИ
# =============================================
st.set_page_config(
    page_title="Портрет квартала",
    page_icon="🏘️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

NVIDIA_API_KEY = "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"

nvidia_client = OpenAI(
    api_key=NVIDIA_API_KEY,
    base_url="https://integrate.api.nvidia.com/v1"
)

FREE_LIMIT_SEARCH = 50
FREE_LIMIT_AI = 50
FREE_LIMIT_CHAT = 100

# =============================================
# БАЗА ЗНАНИЙ ПО УРБАНИСТИКЕ
# =============================================
KNOWLEDGE_BASE = [
    "Принцип разнообразия Джейн Джекобс: район жив, когда в нём смешаны функции — жильё, работа, торговля, досуг. Монофункциональные районы мертвеют.",
    "Принцип 'глаза на улице' Джекобс: безопасность района определяется количеством людей, которые естественно наблюдают за улицей — из окон, из кафе, с тротуаров.",
    "Короткие кварталы Джекобс: чем больше перекрёстков и поворотов, тем живее район. Длинные кварталы без перекрёстков убивают пешеходную жизнь.",
    "Старые здания Джекобс: району нужны здания разного возраста. Старые здания = дешёвая аренда = уникальные маленькие бизнесы.",
    "Принцип масштаба Яна Гейла: город должен быть спроектирован для скорости 5 км/ч (пешеход), а не 60 км/ч (автомобиль).",
    "Правило 5 минут Гейла: человек готов идти пешком максимум 500 метров до ежедневных потребностей.",
    "Принцип активных фасадов Гейла: улица с 15-20 дверями и витринами на 100 метров — живая. Глухой забор — мёртвая.",
    "Концепция 'третьего места' Ольденбурга: кофейня, библиотека, парк, бар — места кроме дома и работы. Район без третьих мест — одинокий.",
    "4 условия пешеходности Спека: полезно, безопасно, комфортно, интересно.",
    "Концепция 15-минутного города: всё необходимое в 15 минутах пешком. 6 функций: жить, работать, снабжаться, лечиться, учиться, отдыхать.",
    "Плотность и безопасность: районы со средней плотностью (150-300 чел/га) безопаснее очень плотных или разреженных.",
    "Разнообразие еды как индикатор: 5+ кухонь = космополитичный район с высоким доходом. Монокухня = низкий сегмент.",
    "Аптеки как якорь: отсутствие аптеки в радиусе 500м — серьёзная инфраструктурная проблема.",
    "Парикмахерские и барбершопы как социальные хабы: их количество — индикатор жилого характера района.",
    "Сетевые vs локальные заведения: высокая доля сетевых = транзитный трафик. Высокая доля авторских = лояльное комьюнити.",
    "Банки как индикатор: 3+ банковских отделения в квартале = деловая активность, офисные работники.",
]

# =============================================
# CSS
# =============================================
st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; }
    .score-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white; border-radius: 16px; padding: 20px; text-align: center; margin: 8px 0;
    }
    .score-number { font-size: 48px; font-weight: bold; }
    .score-label { font-size: 14px; opacity: 0.8; }
    .param-card {
        background: #f8f9fa; border-radius: 12px; padding: 12px;
        margin: 4px 0; border-left: 4px solid #667eea;
    }
    .knowledge-tag {
        background: #e8f4f8; border-radius: 8px; padding: 8px 12px;
        margin: 4px 0; font-size: 12px; border-left: 3px solid #4ECDC4;
    }
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# =============================================
# SESSION STATE
# =============================================
defaults = {
    "organizations": [], "portrait": "", "chat_history": [],
    "org_text": "", "show_report": False, "scores": {},
    "heatmap_data": [], "search_count": 0, "ai_count": 0,
    "chat_count": 0, "logged_in": False, "user_email": "",
    "auth_page": None, "users_db": {},
    # Для сохранения карты
    "saved_bbox": None, "saved_center": None, "saved_zoom": None,
    "map_initialized": False
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val


# =============================================
# АВТОРИЗАЦИЯ
# =============================================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def show_auth():
    tab1, tab2 = st.tabs(["🔑 Вход", "📝 Регистрация"])
    with tab1:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            if st.form_submit_button("Войти", type="primary"):
                if email and password:
                    if email in st.session_state.users_db and st.session_state.users_db[email] == hash_password(password):
                        st.session_state.logged_in = True
                        st.session_state.user_email = email
                        st.rerun()
                    else:
                        st.error("Неверный email или пароль")
    with tab2:
        with st.form("register_form"):
            e = st.text_input("Email", key="reg_email")
            p1 = st.text_input("Пароль (мин 6 символов)", type="password", key="reg_pass")
            p2 = st.text_input("Повторите", type="password", key="reg_pass2")
            if st.form_submit_button("Зарегистрироваться", type="primary"):
                if e and p1 and p1 == p2 and "@" in e and len(p1) >= 6:
                    st.session_state.users_db[e] = hash_password(p1)
                    st.session_state.logged_in = True
                    st.session_state.user_email = e
                    st.rerun()
                else:
                    st.error("Проверьте данные")


# =============================================
# OVERPASS
# =============================================
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
            r = requests.get(server, params={"data": query}, timeout=30)
            if r.status_code == 200 and len(r.text) > 10:
                return r.json().get("elements", []), None
        except:
            time.sleep(2)
    return [], "Серверы недоступны"


# =============================================
# NVIDIA AI
# =============================================
def ask_ai(prompt, model="meta/llama-3.3-70b-instruct"):
    try:
        response = nvidia_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2500,
            temperature=0.7,
            top_p=0.9,
            timeout=90
        )
        text = response.choices[0].message.content
        if text and len(text) > 20:
            return text
        return "AI вернул пустой ответ. Попробуйте ещё раз."
    except Exception as e:
        # Fallback на другую модель
        if model != "meta/llama-3.1-8b-instruct":
            try:
                return ask_ai(prompt, "meta/llama-3.1-8b-instruct")
            except:
                pass
        return f"AI временно недоступен. ({str(e)[:50]})"


# =============================================
# EMBEDDINGS + RAG
# =============================================
@st.cache_data(ttl=3600)
def get_knowledge_embeddings():
    try:
        all_emb = []
        for i in range(0, len(KNOWLEDGE_BASE), 10):
            batch = KNOWLEDGE_BASE[i:i+10]
            response = nvidia_client.embeddings.create(
                input=batch,
                model="nvidia/llama-nemotron-embed-1b-v2",
                encoding_format="float",
                extra_body={"input_type": "passage", "truncate": "NONE"}
            )
            for item in response.data:
                all_emb.append(item.embedding)
        return all_emb
    except:
        return None

def get_query_embedding(query):
    try:
        response = nvidia_client.embeddings.create(
            input=[query],
            model="nvidia/llama-nemotron-embed-1b-v2",
            encoding_format="float",
            extra_body={"input_type": "query", "truncate": "NONE"}
        )
        return response.data[0].embedding
    except:
        return None

def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def find_relevant_knowledge(query, top_k=3):
    kb_emb = get_knowledge_embeddings()
    if kb_emb is None:
        return ""
    q_emb = get_query_embedding(query)
    if q_emb is None:
        return ""
    similarities = [(cosine_similarity(q_emb, e), i) for i, e in enumerate(kb_emb)]
    similarities.sort(reverse=True)
    return "\n\n".join([f"📚 {KNOWLEDGE_BASE[i]}" for sim, i in similarities[:top_k] if sim > 0.3])


# =============================================
# КАТЕГОРИЗАЦИЯ
# =============================================
def categorize(elements):
    categories = {
        "🍕 Еда": ["cafe", "restaurant", "fast_food", "bar", "pub"],
        "🛍️ Шопинг": ["clothes", "shoes", "jewelry", "cosmetics", "convenience", "supermarket"],
        "💊 Здоровье": ["pharmacy", "clinic", "dentist", "hospital"],
        "💅 Красота": ["beauty", "hairdresser"],
        "🏦 Банки": ["bank", "atm"],
        "🏋️ Спорт": ["gym", "fitness_centre", "sports_centre"],
        "🎓 Образование": ["school", "kindergarten", "university"],
        "🏨 Отели": ["hotel", "hostel"],
        "🎭 Досуг": ["cinema", "theatre", "museum", "nightclub"],
        "🏪 Прочее": []
    }
    result = {cat: 0 for cat in categories}
    for el in elements:
        tags = el.get("tags", {})
        amenity = tags.get("amenity", tags.get("shop", tags.get("leisure", "")))
        found = False
        for cat_name, keywords in categories.items():
            if amenity in keywords:
                result[cat_name] += 1
                found = True
                break
        if not found:
            result["🏪 Прочее"] += 1
    return {k: v for k, v in result.items() if v > 0}


# =============================================
# ОЦЕНКА РАЙОНА
# =============================================
def calculate_scores(elements, bbox):
    parts = bbox.split(",")
    min_lat, min_lon, max_lat, max_lon = [float(x) for x in parts]
    area_km2 = max((max_lat - min_lat) * 111 * (max_lon - min_lon) * 111 * 0.6, 0.01)
    total = len(elements)
    cats = categorize(elements)
    food = cats.get("🍕 Еда", 0)
    health = cats.get("💊 Здоровье", 0)
    sport = cats.get("🏋️ Спорт", 0)
    education = cats.get("🎓 Образование", 0)
    shopping = cats.get("🛍️ Шопинг", 0)
    entertainment = cats.get("🎭 Досуг", 0)
    cuisines = set(el.get("tags", {}).get("cuisine", "") for el in elements)
    cuisines.discard("")

    density = min(100, int((total / area_km2) / 150 * 100))
    food_score = min(100, int(food / max(total, 1) * 300 + len(cuisines) * 5))
    health_score = min(100, int(health / area_km2 / 5 * 100))
    sport_score = min(100, int(sport / area_km2 / 3 * 100))
    education_score = min(100, int(education / area_km2 / 2 * 100))
    shopping_score = min(100, int(shopping / max(total, 1) * 250))
    diversity = min(100, int(len(cats) / 10 * 100))
    entertainment_score = min(100, int(entertainment / area_km2 / 3 * 100))

    overall = int(density * 0.15 + food_score * 0.15 + health_score * 0.15 +
                  sport_score * 0.10 + education_score * 0.10 + shopping_score * 0.10 +
                  diversity * 0.15 + entertainment_score * 0.10)

    return {
        "overall": overall, "density": density, "food": food_score,
        "health": health_score, "sport": sport_score, "education": education_score,
        "shopping": shopping_score, "diversity": diversity,
        "entertainment": entertainment_score, "area_km2": round(area_km2, 3),
        "total_places": total, "cuisines_count": len(cuisines),
        "center_lat": (min_lat + max_lat) / 2,
        "center_lon": (min_lon + max_lon) / 2,
    }


# =============================================
# ПОРТРЕТ С RAG
# =============================================
def generate_portrait(org_text, scores):
    knowledge = find_relevant_knowledge(
        f"анализ квартала еда {scores['food']} здоровье {scores['health']}",
        top_k=5
    )
    prompt = f"""Ты — урбанист. Используй знания ниже.

ЗНАНИЯ УРБАНИСТИКИ:
{knowledge}

ОЦЕНКИ (0-100):
Общая: {scores['overall']}, Еда: {scores['food']}, Здоровье: {scores['health']}
Спорт: {scores['sport']}, Образование: {scores['education']}, Шопинг: {scores['shopping']}
Досуг: {scores['entertainment']}, Разнообразие: {scores['diversity']}
Площадь: {scores['area_km2']} км², Мест: {scores['total_places']}

ОРГАНИЗАЦИИ:
{org_text}

Структура ответа:
## Характер квартала
## Кто здесь живёт
## Еда и развлечения
## Шопинг и сервисы
## Плюсы (принципы урбанистики)
## Чего не хватает (15-минутный город)
## Идеи для бизнеса"""
    return ask_ai(prompt)


# =============================================
# ЧАТ С RAG
# =============================================
def chat_answer(question, org_text, history, scores):
    question = question[:500].replace("<", "").replace(">", "")
    if len(question.strip()) < 3:
        return "Задайте более развёрнутый вопрос."
    knowledge = find_relevant_knowledge(question, top_k=3)
    hist = ""
    for msg in history[-6:]:
        role = "Пользователь" if msg["role"] == "user" else "Ассистент"
        hist += f"{role}: {msg['content']}\n"
    prompt = f"""ПРАВИЛА: Отвечай ТОЛЬКО про городскую среду. Вне темы — откажись. Используй знания урбанистики.

ЗНАНИЯ:
{knowledge}

Район: {scores.get('overall', '?')}/100, {scores.get('total_places', '?')} мест
Организации: {org_text[:2000]}
История: {hist}
Вопрос: {question}
Ответ:"""
    return ask_ai(prompt, "meta/llama-3.1-8b-instruct")


# =============================================
# ХЕДЕР
# =============================================
h1, h2, h3 = st.columns([6, 2, 2])
with h1:
    st.title("🏘️ Портрет квартала")
with h2:
    if st.session_state.logged_in:
        st.markdown(f"👤 {st.session_state.user_email}")
with h3:
    if st.session_state.logged_in:
        if st.button("Выйти"):
            st.session_state.logged_in = False
            st.rerun()
    else:
        if st.button("🔑 Войти"):
            st.session_state.auth_page = True
            st.rerun()

if st.session_state.auth_page and not st.session_state.logged_in:
    show_auth()
    if st.button("← Назад к карте"):
        st.session_state.auth_page = None
        st.rerun()
    st.stop()


# =============================================
# КАРТА (СОХРАНЯЕМ ПОЗИЦИЮ)
# =============================================
map_col, chat_col = st.columns([3, 1])

with map_col:
    # Определяем центр карты
    if st.session_state.saved_center:
        start_center = st.session_state.saved_center
        start_zoom = st.session_state.saved_zoom or 15
    else:
        start_center = [55.7558, 37.6173]
        start_zoom = 13

    m = folium.Map(
        location=start_center,
        zoom_start=start_zoom,
        tiles="OpenStreetMap"
    )

    Draw(export=False, draw_options={
        "polyline": False, "circle": False, "circlemarker": False, "marker": False,
        "polygon": {"allowIntersection": False, "shapeOptions": {"color": "#ff6b6b", "fillOpacity": 0.2}},
        "rectangle": {"shapeOptions": {"color": "#ff6b6b", "fillOpacity": 0.2}}
    }).add_to(m)

    # Тепловая карта
    if st.session_state.heatmap_data:
        HeatMap(
            st.session_state.heatmap_data,
            radius=20, blur=15,
            gradient={0.2: 'blue', 0.4: 'lime', 0.6: 'yellow', 0.8: 'orange', 1: 'red'}
        ).add_to(m)

    # Маркеры
    if st.session_state.organizations:
        for el in st.session_state.organizations[:200]:
            tags = el.get("tags", {})
            name = tags.get("name", "")
            if name and "lat" in el:
                amenity = tags.get("amenity", tags.get("shop", ""))
                icons = {"cafe": "☕", "restaurant": "🍽️", "fast_food": "🍔",
                         "bar": "🍺", "pharmacy": "💊", "bank": "🏦",
                         "beauty": "💅", "gym": "🏋️", "school": "🎓", "clinic": "🏥"}
                ic = icons.get(amenity, "📍")
                folium.Marker(
                    [el["lat"], el["lon"]],
                    tooltip=name,
                    icon=folium.DivIcon(html=f'<div style="font-size:14px">{ic}</div>', icon_size=(18, 18))
                ).add_to(m)

    map_data = st_folium(m, width=None, height=580, key="main_map")


# =============================================
# ПРАВАЯ ПАНЕЛЬ: АНАЛИЗ + ЧАТ
# =============================================
with chat_col:
    st.markdown("### 💬 AI-урбанист")

    # Проверяем нарисован ли полигон
    if map_data and map_data.get("last_active_drawing"):
        drawing = map_data["last_active_drawing"]
        coords = drawing.get("geometry", {}).get("coordinates", [[]])[0]
        if coords:
            lats = [c[1] for c in coords]
            lons = [c[0] for c in coords]
            bbox = f"{min(lats)},{min(lons)},{max(lats)},{max(lons)}"

            # Сохраняем центр для фиксации карты
            st.session_state.saved_center = [(min(lats)+max(lats))/2, (min(lons)+max(lons))/2]
            st.session_state.saved_zoom = 15

            if st.button("🔍 Анализировать район", type="primary", use_container_width=True):
                with st.spinner("Сканируем район через OpenStreetMap..."):
                    elements, error = query_overpass(bbox)

                if error:
                    st.error(error)
                elif not elements:
                    st.warning("Ничего не найдено. Попробуйте другую область.")
                else:
                    st.session_state.organizations = elements
                    st.session_state.scores = calculate_scores(elements, bbox)
                    st.session_state.heatmap_data = [[el["lat"], el["lon"]] for el in elements if "lat" in el]
                    st.session_state.saved_bbox = bbox

                    org_lines = []
                    for el in elements:
                        tags = el.get("tags", {})
                        name = tags.get("name", "Без названия")
                        amenity = tags.get("amenity", tags.get("shop", "другое"))
                        cuisine = tags.get("cuisine", "")
                        extra = f" ({cuisine})" if cuisine else ""
                        org_lines.append(f"- {name}: {amenity}{extra}")
                    st.session_state.org_text = "\n".join(org_lines)
                    st.session_state.portrait = ""
                    st.session_state.chat_history = []
                    st.session_state.show_report = False
                    st.rerun()

    # Оценки
    if st.session_state.scores:
        s = st.session_state.scores
        st.markdown(f"""<div class="score-card">
            <div class="score-number">{s['overall']}/100</div>
            <div class="score-label">ИНДЕКС РАЙОНА</div>
        </div>""", unsafe_allow_html=True)
        st.markdown(f"📍 {s['total_places']} мест · {s['area_km2']} км²")

        for label, value in [("🍕 Еда", s["food"]), ("💊 Здоровье", s["health"]),
                              ("🛍️ Шопинг", s["shopping"]), ("🏋️ Спорт", s["sport"]),
                              ("🎓 Образование", s["education"]), ("🎭 Досуг", s["entertainment"]),
                              ("📊 Разнообразие", s["diversity"])]:
            color = "#4CAF50" if value >= 60 else "#FFC107" if value >= 30 else "#f44336"
            st.markdown(f"""<div class="param-card">{label}: <b>{value}</b>
                <div style="background:#e0e0e0;border-radius:4px;height:6px;margin-top:4px">
                    <div style="background:{color};width:{value}%;height:6px;border-radius:4px"></div>
                </div></div>""", unsafe_allow_html=True)

        if st.button("📋 Полный отчёт", use_container_width=True):
            st.session_state.show_report = True
            if not st.session_state.portrait:
                with st.spinner("AI + RAG анализирует..."):
                    st.session_state.portrait = generate_portrait(st.session_state.org_text, s)
            st.rerun()

    # Чат
    if st.session_state.organizations:
        st.markdown("---")
        quick = ["Какой бизнес открыть?", "Безопасно ли?", "Для семьи?", "Чего не хватает?"]
        cols = st.columns(2)
        for i, q in enumerate(quick):
            with cols[i % 2]:
                if st.button(q, key=f"q{i}", use_container_width=True):
                    st.session_state.chat_history.append({"role": "user", "content": q})
                    with st.spinner("RAG + AI..."):
                        ans = chat_answer(q, st.session_state.org_text, st.session_state.chat_history, st.session_state.scores)
                    st.session_state.chat_history.append({"role": "assistant", "content": ans})
                    st.rerun()

        for msg in st.session_state.chat_history[-8:]:
            st.chat_message(msg["role"]).write(msg["content"])

        user_q = st.chat_input("Задайте вопрос...")
        if user_q:
            user_q = user_q[:500].replace("<", "").replace(">", "")
            st.session_state.chat_history.append({"role": "user", "content": user_q})
            with st.spinner("Анализирую..."):
                ans = chat_answer(user_q, st.session_state.org_text, st.session_state.chat_history, st.session_state.scores)
            st.session_state.chat_history.append({"role": "assistant", "content": ans})
            st.rerun()

    elif not st.session_state.organizations:
        st.info("← Нарисуйте область и нажмите 'Анализировать'")


# =============================================
# ОТЧЁТ (ВСПЛЫВАЮЩИЙ)
# =============================================
if st.session_state.show_report and st.session_state.portrait:
    st.markdown("---")
    r1, r2 = st.columns([1, 1])
    with r1:
        st.markdown("### 📊 Диаграммы")
        if st.session_state.organizations:
            cats = categorize(st.session_state.organizations)
            fig = px.pie(names=list(cats.keys()), values=list(cats.values()),
                         title="Категории", hole=0.4, color_discrete_sequence=px.colors.qualitative.Set3)
            fig.update_layout(height=380)
            st.plotly_chart(fig, use_container_width=True)

            s = st.session_state.scores
            fig2 = go.Figure(go.Bar(
                x=[s["food"], s["health"], s["shopping"], s["sport"], s["education"], s["entertainment"], s["diversity"]],
                y=["Еда", "Здоровье", "Шопинг", "Спорт", "Образование", "Досуг", "Разнообразие"],
                orientation="h",
                marker_color=["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD", "#98D8C8"],
                text=[f"{v}" for v in [s["food"], s["health"], s["shopping"], s["sport"], s["education"], s["entertainment"], s["diversity"]]],
                textposition="auto"
            ))
            fig2.update_layout(title="Оценки", height=300, xaxis_range=[0, 100])
            st.plotly_chart(fig2, use_container_width=True)
    with r2:
        st.markdown("### 📝 AI-отчёт")
        st.markdown(st.session_state.portrait)
    if st.button("✖ Закрыть отчёт", use_container_width=True):
        st.session_state.show_report = False
        st.rerun()
