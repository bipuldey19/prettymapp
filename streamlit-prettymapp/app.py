import copy
import json
import requests
import time
import streamlit as st
import geopandas as gpd
import tempfile
import os
from io import BytesIO
import zipfile

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

# Custom CSS for better styling
st.markdown("""
<style>
.location-search-container {
    background-color: #f0f2f6;
    padding: 1rem;
    border-radius: 0.5rem;
    margin-bottom: 1rem;
}
.search-result-btn {
    width: 100%;
    text-align: left;
    margin: 0.2rem 0;
}
.file-upload-section {
    background-color: #e8f4f8;
    padding: 1rem;
    border-radius: 0.5rem;
    border-left: 4px solid #0066cc;
}
.gps-loading {
    color: #0066cc;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)

st.markdown("# 🗺️ Prettymapp - Beautiful Maps Made Easy")

def get_user_location_js():
    return """
    <script>
    function getCurrentLocation() {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                function(position) {
                    const lat = position.coords.latitude;
                    const lon = position.coords.longitude;
                    
                    window.parent.document.dispatchEvent(
                        new CustomEvent('gpsLocation', {detail: {lat: lat, lon: lon}})
                    );
                },
                function(error) {
                    console.error('Geolocation error:', error);
                    alert('Unable to get location. Please check permissions.');
                },
                {enableHighAccuracy: true, timeout: 10000}
            );
        } else {
            alert('Geolocation not supported by this browser.');
        }
    }
    </script>
    """

@st.cache_data(ttl=300)
def search_locations(query, limit=8):
    """Enhanced location search with error handling"""
    if not query or len(query) < 2:
        return []
    
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                'q': query,
                'format': 'json',
                'limit': limit,
                'addressdetails': 1,
                'extratags': 1
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
                'display': ', '.join(display_parts) or item.get('display_name', 'Unnamed location'),
                'full': item.get('display_name', ''),
                'lat': float(item.get('lat', 0)),
                'lon': float(item.get('lon', 0)),
                'type': f"{item.get('type', 'location')} ({item.get('class', 'place')})",
                'importance': item.get('importance', 0)
            })
        
        return sorted(results, key=lambda x: -x['importance'])
    
    except Exception as e:
        st.error(f"Search error: {str(e)}")
        return []

def process_uploaded_file(uploaded_file):
    """File upload handling with better error feedback"""
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

def create_style_selector():
    """Style selector with error-resistant implementation"""
    st.markdown("#### 🎨 Choose Your Map Style")
    cols = st.columns(4)
    styles = list(STYLES.keys())
    
    current_style = st.session_state.get('style', 'Peach')
    
    for idx, style in enumerate(styles):
        with cols[idx % 4]:
            if st.button(
                f"🏞️ {style}",
                key=f"style_{style}",
                use_container_width=True,
                type="primary" if style == current_style else "secondary"
            ):
                st.session_state.style = style
                st.rerun()
    
    return current_style

# Initialize session state
if 'search_results' not in st.session_state:
    st.session_state.search_results = []
if 'location' not in st.session_state:
    st.session_state.location = {'lat': None, 'lon': None}

# Geolocation handling
components_html = get_user_location_js()
st.components.v1.html(components_html, height=0)

# File upload section
with st.expander("📁 Upload Custom Boundaries (Optional)", expanded=False):
    uploaded_file = st.file_uploader(
        "Upload KML/GeoJSON/Zipped Shapefile",
        type=['kml', 'zip', 'geojson', 'json'],
        help="Supported formats: KML, GeoJSON, zipped Shapefile"
    )
    
    if uploaded_file:
        with st.spinner("Processing geospatial file..."):
            if gdf := process_uploaded_file(uploaded_file):
                st.session_state.uploaded_gdf = gdf
                st.success(f"Loaded {len(gdf)} features")
                st.map(gdf)
    
    if 'uploaded_gdf' in st.session_state:
        if st.button("Clear Uploaded Data"):
            del st.session_state.uploaded_gdf

# Location search section
st.markdown("### 🔍 Location Search")
col1, col2 = st.columns([3, 1])

with col1:
    search_query = st.text_input(
        "Search address or place name:",
        placeholder="E.g. 'Central Park NYC', 'Tokyo Station'...",
        key="search_input"
    )
    
    if len(search_query) >= 3:
        with st.spinner("Searching locations..."):
            st.session_state.search_results = search_locations(search_query)

with col2:
    if st.button("📍 Use My Location", help="Get current location using GPS"):
        st.components.v1.html(get_user_location_js(), height=0)
        st.session_state.gps_loading = True

if getattr(st.session_state, 'gps_loading', False):
    with st.status("Getting GPS location..."):
        time.sleep(2)
        if st.session_state.location.get('lat'):
            st.success(f"Found location: {st.session_state.location['lat']:.4f}, {st.session_state.location['lon']:.4f}")
        else:
            st.error("Could not retrieve location")

# Display search results with error handling
if st.session_state.search_results:
    st.markdown("**🔍 Search Results:**")
    for result in st.session_state.search_results[:5]:
        cols = st.columns([4, 1])
        display_text = result.get('display', 'Unnamed location')
        result_type = result.get('type', 'location')
        
        cols[0].button(
            f"📍 {display_text}",
            key=f"result_{display_text}",
            use_container_width=True,
            on_click=lambda r=result: st.session_state.update({
                'address': r.get('full', ''),
                'lat': r.get('lat', 0),
                'lon': r.get('lon', 0)
            })
        )
        cols[1].markdown(f"_{result_type}_")

# Main form
form = st.form(key="main_form")
selected_style = create_style_selector()

with form:
    col1, col2 = st.columns(2)
    address = col1.text_input("Selected Location", key="address")
    radius = col2.slider("Radius (meters)", 100, 2000, 500)
    
    # Advanced settings
    with st.expander("⚙️ Advanced Settings"):
        bg_color = st.color_picker("Background Color", key="bg_color")
        shape = st.selectbox("Map Shape", ["circle", "rectangle"], key="shape")
        contour_width = st.slider("Border Width", 0, 10, 2, key="border_width")
    
    if form.form_submit_button("🖼️ Generate Map", type="primary"):
        if not address and 'uploaded_gdf' not in st.session_state:
            st.warning("Please select a location or upload boundaries")
        else:
            with st.status("Creating your map..."):
                try:
                    config = {
                        'draw_settings': STYLES[selected_style],
                        'bg_color': bg_color,
                        'shape': shape,
                        'contour_width': contour_width
                    }
                    
                    if 'uploaded_gdf' in st.session_state:
                        gdf = st.session_state.uploaded_gdf
                        config['custom_title'] = "Custom Area"
                    else:
                        aoi = get_aoi(address=address, radius=radius)
                        gdf = st_get_osm_geometries(aoi)
                        config['name'] = address
                    
                    fig = st_plot_all(gdf, **config)
                    st.pyplot(fig)
                    st.success("Map created successfully!")
                
                except Exception as e:
                    st.error(f"Map creation failed: {str(e)}")
                    st.error("Try adjusting the location or radius")

# GPS listener and handler
if not hasattr(st.session_state, 'gps_listener_added'):
    st.components.v1.html("""
    <script>
    window.addEventListener('gpsLocation', function(e) {
        const data = e.detail;
        window.parent.document.dispatchEvent(
            new CustomEvent('gpsReceived', {detail: data})
        );
    });
    </script>
    """, height=0)
    st.session_state.gps_listener_added = True

# Handle GPS coordinates display
if st.session_state.location.get('lat'):
    st.write(f"GPS Coordinates: {st.session_state.location['lat']:.4f}, {st.session_state.location['lon']:.4f}")
