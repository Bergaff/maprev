import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import requests
import time
import json

st.set_page_config(
    page_title="Портрет квартала",
    page_icon="🏘️",
    layout="wide"
)

# =============================================
# GEMINI API KEY (из secrets)
# =============================================
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

# =============================================
# ФУНКЦИЯ ЗАПРОСА К OVERPASS
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

    for i, server in enumerate(servers):
        try:
            response = requests.get(
                server,
                params={"data": query},
                timeout=30,
                headers={"User-Agent": "QuarterPortrait/1.0"}
            )
            if response.status_code != 200:
                continue
            if not response.text or len(response.text) < 10:
                continue
            data = response.json()
            return data.get("elements", []), None
        except Exception:
            time.sleep(2)
            continue

    return [], "Все серверы недоступны. Попробуйте позже."


# =============================================
# ФУНКЦИЯ ГЕНЕРАЦИИ ПОРТРЕТА ЧЕРЕЗ GEMINI
# =============================================
def generate_portrait(organizations_text):
    if not GEMINI_KEY:
        return "❌ API ключ Gemini не настроен. Добавьте GEMINI_API_KEY в secrets."

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"

    prompt = f"""Ты — эксперт по городской среде и аналитик районов.

На основе списка организаций ниже составь подробный портрет квартала.

Ответь на русском языке по следующей структуре:

## 🏘️ Общий характер квартала
Опиши атмосферу, тип района (деловой, спальный, туристический, молодёжный и т.д.)

## 👥 Кто здесь живёт / бывает
Опиши типичного жителя или посетителя этого квартала

## ☕ Еда и развлечения
Какие заведения преобладают, какая кухня, ценовой сегмент

## 🛍️ Шопинг и сервисы
Какие магазины и услуги доступны

## ✅ Плюсы квартала
Что хорошего

## ⚠️ Чего не хватает
Какие сервисы или заведения отсутствуют

## 💡 Идеи для бизнеса
Какой бизнес мог бы быть успешен в этом квартале

Вот список организаций в квартале:

{organizations_text}
"""

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return text
        else:
            return f"❌ Ошибка Gemini API: {response.status_code}\n{response.text[:300]}"

    except Exception as e:
        return f"❌ Ошибка: {str(e)}"


# =============================================
# ФУНКЦИЯ ЧАТА С GEMINI
# =============================================
def chat_with_gemini(question, organizations_text, chat_history):
    if not GEMINI_KEY:
        return "❌ API ключ Gemini не настроен."

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"

    # Собираем контекст из истории чата
    history_text = ""
    for msg in chat_history[-6:]:  # последние 6 сообщений
        role = "Пользователь" if msg["role"] == "user" else "Ассистент"
        history_text += f"{role}: {msg['content']}\n"

    prompt = f"""Ты — эксперт по городской среде. Тебе доступен список организаций квартала.
Отвечай на русском языке. Будь конкретным и полезным.

Список организаций в квартале:

{organizations_text}

История диалога:
{history_text}

Вопрос пользователя: {question}

Ответ:"""

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        else:
            return f"❌ Ошибка: {response.status_code}"

    except Exception as e:
        return f"❌ Ошибка: {str(e)}"


# =============================================
# ИНИЦИАЛИЗАЦИЯ SESSION STATE
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
# ЗАГОЛОВОК
# =============================================
st.title("🏘️ Портрет квартала")
st.markdown("Обведите область на карте → получите AI-анализ района")


# =============================================
# КАРТА
# =============================================
moscow_center = [55.7558, 37.6173]

m = folium.Map(
    location=moscow_center,
    zoom_start=14,
    tiles="OpenStreetMap"
)

draw = Draw(
    export=False,
    draw_options={
        "polyline": False,
        "circle": False,
        "circlemarker": False,
        "marker": False,
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


# =============================================
# LAYOUT: КАРТА + РЕЗУЛЬТАТЫ
# =============================================
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📍 Нарисуйте область")
    map_data = st_folium(m, width=700, height=500)

with col2:
    st.subheader("📊 Организации")

    if map_data and map_data.get("last_active_drawing"):
        drawing = map_data["last_active_drawing"]
        geometry = drawing.get("geometry", {})
        coordinates = geometry.get("coordinates", [[]])

        if coordinates and coordinates[0]:
            coords = coordinates[0]
            lats = [c[1] for c in coords]
            lons = [c[0] for c in coords]

            min_lat, max_lat = min(lats), max(lats)
            min_lon, max_lon = min(lons), max(lons)

            lat_km = (max_lat - min_lat) * 111
            lon_km = (max_lon - min_lon) * 111 * 0.6

            st.success(f"✅ Область: {lat_km:.2f} x {lon_km:.2f} км")

            if lat_km > 3 or lon_km > 3:
                st.warning("⚠️ Слишком большая область. Выберите поменьше.")

            bbox = f"{min_lat},{min_lon},{max_lat},{max_lon}"

            if st.button("🔍 Найти организации", type="primary"):
                with st.spinner("Ищем через OpenStreetMap..."):
                    elements, error = query_overpass(bbox)

                if error:
                    st.error(error)
                elif not elements:
                    st.warning("Ничего не найдено.")
                else:
                    st.session_state.organizations = elements

                    # Формируем текст для AI
                    org_lines = []
                    for el in elements:
                        tags = el.get("tags", {})
                        name = tags.get("name", "Без названия")
                        amenity = tags.get("amenity", tags.get("shop", tags.get("tourism", tags.get("leisure", "другое"))))
                        cuisine = tags.get("cuisine", "")
                        extra = f" ({cuisine})" if cuisine else ""
                        org_lines.append(f"- {name}: {amenity}{extra}")

                    st.session_state.org_text = "\n".join(org_lines)
                    st.session_state.portrait = ""
                    st.session_state.chat_history = []

            # Показываем список если есть
            if st.session_state.organizations:
                elements = st.session_state.organizations
                st.success(f"🎉 Найдено {len(elements)} организаций")

                type_counts = {}
                for el in elements:
                    tags = el.get("tags", {})
                    amenity = tags.get("amenity", tags.get("shop", "другое"))
                    type_counts[amenity] = type_counts.get(amenity, 0) + 1

                for amenity_type, count in sorted(
                    type_counts.items(), key=lambda x: x[1], reverse=True
                )[:10]:
                    st.write(f"• {amenity_type}: **{count}**")

    else:
        st.info("👈 Нарисуйте область на карте")


# =============================================
# ПОРТРЕТ КВАРТАЛА (AI)
# =============================================
st.markdown("---")

if st.session_state.organizations:
    st.subheader("🧠 AI-портрет квартала")

    if not st.session_state.portrait:
        if st.button("🎨 Сгенерировать портрет квартала", type="primary"):
            with st.spinner("AI анализирует квартал... (10-20 секунд)"):
                portrait = generate_portrait(st.session_state.org_text)
                st.session_state.portrait = portrait

    if st.session_state.portrait:
        st.markdown(st.session_state.portrait)


    # =============================================
    # ЧАТ-БОТ
    # =============================================
    st.markdown("---")
    st.subheader("💬 Задайте вопрос про квартал")
    st.markdown("Спросите что угодно: какой бизнес открыть, безопасно ли, есть ли парки и т.д.")

    # Показываем историю чата
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.chat_message("user").write(msg["content"])
        else:
            st.chat_message("assistant").write(msg["content"])

    # Поле ввода
    user_question = st.chat_input("Введите вопрос про этот квартал...")

    if user_question:
        # Добавляем вопрос в историю
        st.session_state.chat_history.append({"role": "user", "content": user_question})
        st.chat_message("user").write(user_question)

        # Получаем ответ от Gemini
        with st.spinner("Думаю..."):
            answer = chat_with_gemini(
                user_question,
                st.session_state.org_text,
                st.session_state.chat_history
            )

        # Добавляем ответ в историю
        st.session_state.chat_history.append({"role": "assistant", "content": answer})
        st.chat_message("assistant").write(answer)


# =============================================
# ФУТЕР
# =============================================
st.markdown("---")
st.markdown("Данные: OpenStreetMap | AI: Google Gemini | Интерфейс: Streamlit")
