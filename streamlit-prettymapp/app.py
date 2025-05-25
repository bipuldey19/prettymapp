import copy
import json
import requests

import streamlit as st
from streamlit_image_select import image_select

from utils import (
    st_get_osm_geometries,
    st_plot_all,
    get_colors_from_style,
    gdf_to_bytesio_geojson,
)
from prettymapp.geo import GeoCodingError, get_aoi
from prettymapp.settings import STYLES

@st.cache_data(ttl=300)
def search_locations(query, limit=5):
    if not query or len(query) < 2:
        return []
    
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                'q': query,
                'format': 'json',
                'limit': limit,
                'addressdetails': 1
            },
            headers={'User-Agent': 'prettymapp-streamlit/1.0'},
            timeout=10
        )
        response.raise_for_status()
        
        results = []
        for item in response.json():
            display_parts = []
            address = item.get('address', {})
            
            if name := item.get('name'):
                display_parts.append(name)
            if city := address.get('city') or address.get('town'):
                display_parts.append(city)
            if country := address.get('country'):
                display_parts.append(country)
            
            results.append({
                'display': ', '.join(display_parts) or item.get('display_name', 'Location'),
                'full': item.get('display_name', ''),
                'lat': float(item.get('lat', 0)),
                'lon': float(item.get('lon', 0)),
                'type': f"{item.get('type', 'place')} ({item.get('class', 'location')})",
                'importance': item.get('importance', 0)
            })
        
        return sorted(results, key=lambda x: -x['importance'])
    
    except Exception as e:
        st.error(f"Search error: {str(e)}")
        return []

st.set_page_config(
    page_title="prettymapp", page_icon="🖼️", initial_sidebar_state="collapsed"
)
st.markdown("# Prettymapp")

if not st.session_state:
    lc_class_colors = get_colors_from_style("Peach")
    st.session_state.lc_classes = list(lc_class_colors.keys())  # type: ignore
    st.session_state.update(lc_class_colors)
    st.session_state["previous_style"] = "Peach"
    st.session_state["search_query"] = ""
    st.session_state["selected_location"] = None
    st.session_state["draw_settings"] = copy.deepcopy(STYLES["Peach"])

st.write("")
form = st.form(key="form_settings")
col1, col2, col3 = form.columns([3, 1, 1])

# Search box for location
search_query = col1.text_input(
    "Search location",
    key="search_query",
    placeholder="Type to search for a location..."
)

# Show search results if query is long enough
if search_query and len(search_query) >= 2:
    search_results = search_locations(search_query)
    if search_results:
        # Display results in a more detailed format
        selected_location = col1.selectbox(
            "Select location",
            options=search_results,
            format_func=lambda x: f"{x['display']} ({x['type']})",
            key="selected_location"
        )
        if selected_location:
            address = selected_location['full']
            # Show additional details about the selected location
            col1.markdown(f"**Selected Location Details:**")
            col1.markdown(f"📍 {selected_location['display']}")
            col1.markdown(f"🌍 {selected_location['type']}")
            col1.markdown(f"📌 {selected_location['full']}")
        else:
            address = search_query
    else:
        address = search_query
        col1.info("No locations found. Try a different search term.")
else:
    address = search_query

radius = col2.slider(
    "Radius (meter)",
    100,
    1500,
    key="radius",
)

style: str = col3.selectbox(
    "Color theme",
    options=list(STYLES.keys()),
    key="style",
)

# Update theme colors when style changes
if style != st.session_state["previous_style"]:
    lc_class_colors = get_colors_from_style(style)
    st.session_state.lc_classes = list(lc_class_colors.keys())  # type: ignore
    st.session_state.update(lc_class_colors)
    st.session_state["draw_settings"] = copy.deepcopy(STYLES[style])
    st.session_state["previous_style"] = style

draw_settings = st.session_state["draw_settings"]

expander = form.expander("Customize map style")
col1style, col2style, _, col3style = expander.columns([2, 2, 0.1, 1])

shape_options = ["circle", "rectangle"]
shape = col1style.radio(
    "Map Shape",
    options=shape_options,
    key="shape",
)

bg_shape_options = ["rectangle", "circle", None]
bg_shape = col1style.radio(
    "Background Shape",
    options=bg_shape_options,
    key="bg_shape",
)
bg_color = col1style.color_picker(
    "Background Color",
    key="bg_color",
)
bg_buffer = col1style.slider(
    "Background Size",
    min_value=0,
    max_value=50,
    help="How much the background extends beyond the figure.",
    key="bg_buffer",
)

col1style.markdown("---")
contour_color = col1style.color_picker(
    "Map contour color",
    key="contour_color",
)
contour_width = col1style.slider(
    "Map contour width",
    0,
    30,
    help="Thickness of contour line sourrounding the map.",
    key="contour_width",
)

name_on = col2style.checkbox(
    "Display title",
    help="If checked, adds the selected address as the title. Can be customized below.",
    key="name_on",
)
custom_title = col2style.text_input(
    "Custom title (optional)",
    max_chars=30,
    key="custom_title",
)
font_size = col2style.slider(
    "Title font size",
    min_value=1,
    max_value=50,
    key="font_size",
)
font_color = col2style.color_picker(
    "Title font color",
    key="font_color",
)
text_x = col2style.slider(
    "Title left/right",
    -100,
    100,
    key="text_x",
)
text_y = col2style.slider(
    "Title top/bottom",
    -100,
    100,
    key="text_y",
)
text_rotation = col2style.slider(
    "Title rotation",
    -90,
    90,
    key="text_rotation",
)

for lc_class in st.session_state.lc_classes:
    picked_color = col3style.color_picker(lc_class, key=lc_class)
    if "_" in lc_class:
        lc_class, idx = lc_class.split("_")
        draw_settings[lc_class]["cmap"][int(idx)] = picked_color  # type: ignore
    else:
        draw_settings[lc_class]["fc"] = picked_color

form.form_submit_button(label="Submit")

result_container = st.empty()
with st.spinner("Creating map... (may take up to a minute)"):
    rectangular = shape != "circle"
    try:
        aoi = get_aoi(address=address, radius=radius, rectangular=rectangular)
    except GeoCodingError as e:
        st.error(f"ERROR: {str(e)}")
        st.stop()
    df = st_get_osm_geometries(aoi=aoi)
    config = {
        "aoi_bounds": aoi.bounds,
        "draw_settings": draw_settings,
        "name_on": name_on,
        "name": address if custom_title == "" else custom_title,
        "font_size": font_size,
        "font_color": font_color,
        "text_x": text_x,
        "text_y": text_y,
        "text_rotation": text_rotation,
        "shape": shape,
        "contour_width": contour_width,
        "contour_color": contour_color,
        "bg_shape": bg_shape,
        "bg_buffer": bg_buffer,
        "bg_color": bg_color,
    }
    fig = st_plot_all(_df=df, **config)
    # result_container.write(html, unsafe_allow_html=True)
    st.pyplot(fig, pad_inches=0, bbox_inches="tight", transparent=True, dpi=300)

# svg_string = plt_to_svg(fig)
# html = svg_to_html(svg_string)
# st.write("")
# fname = slugify(address)
# img_format = st.selectbox("Download image as", ["svg", "png", "jpg"], index=0)
# if img_format == "svg":
#     data = svg_string
# elif img_format == "png":
#     import io
#
#     data = io.BytesIO()
#     fig.savefig(data, pad_inches=0, bbox_inches="tight", transparent=True)
# st.download_button(label="Download image", data=data, file_name=f"{fname}.{img_format}")

st.markdown("</br>", unsafe_allow_html=True)
st.markdown("</br>", unsafe_allow_html=True)
ex1, ex2 = st.columns(2)

with ex1.expander("Export geometries as GeoJSON"):
    st.write(f"{df.shape[0]} geometries")
    st.download_button(
        label="Download",
        data=gdf_to_bytesio_geojson(df),
        file_name=f"prettymapp_{address[:10]}.geojson",
        mime="application/geo+json",
    )

config = {"address": address, **config}
with ex2.expander("Export map configuration"):
    st.write(config)


st.markdown("---")
st.write(
    "Share on social media with the hashtag [#prettymaps](https://twitter.com/search?q=%23prettymaps&src=typed_query) !"
)
st.markdown(
    "More infos and :star: at [github.com/chrieke/prettymapp](https://github.com/chrieke/prettymapp)"
)