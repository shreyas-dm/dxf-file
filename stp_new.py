import streamlit as st
import tempfile
import os
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
from OCC.Core.StlAPI import StlAPI_Writer
from OCC.Core.IFSelect import IFSelect_RetDone
from stl import mesh
import plotly.graph_objects as go
import numpy as np

def read_step_file(step_file_path):
    """Reads a STEP file and returns the shape."""
    st.write("Reading STEP file...")
    step_reader = STEPControl_Reader()
    status = step_reader.ReadFile(step_file_path)
    if status == IFSelect_RetDone:
        st.write("STEP file read successfully.")
        step_reader.TransferRoots()
        shape = step_reader.OneShape()
        if shape.IsNull():
            st.error("No valid shape found in the STEP file.")
            return None
        else:
            st.write("Shape extracted from STEP file.")
            return shape
    else:
        st.error(f"Error reading STEP file. Status code: {status}")
        return None

def shape_to_mesh(shape):
    """Converts a shape to mesh data (vertices and faces)."""
    st.write("Starting meshing...")
    # Adjust the deflection parameter as needed
    mesh_gen = BRepMesh_IncrementalMesh(shape, 0.01)
    mesh_gen.Perform()
    if not mesh_gen.IsDone():
        st.error("Meshing failed.")
        return None, None
    st.write("Meshing completed.")

    # Write to a temporary STL file
    with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as tmp_stl:
        stl_writer = StlAPI_Writer()
        stl_writer.Write(shape, tmp_stl.name)
        stl_file = tmp_stl.name

    st.write(f"STL file written to {stl_file}")
    file_size = os.path.getsize(stl_file)
    st.write(f"STL file size: {file_size} bytes")
    if file_size == 0:
        st.error("STL file is empty.")
        return None, None

    # Use numpy-stl to read the STL file
    try:
        your_mesh = mesh.Mesh.from_file(stl_file)
        vertices = your_mesh.vectors.reshape(-1, 3)
        faces = np.arange(len(vertices)).reshape(-1, 3)
        st.write(f"Number of vertices: {len(vertices)}")
        st.write(f"Number of faces: {len(faces)}")
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
    mesh = go.Mesh3d(
        x=x, y=y, z=z,
        i=i, j=j, k=k,
        color='lightblue',
        opacity=0.5
    )
    layout = go.Layout(
        scene=dict(
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            zaxis=dict(visible=False)
        ),
        width=800,
        height=600
    )
    fig = go.Figure(data=[mesh], layout=layout)
    st.plotly_chart(fig)

def main():
    st.title("STEP File Viewer")
    uploaded_file = st.file_uploader("Upload a STEP file", type=["step", "stp"])
    if uploaded_file is not None:
        with tempfile.NamedTemporaryFile(suffix='.step', delete=False) as tmp_step:
            tmp_step.write(uploaded_file.getbuffer())
            tmp_step_path = tmp_step.name

        shape = read_step_file(tmp_step_path)
        if shape is not None:
            vertices, faces = shape_to_mesh(shape)
            if vertices is not None and faces is not None:
                display_mesh(vertices, faces)
            else:
                st.error("Failed to generate mesh data.")

if __name__ == "__main__":
    main()
