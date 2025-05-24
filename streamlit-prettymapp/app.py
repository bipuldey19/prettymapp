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

import geopandas as gpd
import pandas as pd
import requests
import streamlit as st
from matplotlib.patches import Patch
from shapely.geometry import Polygon
from prettymapp.geo import get_aoi
from prettymapp.osm import get_osm_geometries
from prettymapp.plotting import Plot
from prettymapp.settings import STYLES

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
    padding: 1rem;
    border-radius: 0.5rem;
    margin-bottom: 1rem;
}
.file-upload-section {
    background-color: #e8f4f8;
    padding: 1rem;
    border-radius: 0.5rem;
    border-left: 4px solid #0066cc;
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

def create_style_selector():
    st.markdown("#### 🎨 Choose Your Map Style")
    cols = st.columns(4)
    styles = list(STYLES.keys())
    
    current_style = st.session_state.get('style', 'Peach')
    
    for idx, style in enumerate(styles):
        with cols[idx % 4]:
            if st.button(
                f"🏞️ {style}",
                key=f"style_btn_{style}",
                use_container_width=True,
                type="primary" if style == current_style else "secondary"
            ):
                st.session_state.style = style
    return current_style

# Initialize session state
if 'search_results' not in st.session_state:
    st.session_state.search_results = []
if 'location' not in st.session_state:
    st.session_state.location = {'lat': None, 'lon': None}

# File upload section
with st.expander("📁 Upload Custom Boundaries", expanded=False):
    uploaded_file = st.file_uploader(
        "Upload KML/GeoJSON/Zipped Shapefile",
        type=['kml', 'zip', 'geojson', 'json'],
        help="Supported formats: KML, GeoJSON, zipped Shapefile"
    )
    
    if uploaded_file:
        with st.spinner("Processing file..."):
            if gdf := process_uploaded_file(uploaded_file):
                st.session_state.uploaded_gdf = gdf
                st.success(f"Loaded {len(gdf)} features")
                st.map(gdf)
    
    if 'uploaded_gdf' in st.session_state:
        if st.button("Clear Uploaded Data"):
            del st.session_state.uploaded_gdf
            st.rerun()

# Location search
st.markdown("### 🔍 Location Search")
col1, col2 = st.columns([3, 1])

with col1:
    search_query = st.text_input(
        "Search address or place name:",
        placeholder="E.g. 'Central Park NYC', 'Tokyo Station'...",
        key="search_input"
    )
    
    if len(search_query) >= 3:
        with st.spinner("Searching..."):
            st.session_state.search_results = search_locations(search_query)

with col2:
    if st.button("📍 Use My Location"):
        st.components.v1.html("""
        <script>
        function getCurrentLocation() {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    position => {
                        const lat = position.coords.latitude;
                        const lon = position.coords.longitude;
                        window.parent.document.dispatchEvent(
                            new CustomEvent('gpsLocation', {detail: {lat: lat, lon: lon}})
                        );
                    },
                    error => console.error('Geolocation error:', error),
                    {enableHighAccuracy: true, timeout: 10000}
                );
            }
        }
        getCurrentLocation();
        </script>
        """, height=0)

# Display search results
if st.session_state.search_results:
    st.markdown("**🔍 Search Results:**")
    for idx, result in enumerate(st.session_state.search_results):
        cols = st.columns([4, 1])
        display_text = result.get('display', 'Location')
        
        cols[0].button(
            f"📍 {display_text}",
            key=f"result_{idx}",
            use_container_width=True,
            on_click=lambda r=result: st.session_state.update({
                'address': r.get('full', ''),
                'lat': r.get('lat', 0),
                'lon': r.get('lon', 0)
            })
        )
        cols[1].markdown(f"_{result.get('type', 'location')}_")

# Main form
form = st.form(key="main_form")
selected_style = create_style_selector()

with form:
    col1, col2 = st.columns(2)
    address = col1.text_input("Location Name", key="address")
    radius = col2.slider("Radius (meters)", 100, 2000, 500)
    custom_title = st.text_input("Custom Title", key="custom_title", value="My Custom Map")
    
    with st.expander("⚙️ Advanced Settings"):
        bg_color = st.color_picker("Background Color", "#ffffff")
        shape = st.selectbox("Map Shape", ["circle", "rectangle"])
        contour_width = st.slider("Border Width", 0, 10, 2)
        font_size = st.slider("Title Size", 8, 40, 16)
        
        # Visualization controls
        show_legend = st.checkbox("Show Legend", True)
        show_feature_names = st.checkbox("Show Feature Names", False)
        show_copyright = st.checkbox("Show Copyright Info", False)

    # Legend customization
    legend_labels = {}
    with st.expander("📖 Edit Legend Labels"):
        default_features = ['building', 'water', 'green', 'park', 'highway']
        for feature in default_features:
            legend_labels[feature] = st.text_input(
                f"Label for {feature}",
                value=feature.title(),
                key=f"legend_{feature}"
            )

    if form.form_submit_button("🖼️ Generate Map", type="primary"):
        if not address and 'uploaded_gdf' not in st.session_state:
            st.warning("Please select a location or upload boundaries")
        else:
            with st.status("Creating map...", expanded=True) as status:
                try:
                    config = {
                        'draw_settings': STYLES[selected_style],
                        'bg_color': bg_color,
                        'shape': shape,
                        'contour_width': contour_width,
                        'font_size': font_size,
                        'name': custom_title,
                        'name_on': True,
                    }

                    if 'uploaded_gdf' in st.session_state:
                        gdf = st.session_state.uploaded_gdf
                        config['aoi_bounds'] = gdf.total_bounds
                    else:
                        aoi = get_aoi(address=address, radius=radius)
                        gdf = st_get_osm_geometries(aoi)
                        config['aoi_bounds'] = aoi.bounds

                    # Generate plot
                    fig = st_plot_all(gdf, **config)
                    ax = fig.gca()

                    # Add feature names
                    if show_feature_names:
                        for _, row in gdf.iterrows():
                            if 'name' in row and pd.notnull(row['name']):
                                ax.text(
                                    row.geometry.centroid.x,
                                    row.geometry.centroid.y,
                                    row['name'],
                                    fontsize=8,
                                    ha='center',
                                    va='center',
                                    color='black',
                                    fontfamily='serif'
                                )

                    # Add legend
                    if show_legend:
                        legend_elements = []
                        for ft in ['building', 'water', 'green', 'park', 'highway']:
                            if ft in STYLES[selected_style]:
                                legend_elements.append(
                                    Patch(
                                        facecolor=STYLES[selected_style][ft]['fc'],
                                        label=legend_labels.get(ft, ft.title()),
                                        edgecolor='black',
                                        linewidth=0.5
                                    )
                                )
                        
                        legend = ax.legend(
                            handles=legend_elements,
                            loc='upper right',
                            bbox_to_anchor=(1, 1),
                            prop={'family': 'serif', 'size': 10},
                            title='Legend',
                            title_fontproperties={'family': 'serif', 'weight': 'bold', 'size': 12},
                            frameon=True,
                            framealpha=0.9,
                            edgecolor='black'
                        )
                        legend.get_frame().set_facecolor('#ffffff')

                    # Style title
                    if custom_title:
                        ax.title.set_fontfamily('serif')
                        ax.title.set_fontweight('bold')

                    # Add custom copyright
                    if show_copyright:
                        ax.text(
                            0.5, -0.05, "© OpenStreetMap contributors",
                            ha='center', va='center',
                            transform=ax.transAxes,
                            fontsize=8,
                            color='gray',
                            fontfamily='serif'
                        )

                    st.pyplot(fig)
                    status.update(label="Map created successfully!", state="complete")
                    
                except Exception as e:
                    st.error(f"Map creation failed: {str(e)}")
                    st.error("Try adjusting the location or radius")

# Show GPS coordinates if available
if st.session_state.location.get('lat'):
    st.write(f"GPS Coordinates: {st.session_state.location['lat']:.4f}, {st.session_state.location['lon']:.4f}")
