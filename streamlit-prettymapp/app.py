import base64
import io
import json
import os
import re
import tempfile
import time
import unicodedata
import zipfile
from io import BytesIO, StringIO
from typing import Any
import copy

import geopandas as gpd
import pandas as pd
import requests
import streamlit as st
from matplotlib import font_manager
from matplotlib.patches import Patch
from shapely.geometry import Polygon
from prettymapp.geo import get_aoi
from prettymapp.osm import get_osm_geometries
from prettymapp.plotting import Plot
from prettymapp.settings import STYLES
from utils import get_colors_from_style

def gdf_to_bytesio_geojson(gdf: gpd.GeoDataFrame) -> BytesIO:
    """Convert GeoDataFrame to GeoJSON bytes"""
    geojson_str = gdf.to_json()
    return BytesIO(geojson_str.encode())

st.set_page_config(
    page_title="prettymapp", 
    page_icon="🖼️", 
    initial_sidebar_state="collapsed"
)

# Custom CSS
st.markdown("""
<style>
.location-search-container {
    background-color: #f0f2f6;
    padding: 1.5rem;
    border-radius: 0.5rem;
    margin-bottom: 1rem;
}
.search-button {
    margin-top: 1.5rem;
}
</style>
""", unsafe_allow_html=True)

st.markdown("# 🗺️ Prettymapp - Beautiful Maps Made Easy")

@st.cache_data(
    show_spinner=False, 
    hash_funcs={Polygon: lambda x: json.dumps(x.__geo_interface__)}
)
def st_get_osm_geometries(aoi):
    """Wrapper to enable streamlit caching for package function"""
    df = get_osm_geometries(aoi=aoi)
    return df

@st.cache_data(show_spinner=False)
def st_plot_all(_df: gpd.GeoDataFrame, **kwargs):
    """Modified plotting function with copyright removal"""
    plot = Plot(_df, **kwargs)
    fig = plot.plot_all()
    ax = fig.gca()
    
    # Remove default copyright text
    for text in ax.texts:
        if '© OpenStreetMap' in text.get_text():
            text.set_visible(False)
    
    return fig

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

def process_uploaded_file(uploaded_file):
    try:
        if uploaded_file.name.endswith('.kml'):
            return gpd.read_file(uploaded_file)
        
        if uploaded_file.name.endswith('.zip'):
            with tempfile.TemporaryDirectory() as tmpdir:
                with zipfile.ZipFile(uploaded_file) as z:
                    z.extractall(tmpdir)
                
                for f in os.listdir(tmpdir):
                    if f.endswith('.shp'):
                        return gpd.read_file(os.path.join(tmpdir, f))
                st.error("No shapefile found in ZIP archive")
        
        elif uploaded_file.name.endswith(('.geojson', '.json')):
            return gpd.read_file(uploaded_file)
            
    except Exception as e:
        st.error(f"File processing failed: {str(e)}")
    return None

# Initialize session state for selected location
if 'selected_location' not in st.session_state:
    st.session_state.selected_location = None

# File upload section
with st.expander("📁 Upload Custom Boundaries", expanded=False):
    uploaded_file = st.file_uploader(
        "Upload KML/GeoJSON/Zipped Shapefile",
        type=['kml', 'zip', 'geojson', 'json'],
        help="Supported formats: KML, GeoJSON, zipped Shapefile"
    )
    
    if uploaded_file:
        with st.spinner("Processing file..."):
            uploaded_gdf = process_uploaded_file(uploaded_file)
            if uploaded_gdf is not None:
                st.success(f"Loaded {len(uploaded_gdf)} features")
                st.map(uploaded_gdf)

# Location search
st.markdown("### 🔍 Location Search")
col1, col2 = st.columns([3, 1])

with col1:
    search_query = st.text_input(
        "Search address or place name:",
        placeholder="E.g. 'Central Park NYC', 'Tokyo Station'...",
    )
    
    if st.button("🔍 Search", use_container_width=True):
        if len(search_query) >= 3:
            with st.spinner("Searching..."):
                search_results = search_locations(search_query)
        else:
            st.warning("Please enter at least 3 characters to search")

# Display search results
if 'search_results' in locals() and search_results:
    st.markdown("**🔍 Search Results:**")
    for idx, result in enumerate(search_results):
        cols = st.columns([4, 1])
        display_text = result.get('display', 'Location')
        
        if cols[0].button(
            f"📍 {display_text}",
            key=f"result_{idx}",
            use_container_width=True
        ):
            st.session_state.selected_location = result
            st.experimental_rerun()
        cols[1].markdown(f"_{result.get('type', 'location')}_")

# Main form
form = st.form(key="form_settings")
col1, col2, col3 = form.columns([3, 1, 1])

# Initialize address with selected location if available
initial_address = ""
if st.session_state.selected_location:
    initial_address = st.session_state.selected_location.get('full', '')

address = col1.text_input(
    "Location address",
    value=initial_address
)
radius = col2.slider(
    "Radius (meter)",
    100,
    1500,
    500
)

style: str = col3.selectbox(
    "Color theme",
    options=list(STYLES.keys())
)

expander = form.expander("Customize map style")
col1style, col2style, _, col3style = expander.columns([2, 2, 0.1, 1])

shape_options = ["circle", "rectangle"]
shape = col1style.radio(
    "Map Shape",
    options=shape_options
)

bg_shape_options = ["rectangle", "circle", None]
bg_shape = col1style.radio(
    "Background Shape",
    options=bg_shape_options
)
bg_color = col1style.color_picker(
    "Background Color"
)
bg_buffer = col1style.slider(
    "Background Size",
    min_value=0,
    max_value=50,
    help="How much the background extends beyond the figure."
)

col1style.markdown("---")
contour_color = col1style.color_picker(
    "Map contour color"
)
contour_width = col1style.slider(
    "Map contour width",
    0,
    30,
    help="Thickness of contour line sourrounding the map."
)

name_on = col2style.checkbox(
    "Display title",
    help="If checked, adds the selected address as the title. Can be customized below."
)
custom_title = col2style.text_input(
    "Custom title (optional)",
    max_chars=30
)
font_size = col2style.slider(
    "Title font size",
    min_value=1,
    max_value=50
)
font_color = col2style.color_picker(
    "Title font color"
)
text_x = col2style.slider(
    "Title left/right",
    -100,
    100
)
text_y = col2.slider(
    "Title top/bottom",
    -100,
    100
)
text_rotation = col2.slider(
    "Title rotation",
    -90,
    90
)

draw_settings = copy.deepcopy(STYLES[style])
lc_classes = list(get_colors_from_style(style).keys())
for lc_class in lc_classes:
    picked_color = col3style.color_picker(lc_class)
    if "_" in lc_class:
        lc_class, idx = lc_class.split("_")
        draw_settings[lc_class]["cmap"][int(idx)] = picked_color  # type: ignore
    else:
        draw_settings[lc_class]["fc"] = picked_color

submit_button = form.form_submit_button("🖼️ Generate Map", type="primary")

if submit_button:
    if not address and 'uploaded_gdf' not in locals():
        st.warning("Please select a location or upload boundaries")
    else:
        with st.status("Creating map...", expanded=True) as status:
            try:
                config = {
                    'draw_settings': draw_settings,
                    'bg_color': bg_color,
                    'shape': shape,
                    'contour_width': contour_width,
                    'name': address if custom_title == "" else custom_title,
                    'name_on': name_on,
                    'font_size': font_size,
                    'font_color': font_color,
                    'text_x': text_x,
                    'text_y': text_y,
                    'text_rotation': text_rotation,
                    'bg_shape': bg_shape,
                    'bg_buffer': bg_buffer,
                    'contour_color': contour_color,
                }

                if 'uploaded_gdf' in locals():
                    gdf = uploaded_gdf
                    config['aoi_bounds'] = gdf.total_bounds
                else:
                    aoi = get_aoi(address=address, radius=radius)
                    gdf = st_get_osm_geometries(aoi)
                    config['aoi_bounds'] = aoi.bounds

                # Generate plot
                fig = st_plot_all(gdf, **config)
                st.pyplot(fig)
                status.update(label="Map created successfully!", state="complete")
                
            except Exception as e:
                st.error(f"Map creation failed: {str(e)}")
                st.error("Try adjusting the location or radius")

# Export section
st.markdown("### 📤 Export")
ex1, ex2 = st.columns(2)

with ex1.expander("Export geometries as GeoJSON"):
    if 'gdf' in locals() and gdf is not None:
        st.write(f"{gdf.shape[0]} geometries")
        st.download_button(
            label="Download",
            data=gdf_to_bytesio_geojson(gdf),
            file_name=f"prettymapp_{address[:10]}.geojson",
            mime="application/geo+json",
        )
    else:
        st.info("Generate a map first to export geometries")

with ex2.expander("Export map configuration"):
    if 'config' in locals() and config is not None:
        st.write(config)
    else:
        st.info("Generate a map first to export configuration")