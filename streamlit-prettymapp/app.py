import copy
import json
import requests
import time
import streamlit as st
from streamlit_image_select import image_select
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

from utils import (
    st_get_osm_geometries,
    st_plot_all,
    get_colors_from_style,
    gdf_to_bytesio_geojson,
)
from prettymapp.geo import GeoCodingError, get_aoi
from prettymapp.settings import STYLES

st.set_page_config(
    page_title="prettymapp", page_icon="🖼️", initial_sidebar_state="collapsed"
)
st.markdown("# Prettymapp")

# Popular areas for dropdown
POPULAR_AREAS = {
    "Major Cities": [
        "New York, NY, USA",
        "London, UK",
        "Paris, France",
        "Tokyo, Japan",
        "Sydney, Australia",
        "San Francisco, CA, USA",
        "Berlin, Germany",
        "Rome, Italy",
        "Barcelona, Spain",
        "Amsterdam, Netherlands"
    ],
    "Landmarks": [
        "Times Square, New York",
        "Eiffel Tower, Paris",
        "Big Ben, London",
        "Colosseum, Rome",
        "Golden Gate Bridge, San Francisco",
        "Central Park, New York",
        "Hyde Park, London",
        "Shibuya Crossing, Tokyo",
        "Las Ramblas, Barcelona",
        "Dam Square, Amsterdam"
    ],
    "Universities": [
        "Harvard University, Cambridge, MA",
        "Stanford University, Stanford, CA",
        "MIT, Cambridge, MA",
        "Oxford University, Oxford, UK",
        "Cambridge University, Cambridge, UK",
        "Sorbonne, Paris, France",
        "University of Tokyo, Tokyo, Japan",
        "ETH Zurich, Zurich, Switzerland"
    ]
}

def get_user_location():
    """Get user's approximate location using IP geolocation"""
    try:
        # Using ipapi.co for IP-based geolocation
        response = requests.get("https://ipapi.co/json/", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return f"{data.get('city', '')}, {data.get('region', '')}, {data.get('country_name', '')}"
    except:
        pass
    return None

@st.cache_data(ttl=300)  # Cache for 5 minutes
def search_locations(query, limit=5):
    """Search for locations using Nominatim geocoding service"""
    if not query or len(query) < 3:
        return []
    
    try:
        geolocator = Nominatim(user_agent="prettymapp_streamlit")
        # Search with structured query for better results
        locations = geolocator.geocode(
            query, 
            exactly_one=False, 
            limit=limit,
            timeout=3
        )
        
        if locations:
            results = []
            for location in locations:
                # Format the display name nicely
                display_name = location.address
                # Truncate if too long
                if len(display_name) > 60:
                    display_name = display_name[:57] + "..."
                
                results.append({
                    'display_name': display_name,
                    'full_address': location.address,
                    'lat': location.latitude,
                    'lon': location.longitude
                })
            return results
    except (GeocoderTimedOut, GeocoderServiceError):
        pass
    except Exception:
        pass
    
    return []

with open("./streamlit-prettymapp/examples.json", "r", encoding="utf8") as f:
    EXAMPLES = json.load(f)

if not st.session_state:
    st.session_state.update(EXAMPLES["Macau"])

    lc_class_colors = get_colors_from_style("Peach")
    st.session_state.lc_classes = list(lc_class_colors.keys())  # type: ignore
    st.session_state.update(lc_class_colors)
    st.session_state["previous_style"] = "Peach"
    st.session_state["previous_example_index"] = 0

# Initialize location-related session state
if "user_location" not in st.session_state:
    st.session_state.user_location = None
if "selected_area" not in st.session_state:
    st.session_state.selected_area = ""
if "search_query" not in st.session_state:
    st.session_state.search_query = ""
if "search_results" not in st.session_state:
    st.session_state.search_results = []

example_image_pattern = "streamlit-prettymapp/example_prints/{}_small.png"
example_image_fp = [
    example_image_pattern.format(name.lower()) for name in list(EXAMPLES.keys())[:4]
]
index_selected = image_select(
    "",
    images=example_image_fp,
    captions=list(EXAMPLES.keys())[:4],
    index=0,
    return_value="index",
)
if index_selected != st.session_state["previous_example_index"]:
    name_selected = list(EXAMPLES.keys())[index_selected]
    st.session_state.update(EXAMPLES[name_selected].copy())
    st.session_state["previous_example_index"] = index_selected

st.write("")

# Location options section
st.markdown("### 📍 Location Search")

# Real-time location search
search_col1, search_col2 = st.columns([2, 1])

with search_col1:
    # Create a container for the search interface
    search_container = st.container()
    
    with search_container:
        # Search input with real-time updates
        search_query = st.text_input(
            "🔍 Search for any location:",
            value=st.session_state.get("address", ""),
            placeholder="Type any city, landmark, address, or place name...",
            key="location_search",
            help="Start typing to see live search suggestions"
        )
        
        # Perform search when query changes and is long enough
        if search_query != st.session_state.search_query and len(search_query) >= 3:
            st.session_state.search_query = search_query
            with st.spinner("Searching locations..."):
                st.session_state.search_results = search_locations(search_query)
        elif len(search_query) < 3:
            st.session_state.search_results = []
            st.session_state.search_query = search_query
        
        # Display search results
        if st.session_state.search_results and len(search_query) >= 3:
            st.markdown("**Search Results:**")
            for i, result in enumerate(st.session_state.search_results):
                if st.button(
                    f"📍 {result['display_name']}", 
                    key=f"search_result_{i}",
                    help=f"Coordinates: {result['lat']:.4f}, {result['lon']:.4f}"
                ):
                    st.session_state.address = result['full_address']
                    st.session_state.search_query = result['full_address']
                    st.success(f"Selected: {result['display_name']}")
                    st.rerun()

with search_col2:
    # Current location button
    if st.button("📍 Use My Location", help="Get your approximate location", type="secondary"):
        user_loc = get_user_location()
        if user_loc:
            st.session_state.address = user_loc
            st.session_state.search_query = user_loc
            st.success(f"Location: {user_loc}")
            st.rerun()
        else:
            st.error("Unable to get location")
    
    # Quick area search dropdown
    st.markdown("**Quick Search:**")
    area_category = st.selectbox(
        "Category:",
        options=[""] + list(POPULAR_AREAS.keys()),
        key="area_category"
    )
    
    if area_category:
        selected_area = st.selectbox(
            f"{area_category}:",
            options=[""] + POPULAR_AREAS[area_category],
            key="selected_area_dropdown"
        )
        
        if selected_area and selected_area != st.session_state.get("selected_area", ""):
            st.session_state.address = selected_area
            st.session_state.search_query = selected_area
            st.session_state.selected_area = selected_area
            st.success(f"Selected: {selected_area}")
            st.rerun()

# Add some spacing
st.markdown("---")

form = st.form(key="form_settings")
col1, col2, col3 = form.columns([3, 1, 1])

address = col1.text_input(
    "Location address",
    value=st.session_state.get("address", ""),
    key="address",
    help="This will be filled automatically when you use the search above"
)

# Remove the manual search suggestions since we now have real-time search
# if address and len(address) > 3:
#     col1.caption("💡 Try: 'Central Park NYC', 'Eiffel Tower', 'Times Square', or any specific address")

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

if style != st.session_state["previous_style"]:
    st.session_state.update(get_colors_from_style(style))  # type: ignore
draw_settings = copy.deepcopy(STYLES[style])
for lc_class in st.session_state.lc_classes:
    picked_color = col3style.color_picker(lc_class, key=lc_class)
    if "_" in lc_class:
        lc_class, idx = lc_class.split("_")
        draw_settings[lc_class]["cmap"][int(idx)] = picked_color  # type: ignore
    else:
        draw_settings[lc_class]["fc"] = picked_color

submit_button = form.form_submit_button(label="🗺️ Generate Map")

# Only proceed if we have an address
if address and submit_button:
    result_container = st.empty()
    with st.spinner("Creating map... (may take up to a minute)"):
        rectangular = shape != "circle"
        try:
            aoi = get_aoi(address=address, radius=radius, rectangular=rectangular)
        except GeoCodingError as e:
            st.error(f"ERROR: {str(e)}")
            st.error("💡 Try using the dropdown options above or check your address spelling.")
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
        st.pyplot(fig, pad_inches=0, bbox_inches="tight", transparent=True, dpi=300)

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

elif not address and submit_button:
    st.warning("⚠️ Please enter a location address or use one of the quick options above!")

st.markdown("---")

# Enhanced footer with tips
st.markdown("### 💡 Tips for Better Maps")
tips_col1, tips_col2 = st.columns(2)

with tips_col1:
    st.markdown("""
    **Real-time Location Search:**
    - Type any location to get live suggestions
    - Search works for cities, landmarks, addresses
    - Click on search results to select instantly
    - Use coordinates for precise locations
    """)

with tips_col2:
    st.markdown("""
    **Quick Options:**
    - Use "My Location" for current area
    - Browse popular places in dropdowns
    - Adjust radius for different map scales
    - Try different themes and customizations
    """)

st.write(
    "Share on social media with the hashtag [#prettymaps](https://twitter.com/search?q=%23prettymaps&src=typed_query) !"
)
st.markdown(
    "More infos and :star: at [github.com/chrieke/prettymapp](https://github.com/chrieke/prettymapp)"
)

st.session_state["previous_style"] = style
