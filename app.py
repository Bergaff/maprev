import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import requests

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

            st.success("Область выбрана!")

            if st.button("Найти организации", type="primary"):
                with st.spinner("Ищем через OpenStreetMap..."):
                    bbox = f"{min(lats)},{min(lons)},{max(lats)},{max(lons)}"

                    overpass_query = f"""
                    [out:json][timeout:30];
                    (
                      node["amenity"~"cafe|restaurant|bar|shop|pharmacy|bank|clinic|gym"]({bbox});
                      node["shop"]({bbox});
                    );
                    out body;
                    """

                    try:
                        response = requests.get(
                            "http://overpass-api.de/api/interpreter",
                            params={"data": overpass_query},
                            timeout=30
                        )
                        data = response.json()
                        elements = data.get("elements", [])

                        if elements:
                            st.success(f"Найдено {len(elements)} организаций!")

                            for el in elements[:30]:
                                tags = el.get("tags", {})
                                name = tags.get("name", "Без названия")
                                amenity = tags.get("amenity", tags.get("shop", "—"))
                                cuisine = tags.get("cuisine", "")

                                icon = "🏪"
                                if amenity in ["cafe", "restaurant"]:
                                    icon = "☕"
                                elif amenity in ["bar", "pub"]:
                                    icon = "🍺"
                                elif amenity == "pharmacy":
                                    icon = "💊"
                                elif amenity == "bank":
                                    icon = "🏦"

                                extra = f" ({cuisine})" if cuisine else ""
                                st.write(f"{icon} {name} — {amenity}{extra}")

                        else:
                            st.warning("Ничего не найдено. Выберите область побольше.")

                    except Exception as e:
                        st.error(f"Ошибка: {e}")
    else:
        st.info("Нарисуйте прямоугольник или полигон на карте слева")

st.markdown("---")
st.markdown("Данные: OpenStreetMap | Карта: Folium | Интерфейс: Streamlit")
