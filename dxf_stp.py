import streamlit as st
import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
import matplotlib.pyplot as plt
import io
import tempfile
import os
import base64
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
from OCC.Core.StlAPI import StlAPI_Writer
from OCC.Core.IFSelect import IFSelect_RetDone
from stl import mesh
import plotly.graph_objects as go
import numpy as np
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib_Add
from OCC.Core.IGESControl import IGESControl_Reader

# Functions for DXF processing
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

def display_dxf_image(img_str):
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

# Functions for STP Viewer
def read_step_file(step_file_path):
    """Reads a STEP file and returns the shape."""
    step_reader = STEPControl_Reader()
    status = step_reader.ReadFile(step_file_path)
    if status == IFSelect_RetDone:
        step_reader.TransferRoots()
        shape = step_reader.OneShape()
        if shape.IsNull():
            st.error("No valid shape found in the STEP file.")
            return None
        else:
            return shape
    else:
        st.error(f"Error reading STEP file. Status code: {status}")
        return None

def shape_to_mesh(shape):
    """Converts a shape to mesh data (vertices and faces)."""
    mesh_gen = BRepMesh_IncrementalMesh(shape, 0.01)
    mesh_gen.Perform()
    if not mesh_gen.IsDone():
        st.error("Meshing failed.")
        return None, None

    with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as tmp_stl:
        stl_writer = StlAPI_Writer()
        stl_writer.Write(shape, tmp_stl.name)
        stl_file = tmp_stl.name

    try:
        your_mesh = mesh.Mesh.from_file(stl_file)
        vertices = your_mesh.vectors.reshape(-1, 3)
        faces = np.arange(len(vertices)).reshape(-1, 3)
        return vertices, faces
    except Exception as e:
        st.error(f"Error reading STL file: {e}")
        return None, None

def display_mesh(vertices, faces):
    """Displays the mesh using Plotly."""
    if vertices is None or len(vertices) == 0:
        st.error("No vertices to display.")
        return
    x, y, z = vertices.T
    i, j, k = faces.T

    mesh_plot = go.Mesh3d(
        x=x, y=y, z=z,
        i=i, j=j, k=k,
        color='cyan',
        opacity=1.0,
        lighting=dict(
            ambient=0.2,
            diffuse=1.0,
            specular=0.5,
            roughness=0.5,
            fresnel=0.1
        ),
        lightposition=dict(
            x=100,
            y=200,
            z=0
        ),
        flatshading=False
    )

    layout = go.Layout(
        scene=dict(
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            zaxis=dict(visible=False),
            aspectmode='data',
            camera=dict(
                eye=dict(x=1.5, y=1.5, z=1.5)
            ),
        ),
        width=800,
        height=600,
        margin=dict(r=0, l=0, b=0, t=0),
        paper_bgcolor="LightSteelBlue",
    )

    fig = go.Figure(data=[mesh_plot], layout=layout)
    st.plotly_chart(fig)

def process_dxf(uploaded_file):
    try:
        file_contents = io.BytesIO(uploaded_file.getvalue())
        doc = load_dxf(file_contents)
        fig = render_dxf(doc)
        
        img_str = fig_to_base64(fig)
        
        # Display DXF Image
        display_dxf_image(img_str)
        
        # Display dimensions using st.metric and st.columns
        width, height = get_dimensions(doc)
        if width is not None and height is not None:
            st.markdown("### Dimensions")
            col1, col2 = st.columns(2)
            col1.metric("Width", f"{width:.2f} units")
            col2.metric("Height", f"{height:.2f} units")
        else:
            st.write("Unable to determine dimensions.")
    
    except Exception as e:
        st.error(f"Error processing the DXF file: {str(e)}")

def read_iges_file(iges_file_path):
    """Reads an IGES file and returns the shape."""
    iges_reader = IGESControl_Reader()
    status = iges_reader.ReadFile(iges_file_path)
    if status == IFSelect_RetDone:
        iges_reader.TransferRoots()
        shape = iges_reader.OneShape()
        if shape.IsNull():
            st.error("No valid shape found in the IGES file.")
            return None
        else:
            return shape
    else:
        st.error(f"Error reading IGES file. Status code: {status}")
        return None

def get_stp_dimensions(shape):
    """Calculates the dimensions (width, depth, height) of the STP file."""
    bbox = Bnd_Box()
    brepbndlib_Add(shape, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    width = xmax - xmin
    depth = ymax - ymin
    height = zmax - zmin
    return width, depth, height

def process_stp(uploaded_file):
    try:
        with tempfile.NamedTemporaryFile(suffix='.step', delete=False) as tmp_step:
            tmp_step.write(uploaded_file.getbuffer())
            tmp_step_path = tmp_step.name

        shape = read_step_file(tmp_step_path)
        if shape is not None:
            vertices, faces = shape_to_mesh(shape)
            if vertices is not None and faces is not None:
                display_mesh(vertices, faces)

                # Get dimensions and display them after rendering
                width, depth, height = get_stp_dimensions(shape)

                # Display dimensions using st.metric and st.columns
                st.markdown("### Dimensions")
                col1, col2, col3 = st.columns(3)
                col1.metric("Width (X)", f"{width:.2f} units")
                col2.metric("Depth (Y)", f"{depth:.2f} units")
                col3.metric("Height (Z)", f"{height:.2f} units")
            else:
                st.error("Failed to generate mesh data.")
        else:
            st.error("Failed to read the STEP file.")
    except Exception as e:
        st.error(f"Error processing the STEP file: {str(e)}")


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
    .viewer-container {
        margin-top: 20px;
        padding: 10px;
    }
    </style>
    """, unsafe_allow_html=True
    )


    # Main title
    st.markdown('<div class="title">Hyperscripts File Viewer</div>', unsafe_allow_html=True)
    
    # Sidebar for file uploader
    st.sidebar.header("Upload a DXF or STP/STEP file")
    uploaded_file = st.sidebar.file_uploader("Choose a DXF or STP/STEP file", type=["dxf", "stp", "step"])
    
    if uploaded_file is not None:
        file_extension = os.path.splitext(uploaded_file.name)[1].lower()
        if file_extension == '.dxf':
            process_dxf(uploaded_file)
        elif file_extension in ['.stp', '.step']:
            process_stp(uploaded_file)
        else:
            st.error("Unsupported file type.")

if __name__ == "__main__":
    main()