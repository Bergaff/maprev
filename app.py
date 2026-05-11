import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import requests
import time
import google.generativeai as genai

st.set_page_config(
    page_title="Портрет квартала",
    page_icon="🏘️",
    layout="wide"
)

# =============================================
# НАСТРОЙКА GEMINI API
# =============================================
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

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

    return [], "Все серверы OpenStreetMap недоступны. Попробуйте позже."


# =============================================
# ФУНКЦИЯ ГЕНЕРАЦИИ ПОРТРЕТА (Официальный SDK)
# =============================================
def generate_portrait(organizations_text):
    if not GEMINI_KEY:
        return "❌ API ключ Gemini не настроен. Добавьте GEMINI_API_KEY в secrets Streamlit."

    prompt = f"""Ты — эксперт по городской среде, урбанист и бизнес-аналитик районов.

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
Что здесь хорошего, в чём сила локации

## ⚠️ Чего не хватает
Какие базовые или трендовые сервисы отсутствуют

## 💡 Идеи для бизнеса
Какой бизнес с высокой вероятностью взлетит в этом квартале (кофейня, прачечная, бар, йога и т.д.)

Вот список организаций в квартале:
{organizations_text}
"""

    try:
        # Используем стабильную модель 1.5 Flash через SDK
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ Ошибка генерации Gemini: {str(e)}"


# =============================================
# ФУНКЦИЯ ЧАТА С GEMINI (Официальный SDK)
# =============================================
def chat_with_gemini(question, organizations_text, chat_history):
    if not GEMINI_KEY:
        return "❌ API ключ Gemini не настроен."

    # Собираем контекст из последних сообщений
    history_text = ""
    for msg in chat_history[-6:]:
        role = "Пользователь" if msg["role"] == "user" else "Ассистент"
        history_text += f"{role}: {msg['content']}\n"

    full_prompt = f"""Ты — бизнес-консультант и эксперт по городской среде. Тебе доступен список организаций квартала.
Отвечай на русском языке. Будь конкретным, предлагай реальные идеи.

Список организаций в квартале:
{organizations_text}

История диалога:
{history_text}

Вопрос пользователя: {question}

Ответ:"""

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"❌ Ошибка ответа Gemini: {str(e)}"


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
# ИНТЕРФЕЙС: ЗАГОЛОВОК И КАРТА
# =============================================
st.title("🏘️ Портрет квартала")
st.markdown("Обведите область на карте → получите AI-анализ района и пообщайтесь с чат-ботом")

moscow_center = [55.7558, 37.6173]
m = folium.Map(location=moscow_center, zoom_start=14, tiles="OpenStreetMap")

draw = Draw(
    export=False,
    draw_options={
        "polyline": False, "circle": False, "circlemarker": False, "marker": False,
        "polygon": {"allowIntersection": False, "shapeOptions": {"color": "#ff6b6b", "fillOpacity": 0.3}},
        "rectangle": {"shapeOptions": {"color": "#ff6b6b", "fillOpacity": 0.3}}
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
        geometry = drawing.get("geometry", {})
        coordinates = geometry.get("coordinates", [[]])

        if coordinates and coordinates[0]:
            coords = coordinates[0]
            lats = [c[1] for c in coords]
            lons = [c[0] for c in coords]

            min_lat, max_lat = min(lats), max(lats)
            min_lon, max_lon = min(lons), max(lons)
            
            st.success("✅ Область выбрана")

            bbox = f"{min_lat},{min_lon},{max_lat},{max_lon}"

            if st.button("🔍 Найти организации", type="primary"):
                with st.spinner("Ищем через OpenStreetMap..."):
                    elements, error = query_overpass(bbox)

                if error:
                    st.error(error)
                elif not elements:
                    st.warning("Организации не найдены.")
                else:
                    st.session_state.organizations = elements

                    # Формируем сжатый текст для AI
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

            # Статистика
            if st.session_state.organizations:
                elements = st.session_state.organizations
                st.success(f"🎉 Найдено {len(elements)} мест")

                type_counts = {}
                for el in elements:
                    tags = el.get("tags", {})
                    amenity = tags.get("amenity", tags.get("shop", "другое"))
                    type_counts[amenity] = type_counts.get(amenity, 0) + 1

                for amenity_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:8]:
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
        if st.button("🎨 Сгенерировать анализ района", type="primary"):
            with st.spinner("AI изучает состав бизнесов... (10-15 секунд)"):
                st.session_state.portrait = generate_portrait(st.session_state.org_text)
                st.rerun()

    if st.session_state.portrait:
        st.markdown(st.session_state.portrait)

        # =============================================
        # ЧАТ-БОТ ПО КВАРТАЛУ
        # =============================================
        st.markdown("---")
        st.subheader("💬 Задайте вопрос урбанисту-аналитику")
        st.markdown("Спросите: *Чего здесь не хватает? Стоит ли открывать пекарню? Какая тут конкуренция по барбершопам?*")

        # Отрисовка истории сообщений
        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.chat_message("user").write(msg["content"])
            else:
                st.chat_message("assistant").write(msg["content"])

        # Поле ввода
        user_question = st.chat_input("Спросите что-нибудь про этот квартал...")

        if user_question:
            # Сразу показываем вопрос
            st.session_state.chat_history.append({"role": "user", "content": user_question})
            st.chat_message("user").write(user_question)

            # Запрашиваем ответ
            with st.spinner("Анализирую данные..."):
                answer = chat_with_gemini(
                    user_question,
                    st.session_state.org_text,
                    st.session_state.chat_history
                )

            # Показываем ответ
            st.session_state.chat_history.append({"role": "assistant", "content": answer})
            st.rerun()


# =============================================
# ФУТЕР
# =============================================
st.markdown("---")
st.markdown("Данные: OpenStreetMap | AI: Google Gemini SDK | Интерфейс: Streamlit")
