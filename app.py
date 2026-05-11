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

st.title("🏘️ Портрет квартала")
st.markdown("Обведите область на карте и получите анализ района по отзывам")

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
            "shapeOptions": {
                "color": "#ff6b6b",
                "fillOpacity": 0.3
            }
        },
        "rectangle": {
            "shapeOptions": {
                "color": "#ff6b6b",
                "fillOpacity": 0.3
            }
        }
    }
)
draw.add_to(m)

# =============================================
# ФУНКЦИЯ ЗАПРОСА К OVERPASS
# Пробует несколько серверов по очереди
# =============================================
def query_overpass(bbox):
    
    # Несколько зеркал Overpass API
    servers = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ]

    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"~"cafe|restaurant|bar|pharmacy|bank|clinic|gym|beauty|fast_food|pub|hotel"]({bbox});
      node["shop"]({bbox});
      node["leisure"~"fitness_centre|sports_centre"]({bbox});
    );
    out body;
    """

    for i, server in enumerate(servers):
        try:
            st.write(f"🔄 Пробуем сервер {i+1} из {len(servers)}...")
            
            response = requests.get(
                server,
                params={"data": query},
                timeout=30,
                headers={"User-Agent": "QuarterPortrait/1.0"}
            )

            # Проверяем статус
            st.write(f"📡 Статус ответа: {response.status_code}")
            
            if response.status_code != 200:
                st.write(f"⚠️ Сервер {i+1} вернул ошибку {response.status_code}, пробуем следующий...")
                continue

            # Проверяем что ответ не пустой
            if not response.text or len(response.text) < 10:
                st.write(f"⚠️ Сервер {i+1} вернул пустой ответ, пробуем следующий...")
                continue

            # Пробуем распарсить JSON
            data = response.json()
            elements = data.get("elements", [])
            
            st.write(f"✅ Сервер {i+1} ответил! Найдено элементов: {len(elements)}")
            return elements, None

        except requests.exceptions.Timeout:
            st.write(f"⏱️ Сервер {i+1} не ответил за 30 секунд, пробуем следующий...")
            time.sleep(2)
            continue
            
        except requests.exceptions.ConnectionError:
            st.write(f"🔌 Не удалось подключиться к серверу {i+1}, пробуем следующий...")
            time.sleep(2)
            continue
            
        except ValueError as e:
            st.write(f"📋 Сервер {i+1} вернул не JSON: {str(e)[:100]}")
            st.write(f"Первые 200 символов ответа: {response.text[:200]}")
            time.sleep(2)
            continue
            
        except Exception as e:
            st.write(f"❌ Неизвестная ошибка на сервере {i+1}: {str(e)}")
            time.sleep(2)
            continue

    return [], "Все серверы недоступны. Попробуйте позже."


# =============================================
# ИНТЕРФЕЙС
# =============================================
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Нарисуйте область")
    map_data = st_folium(m, width=700, height=500)

with col2:
    st.subheader("Результаты")

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

            # Считаем примерный размер области в км
            lat_km = (max_lat - min_lat) * 111
            lon_km = (max_lon - min_lon) * 111 * 0.6

            st.success("✅ Область выбрана!")
            st.write(f"📐 Примерный размер: {lat_km:.2f} x {lon_km:.2f} км")

            # Предупреждение если область слишком большая
            if lat_km > 3 or lon_km > 3:
                st.warning(
                    "⚠️ Область очень большая! "
                    "Рекомендуем выбрать квартал поменьше (до 1x1 км), "
                    "иначе запрос может зависнуть."
                )

            bbox = f"{min_lat},{min_lon},{max_lat},{max_lon}"
            st.code(f"bbox: {bbox}", language="text")

            if st.button("🔍 Найти организации", type="primary"):
                with st.spinner("Запрашиваем данные..."):
                    elements, error = query_overpass(bbox)

                if error:
                    st.error(f"❌ {error}")
                    st.info(
                        "💡 Совет: попробуйте выбрать меньшую область "
                        "или повторите попытку через минуту"
                    )

                elif not elements:
                    st.warning(
                        "🤷 Организации не найдены. "
                        "Попробуйте выбрать другую область или побольше."
                    )

                else:
                    st.success(f"🎉 Найдено {len(elements)} организаций!")

                    # Счётчики по типам
                    type_counts = {}
                    for el in elements:
                        tags = el.get("tags", {})
                        amenity = tags.get("amenity", tags.get("shop", "другое"))
                        type_counts[amenity] = type_counts.get(amenity, 0) + 1

                    # Показываем статистику
                    st.markdown("**📊 По категориям:**")
                    for amenity_type, count in sorted(
                        type_counts.items(), key=lambda x: x[1], reverse=True
                    )[:10]:
                        st.write(f"• {amenity_type}: **{count}**")

                    st.markdown("---")
                    st.markdown("**📍 Список (первые 30):**")

                    for el in elements[:30]:
                        tags = el.get("tags", {})
                        name = tags.get("name", "Без названия")
                        amenity = tags.get("amenity", tags.get("shop", "—"))
                        cuisine = tags.get("cuisine", "")

                        icon = "🏪"
                        if amenity in ["cafe", "restaurant", "fast_food"]:
                            icon = "☕"
                        elif amenity in ["bar", "pub"]:
                            icon = "🍺"
                        elif amenity == "pharmacy":
                            icon = "💊"
                        elif amenity == "bank":
                            icon = "🏦"
                        elif amenity in ["gym", "fitness_centre"]:
                            icon = "🏋️"
                        elif amenity in ["clinic", "doctors"]:
                            icon = "🏥"
                        elif amenity == "beauty":
                            icon = "💅"
                        elif amenity == "hotel":
                            icon = "🏨"

                        extra = f" ({cuisine})" if cuisine else ""
                        st.write(f"{icon} **{name}** — {amenity}{extra}")

                    st.session_state["organizations"] = elements
                    st.markdown("---")
                    st.info("🧠 Следующий шаг: подключить отзывы и AI-анализ")

    else:
        st.info("👈 Нарисуйте прямоугольник или полигон на карте слева")

st.markdown("---")
st.markdown("Данные: OpenStreetMap | Карта: Folium | Интерфейс: Streamlit")
