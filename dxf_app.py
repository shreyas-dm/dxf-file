import streamlit as st
import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
import matplotlib.pyplot as plt
import io
import tempfile
import os
import base64

def load_dxf(file):
    if isinstance(file, io.BytesIO):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.dxf') as tmp_file:
            tmp_file.write(file.getvalue())
            tmp_file_path = tmp_file.name
        try:
            doc = ezdxf.readfile(tmp_file_path)
        finally:
            os.unlink(tmp_file_path)
    else:
        doc = ezdxf.readfile(file)
    return doc

def render_dxf(doc):
    msp = doc.modelspace()
    fig = plt.figure(figsize=(20, 16), dpi=300)  # High resolution figure
    ax = fig.add_axes([0, 0, 1, 1])
    ctx = RenderContext(doc)
    out = MatplotlibBackend(ax)
    Frontend(ctx, out).draw_layout(msp)
    
    # Ensure white background and black lines
    ax.set_facecolor('white')
    for child in ax.get_children():
        if isinstance(child, plt.Line2D):
            child.set_color('black')
            child.set_linewidth(0.5)  # Thin lines for better quality
    
    # Fit all elements in view
    ax.autoscale()
    ax.margins(0.1)
    ax.set_axis_off()
    
    return fig

def fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=300, bbox_inches='tight', pad_inches=0)
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode('utf-8')

def get_dimensions(doc):
    msp = doc.modelspace()
    x_coords, y_coords = [], []
    
    for entity in msp:
        if entity.dxftype() == 'LINE':
            x_coords.extend([entity.dxf.start.x, entity.dxf.end.x])
            y_coords.extend([entity.dxf.start.y, entity.dxf.end.y])
        elif entity.dxftype() == 'CIRCLE':
            center = entity.dxf.center
            radius = entity.dxf.radius
            x_coords.extend([center.x - radius, center.x + radius])
            y_coords.extend([center.y - radius, center.y + radius])
        elif entity.dxftype() == 'ARC':
            center = entity.dxf.center
            radius = entity.dxf.radius
            x_coords.extend([center.x - radius, center.x + radius])
            y_coords.extend([center.y - radius, center.y + radius])
        elif entity.dxftype() == 'POLYLINE' or entity.dxftype() == 'LWPOLYLINE':
            for vertex in entity:
                x_coords.append(vertex.dxf.x)
                y_coords.append(vertex.dxf.y)
        elif entity.dxftype() == 'SPLINE':
            for point in entity.control_points:
                x_coords.append(point[0])
                y_coords.append(point[1])
    
    if x_coords and y_coords:
        width = max(x_coords) - min(x_coords)
        height = max(y_coords) - min(y_coords)
        return width, height
    else:
        return None, None

def main():
    # Apply custom styles using markdown
    st.markdown(
        """
        <style>
        .title {
            font-size: 48px;
            font-weight: bold;
            text-align: center;
            margin-top: -50px;
            color: #4B9CD3;
        }
        .sidebar .sidebar-content {
            background-color: #f0f2f6;
        }
        .dimensions-container {
            border: 2px solid #4B9CD3;
            border-radius: 10px;
            background-color: #F9F9F9;
            padding: 20px;
            text-align: center;
            margin-top: 20px;
        }
        .dimensions-text {
            font-size: 24px;
            color: #333;
            font-weight: bold;
        }
        .viewer-container {
            margin-top: 20px;
            padding: 10px;
        }
        </style>
        """, unsafe_allow_html=True
    )

    # Main title
    st.markdown('<div class="title">Hyperscripts DXF File Viewer</div>', unsafe_allow_html=True)
    
    # Sidebar for file uploader
    st.sidebar.header("Upload a DXF file")
    uploaded_file = st.sidebar.file_uploader("Choose a DXF file", type=["dxf"])
    
    if uploaded_file is not None:
        try:
            file_contents = io.BytesIO(uploaded_file.getvalue())
            doc = load_dxf(file_contents)
            fig = render_dxf(doc)
            
            img_str = fig_to_base64(fig)
            
            # HTML and JavaScript for image viewer with simple zoom
            html = f'''
            <div class="viewer-container">
                <div style="width:100%; height:600px; overflow:hidden; position:relative;">
                    <img id="dxfImage" src="data:image/png;base64,{img_str}" style="width:100%; height:100%; object-fit:contain;">
                </div>
            </div>
            <script>
                var img = document.getElementById('dxfImage');
                var scale = 1;
                var translateX = 0;
                var translateY = 0;
                
                function updateTransform() {{
                    img.style.transform = `translate(${{translateX}}px, ${{translateY}}px) scale(${{scale}})`;
                }}
                
                function zoom(factor, centerX, centerY) {{
                    var prevScale = scale;
                    scale *= factor;
                    scale = Math.min(Math.max(0.1, scale), 10);  // Limit zoom level
                    
                    translateX -= centerX * (scale - prevScale);
                    translateY -= centerY * (scale - prevScale);
                    
                    updateTransform();
                }}
                
                img.onwheel = function(event) {{
                    if (event.ctrlKey) {{
                        event.preventDefault();
                        var rect = img.getBoundingClientRect();
                        var mouseX = event.clientX - rect.left;
                        var mouseY = event.clientY - rect.top;
                        
                        var wheel = event.deltaY < 0 ? 1.1 : 0.9;
                        zoom(wheel, mouseX, mouseY);
                    }}
                }};
                
                img.onmousedown = function(event) {{
                    var lastX = event.clientX;
                    var lastY = event.clientY;
                    
                    function mousemove(event) {{
                        var deltaX = event.clientX - lastX;
                        var deltaY = event.clientY - lastY;
                        translateX += deltaX;
                        translateY += deltaY;
                        lastX = event.clientX;
                        lastY = event.clientY;
                        updateTransform();
                    }}
                    
                    function mouseup() {{
                        document.removeEventListener('mousemove', mousemove);
                        document.removeEventListener('mouseup', mouseup);
                    }}
                    
                    document.addEventListener('mousemove', mousemove);
                    document.addEventListener('mouseup', mouseup);
                }};
            </script>
            '''
            st.components.v1.html(html, height=620)
            
            # Display dimensions in a styled container
            width, height = get_dimensions(doc)
            if width is not None and height is not None:
                st.markdown(
                    f'''
                    <div class="dimensions-container">
                        <p class="dimensions-text">Dimensions</p>
                        <p class="dimensions-text">Width: {width:.2f} units</p>
                        <p class="dimensions-text">Height: {height:.2f} units</p>
                    </div>
                    ''', unsafe_allow_html=True
                )
            else:
                st.markdown('<div class="dimensions-container">Unable to determine dimensions.</div>', unsafe_allow_html=True)
        
        except Exception as e:
            st.error(f"Error processing the file: {str(e)}")

if __name__ == "__main__":
    main()
