from pathlib import Path
import streamlit.components.v1 as components
device_storage=components.declare_component('ayo_saved_login',path=str(Path(__file__).parent/'login_component'))
