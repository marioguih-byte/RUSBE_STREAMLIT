import streamlit as st
import folium
from streamlit_folium import st_folium
from unidades import ESTACOES

st.set_page_config(page_title='RUSBÉ', layout='wide')

st.title('⚡ RUSBÉ - Dashboard Meteorológico')

camada = st.sidebar.selectbox('Estilo do mapa', ['Escuro','Satélite','OpenStreetMap'])

if camada == 'Satélite':
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
elif camada == 'OpenStreetMap':
    tiles='OpenStreetMap'
else:
    tiles='CartoDB dark_matter'

m = folium.Map(location=[-15,-55], zoom_start=4, tiles=tiles)

for e in ESTACOES:
    folium.Marker(
        [e['lat'],e['lon']],
        popup=e['nome']
    ).add_to(m)

st_folium(m,width=1100,height=700)
