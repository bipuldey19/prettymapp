import copy
import json
import requests
import time
import streamlit as st
from streamlit_image_select import image_select
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
.style-preview {
    border: 2px solid transparent;
    border-radius: 8px;
    padding: 10px;
    margin: 5px;
    cursor: pointer;
    transition: all 0.3s ease;
}
.style-preview:hover {
    border-color: #ff4b4b;
    transform: scale(1.02);
}
.style-preview.selected {
    border-color: #ff4b4b;
    background-color: #fff5f5;
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

# Popular areas for dropdown
POPULAR_AREAS = {
    "🏙️ Major Cities": [
        "New York, NY, USA",
        "London, UK",
        "Paris, France",
        "Tokyo, Japan",
        "Sydney, Australia",
        "San Francisco, CA, USA",
        "Berlin, Germany",
        "Rome, Italy",
        "Barcelona, Spain",
        "Amsterdam, Netherlands",
        "Dubai, UAE",
        "Singapore",
        "Toronto, Canada",
        "Mumbai, India",
        "São Paulo, Brazil"
    ],
    "🏛️ Famous Landmarks": [
        "Times Square, New York",
        "Eiffel Tower, Paris",
        "Big Ben, London",
        "Colosseum, Rome",
        "Golden Gate Bridge, San Francisco",
        "Central Park, New York",
        "Hyde Park, London",
        "Shibuya Crossing, Tokyo",
        "Las Ramblas, Barcelona",
        "Dam Square, Amsterdam",
        "Statue of Liberty, New York",
        "Tower Bridge, London",
        "Arc de Triomphe, Paris",
        "Brandenburg Gate, Berlin",
        "Sydney Opera House, Sydney"
    ],
    "🎓 Universities": [
        "Harvard University, Cambridge, MA",
        "Stanford University, Stanford, CA",
        "MIT, Cambridge, MA",
        "Oxford University, Oxford, UK",
        "Cambridge University, Cambridge, UK",
        "Sorbonne, Paris, France",
        "University of Tokyo, Tokyo, Japan",
        "ETH Zurich, Zurich, Switzerland",
        "Yale University, New Haven, CT",
        "Princeton University, Princeton, NJ"
    ],
    "🏞️ Natural Wonders": [
        "Central Park, New York",
        "Golden Gate Park, San Francisco",
        "Regent's Park, London",
        "Bois de Boulogne, Paris",
        "Ueno Park, Tokyo",
        "Royal Botanic Gardens, Sydney",
        "Tiergarten, Berlin",
        "Villa Borghese, Rome",
        "Vondelpark, Amsterdam",
        "Stanley Park, Vancouver"
    ]
}

def get_user_location_js():
    """Generate JavaScript for geolocation"""
    return """
    <script>
    function getCurrentLocation() {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                function(position) {
                    const lat = position.coords.latitude;
                    const lon = position.coords.longitude;
                    
                    // Use Nominatim for reverse geocoding
                    fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`)
                        .then(response => response.json())
                        .then(data => {
                            if (data && data.display_name) {
                                const event = new CustomEvent('locationFound', {
                                    detail: {
                                        address: data.display_name,
                                        lat: lat,
                                        lon: lon
                                    }
                                });
                                window.dispatchEvent(event);
                            }
                        })
                        .catch(error => {
                            console.error('Geocoding error:', error);
                            const event = new CustomEvent('locationFound', {
                                detail: {
                                    address: `${lat.toFixed(6)}, ${lon.toFixed(6)}`,
                                    lat: lat,
                                    lon: lon
                                }
                            });
                            window.dispatchEvent(event);
                        });
                },
                function(error) {
                    console.error('Geolocation error:', error);
                    alert('Unable to get your location. Please check browser permissions.');
                },
                {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 300000
                }
            );
        } else {
            alert('Geolocation is not supported by this browser.');
        }
    }
    </script>
    """

@st.cache_data(ttl=300)
def search_locations(query, limit=8):
    """Enhanced search for locations using OpenStreetMap Nominatim API"""
    if not query or len(query) < 2:
        return []
    
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': query,
            'format': 'json',
            'limit': limit,
            'addressdetails': 1,
            'extratags': 1,
            'namedetails': 1
        }
        
        headers = {
            'User-Agent': 'prettymapp-streamlit-app/1.0'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=8)
        
        if response.status_code == 200:
            data = response.json()
            results = []
            
            for item in data:
                # Create a more readable display name
                display_name = item.get('display_name', '')
                
                # Extract key components for better display
                name = item.get('name', '')
                address = item.get('address', {})
                
                # Build a cleaner display name
                parts = []
                if name:
                    parts.append(name)
                
                # Add city/town
                city = (address.get('city') or 
                       address.get('town') or 
                       address.get('village') or
                       address.get('municipality'))
                if city and city != name:
                    parts.append(city)
                
                # Add country
                country = address.get('country')
                if country:
                    parts.append(country)
                
                clean_name = ', '.join(parts) if parts else display_name
                
                # Limit length
                if len(clean_name) > 70:
                    clean_name = clean_name[:67] + "..."
                
                results.append({
                    'display_name': clean_name,
                    'full_address': display_name,
                    'lat': float(item.get('lat', 0)),
                    'lon': float(item.get('lon', 0)),
                    'importance': float(item.get('importance', 0)),
                    'type': item.get('type', ''),
                    'class': item.get('class', '')
                })
            
            # Sort by importance (higher first)
            results.sort(key=lambda x: x['importance'], reverse=True)
            return results
            
    except Exception as e:
        st.error(f"Search error: {str(e)}")
        return []
    
    return []

def process_uploaded_file(uploaded_file):
    """Process uploaded KML or SHP file"""
    try:
        if uploaded_file.name.endswith('.kml'):
            # Handle KML file
            gdf = gpd.read_file(uploaded_file)
            return gdf
        
        elif uploaded_file.name.endswith('.zip'):
            # Handle zipped shapefile
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract zip file
                with zipfile.ZipFile(uploaded_file, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                # Find .shp file
                shp_files = [f for f in os.listdir(temp_dir) if f.endswith('.shp')]
                if shp_files:
                    shp_path = os.path.join(temp_dir, shp_files[0])
                    gdf = gpd.read_file(shp_path)
                    return gdf
                else:
                    st.error("No .shp file found in the uploaded zip archive")
                    return None
        
        elif uploaded_file.name.endswith('.shp'):
            # Handle individual shapefile (note: needs associated files)
            st.warning("For shapefiles, please upload a ZIP file containing all associated files (.shp, .shx, .dbf, etc.)")
            return None
        
        else:
            st.error("Unsupported file format. Please upload KML or zipped shapefile.")
            return None
            
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        return None

def create_style_selector():
    """Create an enhanced style selector with previews"""
    st.markdown("#### 🎨 Choose Your Map Style")
    
    # Create style preview grid
    cols = st.columns(4)
    selected_style = st.session_state.get('style', 'Peach')
    
    style_descriptions = {
        'Peach': '🍑 Warm peach tones',
        'Auburn': '🍂 Rich autumn colors',
        'Barcelona': '🏛️ Mediterranean vibes',
        'Berlin': '🏙️ Urban minimalist',
        'BlackWhite': '⚫ Classic monochrome',
        'Blue': '💙 Ocean blues',
        'Cardiff': '🏰 Celtic charm',
        'Citrus': '🍊 Bright citrus pop',
        'CobaltBlue': '💎 Deep cobalt',
        'Flamingo': '🦩 Pink paradise',
        'GreenWhite': '🌿 Fresh nature',
        'Infrared': '🔴 Bold infrared',
        'Minimal': '⚪ Clean minimal',
        'OrangeWhite': '🧡 Vibrant orange',
        'Pink': '💗 Soft pink',
        'RedWhite': '❤️ Classic red',
    }
    
    styles_list = list(STYLES.keys())
    
    for i, style_name in enumerate(styles_list):
        col_idx = i % 4
        with cols[col_idx]:
            description = style_descriptions.get(style_name, f'🎨 {style_name}')
            
            # Create button for style selection
            is_selected = style_name == selected_style
            button_type = "primary" if is_selected else "secondary"
            
            if st.button(
                f"{description}",
                key=f"style_{style_name}",
                type=button_type,
                use_container_width=True
            ):
                st.session_state['style'] = style_name
                st.rerun()
    
    return selected_style

# Load examples
with open("./streamlit-prettymapp/examples.json", "r", encoding="utf8") as f:
    EXAMPLES = json.load(f)

# Initialize session state
if not st.session_state:
    st.session_state.update(EXAMPLES["Macau"])
    lc_class_colors = get_colors_from_style("Peach")
    st.session_state.lc_classes = list(lc_class_colors.keys())
    st.session_state.update(lc_class_colors)
    st.session_state["previous_style"] = "Peach"
    st.session_state["previous_example_index"] = 0

# Initialize additional session state
for key in ["user_location", "selected_area", "search_query", "search_results", "uploaded_gdf", "use_uploaded_file"]:
    if key not in st.session_state:
        st.session_state[key] = [] if key == "search_results" else None if key == "uploaded_gdf" else False if key == "use_uploaded_file" else ""

# JavaScript for geolocation
components_html = get_user_location_js()
st.components.v1.html(components_html, height=0)

# Example images
example_image_pattern = "streamlit-prettymapp/example_prints/{}_small.png"
example_image_fp = [
    example_image_pattern.format(name.lower()) for name in list(EXAMPLES.keys())[:4]
]

st.markdown("### 🖼️ Quick Start Examples")
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

st.markdown("---")

# File upload section
st.markdown("### 📁 Upload Your Own Boundaries (Optional)")
with st.container():
    st.markdown('<div class="file-upload-section">', unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_file = st.file_uploader(
            "Upload KML or zipped Shapefile to use custom boundaries",
            type=['kml', 'zip'],
            help="Upload a KML file or a ZIP file containing shapefile components (.shp, .shx, .dbf, etc.)"
        )
        
        if uploaded_file is not None:
            with st.spinner("Processing uploaded file..."):
                gdf = process_uploaded_file(uploaded_file)
                if gdf is not None:
                    st.session_state.uploaded_gdf = gdf
                    st.success(f"✅ File processed successfully! Found {len(gdf)} geometries.")
                    st.info("The uploaded boundaries will be used instead of the address location.")
    
    with col2:
        if st.session_state.uploaded_gdf is not None:
            use_uploaded = st.checkbox(
                "Use uploaded file boundaries",
                value=True,
                key="use_uploaded_file",
                help="Check to use uploaded boundaries, uncheck to use address location"
            )
            
            if st.button("Clear uploaded file"):
                st.session_state.uploaded_gdf = None
                st.session_state.use_uploaded_file = False
                st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("---")

# Enhanced location search section
st.markdown("### 🔍 Location Search")
st.markdown('<div class="location-search-container">', unsafe_allow_html=True)

search_col1, search_col2 = st.columns([3, 1])

with search_col1:
    # Real-time search input
    search_query = st.text_input(
        "🌍 Search for any location worldwide:",
        value=st.session_state.get("address", ""),
        placeholder="Try: 'Central Park NYC', 'Eiffel Tower', 'Tokyo Station', or any address...",
        key="location_search",
        help="Start typing to see live suggestions (works worldwide!)"
    )
    
    # Enhanced search with debouncing
    if search_query != st.session_state.search_query and len(search_query) >= 2:
        st.session_state.search_query = search_query
        if len(search_query) >= 3:  # Only search for 3+ characters
            with st.spinner("🔍 Searching locations..."):
                st.session_state.search_results = search_locations(search_query, limit=8)
    elif len(search_query) < 2:
        st.session_state.search_results = []
        st.session_state.search_query = search_query
    
    # Display enhanced search results
    if st.session_state.search_results and len(search_query) >= 2:
        st.markdown("**🎯 Search Results:**")
        
        # Group results by type for better organization
        for i, result in enumerate(st.session_state.search_results):
            col1, col2 = st.columns([4, 1])
            
            with col1:
                # Enhanced button with icons based on type
                icon = "🏛️" if result['class'] in ['historic', 'tourism'] else "🏙️" if result['class'] == 'place' else "📍"
                
                if st.button(
                    f"{icon} {result['display_name']}", 
                    key=f"search_result_{i}",
                    use_container_width=True
                ):
                    st.session_state.address = result['full_address']
                    st.session_state.search_query = result['full_address']
                    st.success(f"✅ Selected: {result['display_name']}")
                    st.rerun()
            
            with col2:
                st.caption(f"📊 {result['importance']:.2f}")

with search_col2:
    # Enhanced current location button
    if st.button("📍 My Location", help="Get your current location using GPS", type="secondary", use_container_width=True):
        st.markdown("""
        <script>
        getCurrentLocation();
        </script>
        """, unsafe_allow_html=True)
        st.info("🌐 Getting your location... Please allow location access if prompted.")
    
    st.markdown("---")
    
    # Enhanced quick search dropdowns
    st.markdown("**🚀 Quick Search:**")
    area_category = st.selectbox(
        "Category",
        options=[""] + list(POPULAR_AREAS.keys()),
        key="area_category",
        format_func=lambda x: x if x else "Choose category..."
    )
    
    if area_category:
        selected_area = st.selectbox(
            "Location",
            options=[""] + POPULAR_AREAS[area_category],
            key="selected_area_dropdown",
            format_func=lambda x: x if x else "Choose location..."
        )
        
        if selected_area and selected_area != st.session_state.get("selected_area", ""):
            st.session_state.address = selected_area
            st.session_state.search_query = selected_area
            st.session_state.selected_area = selected_area
            st.success(f"✅ Selected: {selected_area}")
            st.rerun()

st.markdown('</div>', unsafe_allow_html=True)
st.markdown("---")

# Main form
form = st.form(key="form_settings")
col1, col2, col3 = form.columns([3, 1, 1])

# Address field (read-only if using uploaded file)
if st.session_state.use_uploaded_file and st.session_state.uploaded_gdf is not None:
    address = col1.text_input(
        "Location address",
        value="Using uploaded file boundaries",
        disabled=True,
        help="Boundaries from uploaded file will be used"
    )
else:
    address = col1.text_input(
        "Location address",
        value=st.session_state.get("address", ""),
        key="address",
        help="This will be filled automatically when you use search above"
    )

radius = col2.slider(
    "Radius (meters)",
    100,
    1500,
    key="radius",
    help="Map coverage area"
)

# Enhanced style selection
selected_style = create_style_selector()

expander = form.expander("🎛️ Advanced Map Customization")
col1style, col2style, _, col3style = expander.columns([2, 2, 0.1, 1])

# Shape options
shape_options = ["circle", "rectangle"]
shape = col1style.radio(
    "🔲 Map Shape",
    options=shape_options,
    key="shape",
)

# Background options
bg_shape_options = ["rectangle", "circle", None]
bg_shape = col1style.radio(
    "⬜ Background Shape",
    options=bg_shape_options,
    key="bg_shape",
)
bg_color = col1style.color_picker(
    "🎨 Background Color",
    key="bg_color",
)
bg_buffer = col1style.slider(
    "📏 Background Size",
    min_value=0,
    max_value=50,
    help="How much the background extends beyond the figure.",
    key="bg_buffer",
)

col1style.markdown("---")
contour_color = col1style.color_picker(
    "🖊️ Map Border Color",
    key="contour_color",
)
contour_width = col1style.slider(
    "📐 Map Border Width",
    0,
    30,
    help="Thickness of border line surrounding the map.",
    key="contour_width",
)

# Title options
name_on = col2style.checkbox(
    "📝 Show Title",
    help="Display location name on the map",
    key="name_on",
)
custom_title = col2style.text_input(
    "✏️ Custom Title (optional)",
    max_chars=40,
    key="custom_title",
)
font_size = col2style.slider(
    "🔤 Title Size",
    min_value=8,
    max_value=60,
    key="font_size",
)
font_color = col2style.color_picker(
    "🎨 Title Color",
    key="font_color",
)
text_x = col2style.slider(
    "↔️ Title Horizontal Position",
    -100,
    100,
    key="text_x",
)
text_y = col2style.slider(
    "↕️ Title Vertical Position",
    -100,
    100,
    key="text_y",
)
text_rotation = col2style.slider(
    "🔄 Title Rotation",
    -90,
    90,
    key="text_rotation",
)

# Color customization
if selected_style != st.session_state.get("previous_style", "Peach"):
    st.session_state.update(get_colors_from_style(selected_style))
    st.session_state["previous_style"] = selected_style

draw_settings = copy.deepcopy(STYLES[selected_style])
col3style.markdown("**🎨 Custom Colors:**")
for lc_class in st.session_state.lc_classes:
    picked_color = col3style.color_picker(
        lc_class.replace('_', ' ').title(), 
        key=lc_class
    )
    if "_" in lc_class:
        lc_class_name, idx = lc_class.split("_")
        draw_settings[lc_class_name]["cmap"][int(idx)] = picked_color
    else:
        draw_settings[lc_class]["fc"] = picked_color

submit_button = form.form_submit_button(
    label="🗺️ Generate Beautiful Map", 
    type="primary",
    use_container_width=True
)

# Map generation
if submit_button:
    if st.session_state.use_uploaded_file and st.session_state.uploaded_gdf is not None:
        # Use uploaded file
        with st.spinner("🎨 Creating map from uploaded boundaries..."):
            try:
                # Create map using uploaded geometries
                config = {
                    "draw_settings": draw_settings,
                    "name_on": name_on,
                    "name": custom_title if custom_title else "Custom Boundaries",
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
                
                # Use the uploaded geodataframe directly
                fig = st_plot_all(_df=st.session_state.uploaded_gdf, **config)
                st.pyplot(fig, pad_inches=0, bbox_inches="tight", transparent=True, dpi=300)
                
                st.success("🎉 Map created successfully from uploaded boundaries!")
                
            except Exception as e:
                st.error(f"❌ Error creating map from uploaded file: {str(e)}")
                
    elif address:
        # Use address-based location
        with st.spinner("🎨 Creating your beautiful map... (this may take up to a minute)"):
            rectangular = shape != "circle"
            try:
                aoi = get_aoi(address=address, radius=radius, rectangular=rectangular)
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
                
                st.success("🎉 Your beautiful map is ready!")
                
                # Export options
                st.markdown("---")
                st.markdown("### 📥 Export Options")
                ex1, ex2 = st.columns(2)

                with ex1.expander("📊 Export Map Data (GeoJSON)"):
                    st.write(f"📍 {df.shape[0]} geographic features found")
                    st.download_button(
                        label="⬇️ Download GeoJSON",
                        data=gdf_to_bytesio_geojson(df),
                        file_name=f"prettymapp_{address[:15].replace(' ', '_')}.geojson",
                        mime="application/geo+json",
                    )

                config["address"] = address
                with ex2.expander("⚙️ Export Map Configuration"):
                    st.json(config)
                    
            except GeoCodingError as e:
                st.error(f"❌ Location Error: {str(e)}")
                st.error("💡 **Try these solutions:**")
                st.error("- Use the search suggestions above")
                st.error("- Try a more specific address")
                st.error("- Check spelling of the location")
                st.error("- Use popular locations from dropdowns")
    else:
        st.warning("⚠️ Please enter a location address, use search suggestions, or upload a file!")

# Enhanced footer
st.markdown("---")
st.markdown("### 💡 Pro Tips for Amazing Maps")

tips_col1, tips_col2, tips_col3 = st.columns(3)

with tips_col1:
    st.markdown("""
    **🔍 Smart Search:**
    - Type any location worldwide
    - Use landmarks, not just addresses
    - Try different languages
    - Search updates as you type
    """)

with tips_col2:
    st.markdown("""
    **🎨 Style & Design:**
    - Preview styles before selecting
    - Customize colors for uniqueness
    - Adjust radius for perfect scale
    - Try different shapes & borders
    """)

with tips_col3:
    st.markdown("""
    **📁 File Upload:**
    - Upload KML or zipped shapefiles
    - Create maps from custom boundaries
    - Perfect for specific areas
    - Export data for further use
    """)

st.markdown("---")
st.markdown("""
<div style='text-align: center; padding: 20px;'>
    <h4>🌟 Share Your Beautiful Maps!</h4>
    <p>Tag us with <a href="https://twitter.com/search?q=%23prettymaps" target="_blank">#prettymaps</a> on social media</p>
    <p>⭐ <a href="https://github.com/chrieke/prettymapp" target="_blank">Star us on GitHub</a> • 
    📖 <a href="https://github.com/chrieke/prettymapp" target="_blank">Documentation & More</a></p>
</div>
""", unsafe_allow_html=True)

# Update session state
st.session_state["previous_style"] = selected_style
