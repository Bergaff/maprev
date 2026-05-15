import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw, HeatMap
import plotly.express as px
import plotly.graph_objects as go
import requests
from openai import OpenAI

st.set_page_config(
    page_title="Портрет квартала",
    page_icon="🏘️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ====================== NVIDIA ======================
nvidia_client = OpenAI(
    api_key="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",
    base_url="https://integrate.api.nvidia.com/v1"
)

def ask_nvidia(prompt):
    try:
        r = nvidia_client.chat.completions.create(
            model="meta/llama-3.3-70b-instruct",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2500,
            temperature=0.7
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"Ошибка AI: {str(e)[:200]}"

# ====================== OVERPASS ======================
def query_overpass(bbox):
    query = '[out:json][timeout:25];('
    query += 'node["amenity"~"cafe|restaurant|bar|pharmacy|bank|clinic|gym|beauty|fast_food|pub|hotel|dentist|school|kindergarten"](' + bbox + ');'
    query += 'node["shop"](' + bbox + ');'
    query += 'node["leisure"~"fitness_centre|sports_centre|playground"](' + bbox + ');'
    query += 'node["tourism"](' + bbox + ');'
    query += 'node["office"](' + bbox + ');'
    query += ');out body;'

    servers = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter"
    ]
    for server in servers:
        try:
            r = requests.get(server, params={"data": query}, timeout=25)
            if r.status_code == 200:
                return r.json().get("elements", []), None
        except:
            continue
    return [], "Серверы карт недоступны"

# ====================== КАТЕГОРИИ ======================
def categorize(elements):
    cat_map = {
        "Еда и напитки": ["cafe","restaurant","fast_food","bar","pub"],
        "Шопинг": ["clothes","shoes","jewelry","cosmetics","convenience","supermarket","watches","books"],
        "Здоровье": ["pharmacy","clinic","dentist","doctors"],
        "Красота": ["beauty","hairdresser"],
        "Финансы": ["bank","atm"],
        "Спорт": ["gym","fitness_centre","sports_centre"],
        "Образование": ["school","kindergarten","university"],
        "Гостиницы": ["hotel","hostel"],
        "Досуг": ["cinema","theatre","museum","playground","nightclub"],
    }
    result = {}
    for el in elements:
        tags = el.get("tags", {})
        amenity = tags.get("amenity", tags.get("shop", tags.get("leisure", "")))
        found = False
        for cat_name, keywords in cat_map.items():
            if amenity in keywords:
                result[cat_name] = result.get(cat_name, 0) + 1
                found = True
                break
        if not found:
            result["Прочее"] = result.get("Прочее", 0) + 1
    return result

# ====================== ОЦЕНКА ======================
def calculate_scores(elements, bbox):
    parts = [float(x) for x in bbox.split(",")]
    area = max((parts[2]-parts[0])*111*(parts[3]-parts[1])*111*0.6, 0.01)
    total = max(len(elements), 1)
    cats = categorize(elements)

    food_s  = min(100, int(cats.get("Еда и напитки",0) / total * 280))
    health_s = min(100, int(cats.get("Здоровье",0) / area / 5 * 100))
    sport_s  = min(100, int(cats.get("Спорт",0) / area / 3 * 100))
    edu_s    = min(100, int(cats.get("Образование",0) / area / 2 * 100))
    shop_s   = min(100, int(cats.get("Шопинг",0) / total * 220))
    fun_s    = min(100, int(cats.get("Досуг",0) / area / 3 * 100))
    density  = min(100, int(total / area / 150 * 100))
    div_s    = min(100, int(len(cats) / 10 * 100))

    overall = int(
        density*0.15 + food_s*0.2 + health_s*0.15 +
        sport_s*0.1 + edu_s*0.1 + shop_s*0.15 + div_s*0.15
    )

    return {
        "overall": overall, "density": density, "food": food_s,
        "health": health_s, "sport": sport_s, "education": edu_s,
        "shopping": shop_s, "entertainment": fun_s, "diversity": div_s,
        "area_km2": round(area, 3), "total_places": len(elements)
    }

# ====================== SESSION STATE ======================
defaults = {
    "organizations": [], "portrait": "", "chat_history": [],
    "org_text": "", "scores": {}, "heatmap_data": [],
    "show_report": False, "bbox": None
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ====================== CSS ======================
st.markdown("""
<style>
.block-container { padding-top: 1rem; }
footer { visibility: hidden; }
#MainMenu { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ====================== ЗАГОЛОВОК ======================
st.title("Портрет квартала")

# ====================== LAYOUT ======================
col_map, col_chat = st.columns([3, 1.2])

# ---- КАРТА ----
with col_map:
    m = folium.Map(location=[55.7558, 37.6173], zoom_start=13, tiles="OpenStreetMap")

    Draw(
        export=False,
        draw_options={
            "polyline": False, "circle": False,
            "circlemarker": False, "marker": False,
            "polygon": {
                "allowIntersection": False,
                "shapeOptions": {"color": "#ff6b6b", "fillOpacity": 0.2}
            },
            "rectangle": {
                "shapeOptions": {"color": "#ff6b6b", "fillOpacity": 0.2}
            }
        }
    ).add_to(m)

    if st.session_state.heatmap_data:
        HeatMap(
            st.session_state.heatmap_data,
            radius=18, blur=14
        ).add_to(m)

    for el in st.session_state.organizations:
        if "lat" in el and "lon" in el:
            name = el.get("tags", {}).get("name", "")
            if name:
                folium.CircleMarker(
                    [el["lat"], el["lon"]],
                    radius=5,
                    color="#ff6b6b",
                    fill=True,
                    tooltip=name
                ).add_to(m)

    # ВАЖНО: статичный key — карта не мигает
    map_data = st_folium(m, width=None, height=620, key="main_map")

    # Сохраняем bbox только когда рисуют
    if map_data and map_data.get("last_active_drawing"):
        coords = map_data["last_active_drawing"]["geometry"]["coordinates"][0]
        lats = [p[1] for p in coords]
        lons = [p[0] for p in coords]
        st.session_state.bbox = f"{min(lats)},{min(lons)},{max(lats)},{max(lons)}"

# ---- ПРАВАЯ ПАНЕЛЬ ----
with col_chat:
    st.subheader("AI-урбанист")

    # --- Кнопка анализа ---
    if st.session_state.bbox:
        if st.button("Анализировать район", type="primary", use_container_width=True):
            with st.spinner("Сканируем..."):
                elements, err = query_overpass(st.session_state.bbox)
            if err:
                st.error(err)
            elif not elements:
                st.warning("Ничего не найдено. Выберите область побольше.")
            else:
                st.session_state.organizations = elements
                st.session_state.scores = calculate_scores(elements, st.session_state.bbox)
                st.session_state.heatmap_data = [
                    [el["lat"], el["lon"]]
                    for el in elements if "lat" in el and "lon" in el
                ]
                lines = []
                for el in elements:
                    tags = el.get("tags", {})
                    name = tags.get("name", "Без названия")
                    amenity = tags.get("amenity", tags.get("shop", "другое"))
                    cuisine = tags.get("cuisine", "")
                    extra = " (" + cuisine + ")" if cuisine else ""
                    lines.append("- " + name + ": " + amenity + extra)
                st.session_state.org_text = chr(10).join(lines)
                st.session_state.portrait = ""
                st.session_state.chat_history = []
                st.session_state.show_report = False
                st.rerun()
    else:
        st.info("Нарисуйте область на карте слева")

    # --- Оценки ---
    if st.session_state.scores:
        s = st.session_state.scores

        st.markdown(
            "<div style='background:linear-gradient(135deg,#667eea,#764ba2);"
            "color:white;padding:14px;border-radius:12px;text-align:center;margin:8px 0'>"
            "<div style='font-size:38px;font-weight:bold'>" + str(s['overall']) + "/100</div>"
            "<div style='font-size:13px;opacity:0.85'>ИНДЕКС РАЙОНА</div>"
            "</div>",
            unsafe_allow_html=True
        )

        st.caption(str(s['total_places']) + " мест · " + str(s['area_km2']) + " км²")

        for label, val in [
            ("Еда", s["food"]),
            ("Здоровье", s["health"]),
            ("Шопинг", s["shopping"]),
            ("Спорт", s["sport"]),
            ("Образование", s["education"]),
            ("Досуг", s["entertainment"]),
            ("Разнообразие", s["diversity"]),
        ]:
            st.progress(val / 100, text=label + ": " + str(val) + "/100")

        # --- Кнопка полного отчёта ---
        if st.button("Полный отчёт", use_container_width=True):
            if not st.session_state.portrait:
                with st.spinner("AI генерирует отчёт..."):
                    p = "Ты урбанист и бизнес-аналитик. Составь подробный портрет квартала на русском языке." + chr(10)
                    p += "Оценка района: " + str(s['overall']) + "/100" + chr(10)
                    p += "Еда: " + str(s['food']) + ", Здоровье: " + str(s['health']) + ", Шопинг: " + str(s['shopping']) + chr(10)
                    p += "Спорт: " + str(s['sport']) + ", Образование: " + str(s['education']) + ", Досуг: " + str(s['entertainment']) + chr(10)
                    p += "Разнообразие: " + str(s['diversity']) + ", Плотность: " + str(s['density']) + chr(10)
                    p += "Площадь: " + str(s['area_km2']) + " км2, Мест: " + str(s['total_places']) + chr(10) + chr(10)
                    p += "Организации:" + chr(10) + st.session_state.org_text[:3000] + chr(10) + chr(10)
                    p += "Структура ответа:" + chr(10)
                    p += "## Характер квартала" + chr(10)
                    p += "## Кто здесь живёт" + chr(10)
                    p += "## Еда и развлечения" + chr(10)
                    p += "## Шопинг и сервисы" + chr(10)
                    p += "## Плюсы" + chr(10)
                    p += "## Чего не хватает" + chr(10)
                    p += "## Идеи для бизнеса"
                    st.session_state.portrait = ask_nvidia(p)
            # ВАЖНО: нет st.rerun() — отчёт появляется ниже без перезагрузки
            st.session_state.show_report = True

    # --- Быстрые вопросы ---
    if st.session_state.organizations:
        st.markdown("---")
        quick = [
            "Какой бизнес открыть?",
            "Безопасно ли тут?",
            "Подходит для семьи?",
            "Чего не хватает?"
        ]
        qcols = st.columns(2)
        for i, q in enumerate(quick):
            with qcols[i % 2]:
                if st.button(q, key="q" + str(i), use_container_width=True):
                    st.session_state.chat_history.append({"role": "user", "content": q})
                    with st.spinner("Думаю..."):
                        p = "Ты урбанист. Отвечай кратко и по делу на русском." + chr(10)
                        p += "Оценка района: " + str(st.session_state.scores.get('overall','?')) + "/100" + chr(10)
                        p += "Организации:" + chr(10) + st.session_state.org_text[:2000] + chr(10)
                        p += "Вопрос: " + q + chr(10) + "Ответ:"
                        answer = ask_nvidia(p)
                    st.session_state.chat_history.append({"role": "assistant", "content": answer})
                    st.rerun()

        # История чата
        for msg in st.session_state.chat_history[-10:]:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        # Свободный ввод
        user_input = st.chat_input("Спросите про район...")
        if user_input:
            user_input = user_input[:500]
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            with st.spinner("Анализирую..."):
                p = "Ты урбанист-аналитик. Отвечай на русском." + chr(10)
                p += "Оценка района: " + str(st.session_state.scores.get('overall','?')) + "/100" + chr(10)
                p += "Организации:" + chr(10) + st.session_state.org_text[:2000] + chr(10)
                p += "Вопрос: " + user_input + chr(10) + "Ответ:"
                answer = ask_nvidia(p)
            st.session_state.chat_history.append({"role": "assistant", "content": answer})
            st.rerun()

    elif not st.session_state.bbox:
        st.info("Нарисуйте область на карте слева")

# ====================== ОТЧЁТ НИЖЕ КАРТЫ ======================
if st.session_state.show_report and st.session_state.portrait:
    st.markdown("---")
    st.subheader("Полный отчёт")

    rep1, rep2 = st.columns([1, 1])

    with rep1:
        st.subheader("Диаграммы")
        cats = categorize(st.session_state.organizations)

        fig = px.pie(
            names=list(cats.keys()),
            values=list(cats.values()),
            title="Категории организаций",
            hole=0.4
        )
        fig.update_layout(height=380)
        st.plotly_chart(fig, use_container_width=True)

        s = st.session_state.scores
        labels = ["Еда","Здоровье","Шопинг","Спорт","Образование","Досуг","Разнообразие"]
        values_bar = [s["food"],s["health"],s["shopping"],s["sport"],s["education"],s["entertainment"],s["diversity"]]
        colors = ["#FF6B6B","#4ECDC4","#45B7D1","#96CEB4","#FFEAA7","#DDA0DD","#98D8C8"]

        fig2 = go.Figure(go.Bar(
            x=values_bar, y=labels,
            orientation="h",
            marker_color=colors,
            text=[str(v) for v in values_bar],
            textposition="auto"
        ))
        fig2.update_layout(
            title="Оценки района",
            height=300,
            xaxis=dict(range=[0, 100])
        )
        st.plotly_chart(fig2, use_container_width=True)

    with rep2:
        st.subheader("AI-отчёт")
        st.markdown(st.session_state.portrait)

    if st.button("Закрыть отчёт", use_container_width=True):
        st.session_state.show_report = False
        st.rerun()
