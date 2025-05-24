import copy
import json
import base64
import io
from io import BytesIO
import streamlit as st
from streamlit_image_select import image_select
from matplotlib import pyplot as plt
from matplotlib.pyplot import figure
from shapely.geometry import Polygon
import geopandas as gpd

from utils import (
    st_get_osm_geometries,
    st_plot_all,
    get_colors_from_style,
    gdf_to_bytesio_geojson,
    slugify,
    plt_to_svg,
    svg_to_html
)
from prettymapp.geo import GeoCodingError, get_aoi
from prettymapp.settings import STYLES

st.set_page_config(
    page_title="prettymapp", 
    page_icon="🖼️", 
    initial_sidebar_state="collapsed"
)
st.markdown("# 🗺️ Prettymapp - Advanced Map Creator")

# Load examples
with open("./streamlit-prettymapp/examples.json", "r", encoding="utf8") as f:
    EXAMPLES = json.load(f)

# Replace the existing session state initialization with:

# Initialize session state with required keys
if "previous_example_index" not in st.session_state:
    st.session_state["previous_example_index"] = 0
if "previous_style" not in st.session_state:
    st.session_state["previous_style"] = "Peach"
if "lc_classes" not in st.session_state:
    lc_class_colors = get_colors_from_style("Peach")
    st.session_state.lc_classes = list(lc_class_colors.keys())
    st.session_state.update(lc_class_colors)

# Then load example data if not already loaded
if "address" not in st.session_state:
    st.session_state.update(EXAMPLES["Macau"])

# Modify the example selection code to:
index_selected = image_select(
    "",
    images=example_image_fp,
    captions=list(EXAMPLES.keys())[:4],
    index=st.session_state.get("previous_example_index", 0),
    return_value="index",
)

# Update the comparison to handle missing key
if index_selected != st.session_state.get("previous_example_index", 0):
    name_selected = list(EXAMPLES.keys())[index_selected]
    st.session_state.update(EXAMPLES[name_selected].copy())
    st.session_state["previous_example_index"] = index_selected

# Main form
form = st.form(key="main_form")
col1, col2, col3 = form.columns([3, 1, 1])

# Location input
address = col1.text_input(
    "Location address",
    key="address",
    placeholder="Enter address or coordinates"
)

# Radius selection
radius = col2.slider(
    "Radius (meters)",
    100,
    1500,
    key="radius",
    help="Area coverage radius in meters"
)

# Style selection with container
with col3.container(border=True):
    style = st.selectbox(
        "Color Theme",
        options=list(STYLES.keys()),
        key="style",
        help="Choose from predefined color schemes"
    )

# Advanced settings expander
with form.expander("⚙️ Advanced Customization", expanded=False):
    adv_col1, adv_col2, adv_col3 = st.columns([2, 2, 1])

    # Map shape settings
    with adv_col1.container(border=True):
        st.markdown("**Map Shape**")
        shape = st.radio(
            "Base Shape",
            options=["circle", "rectangle"],
            key="shape",
            horizontal=True
        )
        contour_width = st.slider(
            "Border Width",
            0,
            30,
            key="contour_width",
            help="Thickness of map border"
        )
        contour_color = st.color_picker(
            "Border Color",
            key="contour_color"
        )

    # Background settings
    with adv_col2.container(border=True):
        st.markdown("**Background**")
        bg_shape = st.radio(
            "Background Shape",
            options=["rectangle", "circle", "none"],
            key="bg_shape",
            horizontal=True
        )
        bg_color = st.color_picker(
            "Background Color",
            key="bg_color"
        )
        bg_buffer = st.slider(
            "Background Size",
            0,
            50,
            key="bg_buffer",
            help="Extension beyond map boundaries"
        )

    # Title customization
    with adv_col3.container(border=True):
        st.markdown("**Title Settings**")
        name_on = st.checkbox(
            "Show Title",
            key="name_on",
            value=True
        )
        if name_on:
            custom_title = st.text_input(
                "Custom Title",
                key="custom_title",
                max_chars=30
            )
            font_size = st.slider(
                "Font Size",
                8,
                40,
                key="font_size",
                value=16
            )
            font_color = st.color_picker(
                "Font Color",
                key="font_color"
            )
            text_rotation = st.slider(
                "Rotation",
                -90,
                90,
                key="text_rotation"
            )

# Color customization
with form.expander("🎨 Advanced Color Customization", expanded=False):
    if style != st.session_state["previous_style"]:
        st.session_state.update(get_colors_from_style(style))
    
    draw_settings = copy.deepcopy(STYLES[style])
    cols = st.columns(3)
    color_picker_index = 0
    
    for lc_class in st.session_state.lc_classes:
        with cols[color_picker_index % 3]:
            picked_color = st.color_picker(
                lc_class.replace("_", " ").title(),
                key=lc_class
            )
            if "_" in lc_class:
                class_part, idx = lc_class.split("_")
                draw_settings[class_part]["cmap"][int(idx)] = picked_color
            else:
                draw_settings[lc_class]["fc"] = picked_color
        color_picker_index += 1

form.form_submit_button(label="Generate Map", type="primary")

# Main map generation
if st.session_state.get("address"):
    try:
        with st.spinner("Creating your masterpiece... (may take up to a minute)"):
            # Get area of interest
            rectangular = shape != "circle"
            aoi = get_aoi(address=address, radius=radius, rectangular=rectangular)
            
            # Get OSM geometries
            df = st_get_osm_geometries(aoi=aoi)
            
            # Configuration
            config = {
                "aoi_bounds": aoi.bounds,
                "draw_settings": draw_settings,
                "name_on": name_on,
                "name": custom_title if name_on and custom_title else "",
                "font_size": font_size if name_on else 0,
                "font_color": font_color if name_on else "#000000",
                "text_rotation": text_rotation if name_on else 0,
                "shape": shape,
                "contour_width": contour_width,
                "contour_color": contour_color,
                "bg_shape": bg_shape if bg_shape != "none" else None,
                "bg_buffer": bg_buffer,
                "bg_color": bg_color,
            }

            # Generate plot
            fig = st_plot_all(_df=df, **config)
            
            # Display plot
            st.pyplot(fig, pad_inches=0, bbox_inches="tight", transparent=True, dpi=300)
            
            # Download section
            st.markdown("---")
            with st.container(border=True):
                st.markdown("### 📥 Export Options")
                
                # Image download
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    with st.expander("🖼️ Download Image"):
                        img_format = st.selectbox(
                            "Image Format",
                            ["png", "svg", "jpg"],
                            index=0
                        )
                        img_buffer = BytesIO()
                        fig.savefig(img_buffer, format=img_format, 
                                  bbox_inches="tight", pad_inches=0, dpi=300)
                        st.download_button(
                            label=f"Download .{img_format}",
                            data=img_buffer.getvalue(),
                            file_name=f"{slugify(address)}.{img_format}",
                            mime=f"image/{img_format}"
                        )
                
                # Data export
                with col_d2:
                    with st.expander("📁 Export Data"):
                        st.download_button(
                            label="Download GeoJSON",
                            data=gdf_to_bytesio_geojson(df),
                            file_name=f"{slugify(address)}.geojson",
                            mime="application/geo+json"
                        )
                        st.download_button(
                            label="Download Config",
                            data=json.dumps(config, indent=2),
                            file_name=f"{slugify(address)}_config.json",
                            mime="application/json"
                        )

    except GeoCodingError as e:
        st.error(f"Location Error: {str(e)}")
        st.stop()
    except Exception as e:
        st.error(f"Map Creation Error: {str(e)}")
        st.stop()

# Footer
st.markdown("---")
st.markdown("### 💡 Tips & Information")
st.markdown("""
- Share your creations with **#prettymaps**
- Found an issue? [Report it on GitHub](https://github.com/chrieke/prettymapp)
- Adjust advanced settings carefully for best results
- Larger areas may take longer to process
""")

st.session_state["previous_style"] = style
