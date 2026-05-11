import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import requests
import time

st.set_page_config(
    page_title="Портрет квартала",
    page_icon="🏘️",
    layout="wide"
)

OPENROUTER_KEY = st.secrets.get("OPENROUTER_KEY", "")

# =============================================
# OVERPASS
# =============================================
def query_overpass(bbox):
    servers = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ]

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
            response = requests.get(
                server,
                params={"data": query},
                timeout=30,
                headers={"User-Agent": "QuarterPortrait/1.0"}
            )
            if response.status_code == 200 and len(response.text) > 10:
                return response.json().get("elements", []), None
        except Exception:
            time.sleep(2)
            continue

    return [], "Все серверы недоступны."


# =============================================
# AI ЧЕРЕЗ OPENROUTER
# =============================================
def ask_ai(prompt):
    if not OPENROUTER_KEY:
        return "API ключ не настроен. Добавьте OPENROUTER_KEY в Secrets."

    # Список моделей по приоритету (от лучшей к запасной)
    models = [
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemma-4-31b-it:free",
        "nousresearch/hermes-3-llama-3.1-405b:free",
    ]

    for model_name in models:
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://quarter-portrait.streamlit.app",
                    "X-Title": "Quarter Portrait"
                },
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 2000
                },
                timeout=90
            )

            if response.status_code == 200:
                data = response.json()
                text = data["choices"][0]["message"]["content"]
                if text and len(text) > 20:
                    return text

        except Exception:
            continue

    return "Все AI модели временно недоступны. Попробуйте через минуту."


# =============================================
# ГЕНЕРАЦИЯ ПОРТРЕТА
# =============================================
def generate_portrait(org_text):
    prompt = f"""Ты — эксперт по городской среде, урбанист и бизнес-аналитик.

На основе списка организаций составь подробный портрет квартала.
Отвечай на русском языке.

## 🏘️ Общий характер квартала
Опиши атмосферу, тип района

## 👥 Кто здесь живёт и бывает
Типичный житель или посетитель

## ☕ Еда и развлечения
Какие заведения, кухня, ценовой сегмент

## 🛍️ Шопинг и сервисы
Магазины и услуги

## ✅ Плюсы квартала

## ⚠️ Чего не хватает

## 💡 Идеи для бизнеса
Что взлетит в этом квартале

Список организаций:
{org_text}"""

    return ask_ai(prompt)


# =============================================
# ЧАТ
# =============================================
def chat_answer(question, org_text, history):
    history_text = ""
    for msg in history[-6:]:
        role = "Пользователь" if msg["role"] == "user" else "Ассистент"
        history_text += f"{role}: {msg['content']}\n"

    prompt = f"""Ты — бизнес-консультант и урбанист. Отвечай на русском.

Организации в квартале:
{org_text}

История диалога:
{history_text}

Вопрос: {question}

Ответ:"""

    return ask_ai(prompt)


# =============================================
# SESSION STATE
# =============================================
if "organizations" not in st.session_state:
    st.session_state.organizations = []
if "portrait" not in st.session_state:
    st.session_state.portrait = ""
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "org_text" not in st.session_state:
    st.session_state.org_text = ""


# =============================================
# ИНТЕРФЕЙС
# =============================================
st.title("🏘️ Портрет квартала")
st.markdown("Обведите область на карте → AI-анализ + чат с аналитиком")

moscow_center = [55.7558, 37.6173]
m = folium.Map(location=moscow_center, zoom_start=14, tiles="OpenStreetMap")

draw = Draw(
    export=False,
    draw_options={
        "polyline": False, "circle": False,
        "circlemarker": False, "marker": False,
        "polygon": {
            "allowIntersection": False,
            "shapeOptions": {"color": "#ff6b6b", "fillOpacity": 0.3}
        },
        "rectangle": {
            "shapeOptions": {"color": "#ff6b6b", "fillOpacity": 0.3}
        }
    }
)
draw.add_to(m)

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📍 Нарисуйте область")
    map_data = st_folium(m, width=700, height=500)

with col2:
    st.subheader("📊 Организации")

    if map_data and map_data.get("last_active_drawing"):
        drawing = map_data["last_active_drawing"]
        coordinates = drawing.get("geometry", {}).get("coordinates", [[]])

        if coordinates and coordinates[0]:
            coords = coordinates[0]
            lats = [c[1] for c in coords]
            lons = [c[0] for c in coords]

            st.success("✅ Область выбрана")
            bbox = f"{min(lats)},{min(lons)},{max(lats)},{max(lons)}"

            if st.button("🔍 Найти организации", type="primary"):
                with st.spinner("Ищем через OpenStreetMap..."):
                    elements, error = query_overpass(bbox)

                if error:
                    st.error(error)
                elif not elements:
                    st.warning("Ничего не найдено.")
                else:
                    st.session_state.organizations = elements
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
                    st.rerun()

            if st.session_state.organizations:
                st.success(f"🎉 {len(st.session_state.organizations)} мест")
                type_counts = {}
                for el in st.session_state.organizations:
                    tags = el.get("tags", {})
                    amenity = tags.get("amenity", tags.get("shop", "другое"))
                    type_counts[amenity] = type_counts.get(amenity, 0) + 1

                for t, c in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:8]:
                    st.write(f"• {t}: **{c}**")
    else:
        st.info("👈 Нарисуйте область на карте")


# =============================================
# AI ПОРТРЕТ
# =============================================
st.markdown("---")

if st.session_state.organizations:
    st.subheader("🧠 AI-портрет квартала")

    if not st.session_state.portrait:
        if st.button("🎨 Сгенерировать анализ", type="primary"):
            with st.spinner("AI анализирует район..."):
                st.session_state.portrait = generate_portrait(st.session_state.org_text)
            st.rerun()

    if st.session_state.portrait:
        st.markdown(st.session_state.portrait)

        st.markdown("---")
        st.subheader("💬 Спросите про квартал")

        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.chat_message("user").write(msg["content"])
            else:
                st.chat_message("assistant").write(msg["content"])

        user_question = st.chat_input("Задайте вопрос...")

        if user_question:
            st.session_state.chat_history.append({"role": "user", "content": user_question})
            st.chat_message("user").write(user_question)

            with st.spinner("Думаю..."):
                answer = chat_answer(
                    user_question,
                    st.session_state.org_text,
                    st.session_state.chat_history
                )

            st.session_state.chat_history.append({"role": "assistant", "content": answer})
            st.rerun()

st.markdown("---")
st.markdown("Данные: OpenStreetMap | AI: OpenRouter | Интерфейс: Streamlit")
