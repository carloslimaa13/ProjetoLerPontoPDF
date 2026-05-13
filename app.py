import streamlit as st
import tempfile
import os
import pandas as pd
import plotly.express as px  # O novo motor gráfico para o visual Premium
from processing import PontoProcessor

st.set_page_config(page_title="Dashboard RH - Ponto", page_icon="⏱️", layout="wide")

st.title("📊 Dashboard de Espelho de Ponto")
st.markdown("Faça o upload dos relatórios do Secullum para consolidação automática de métricas.")

arquivos_pdf = st.file_uploader("Selecione os arquivos PDF", type=["pdf"], accept_multiple_files=True)

if arquivos_pdf:
    with st.spinner("Processando dados e montando linha do tempo..."):
        caminhos_temporarios = []
        try:
            for arquivo in arquivos_pdf:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(arquivo.read())
                    caminhos_temporarios.append(tmp_file.name)
            
            processador = PontoProcessor(caminhos_temporarios)
            df_resultado = processador.execute_pipeline()
            df_diario_polars = processador.extract_daily_faults()
        finally:
            for caminho in caminhos_temporarios:
                if os.path.exists(caminho): os.remove(caminho)

    if not df_resultado.is_empty():
        df_pandas = df_resultado.to_pandas()

        def converte_hhmm_para_decimal(hhmm_str):
            if not hhmm_str or ":" not in hhmm_str: return 0.0
            horas, minutos = map(int, hhmm_str.split(':'))
            return horas + (minutos / 60.0)

        df_pandas['Faltas_Num'] = df_pandas['Faltas (HH:MM)'].apply(converte_hhmm_para_decimal)
        df_pandas['Extras_Num'] = df_pandas['Extras (HH:MM)'].apply(converte_hhmm_para_decimal)

        # ==========================================
        # SEÇÃO DE EVOLUÇÃO DIÁRIA (Gráfico Curvo com Sombra)
        # ==========================================
        if not df_diario_polars.is_empty():
            df_diario = df_diario_polars.to_pandas()
            df_diario['Data'] = pd.to_datetime(df_diario['Data'], format='%d/%m/%Y')
            
            # Filtro para ignorar Finais de Semana
            df_diario = df_diario[df_diario['Data'].dt.dayofweek < 5]
            
            # Agrupa tudo por dia
            df_diario_agrupado = df_diario.groupby('Data')[['Minutos_Falta', 'Minutos_Extra']].sum().reset_index()
            
            ultimos_7_dias = df_diario_agrupado.sort_values('Data', ascending=False).head(7)
            ultimos_7_dias = ultimos_7_dias.sort_values('Data', ascending=True)
            
            ultimos_7_dias['Faltas'] = ultimos_7_dias['Minutos_Falta'] / 60.0
            ultimos_7_dias['Extras'] = ultimos_7_dias['Minutos_Extra'] / 60.0
            ultimos_7_dias['Data'] = ultimos_7_dias['Data'].dt.strftime('%d/%m')
            
            st.subheader("📅 Evolução Diária da Empresa (Últimos 7 Dias Úteis)")
            
            # --- MÁGICA DO PLOTLY (Sombra e Curvas) ---
            fig = px.area(
                ultimos_7_dias,
                x='Data',
                y=['Faltas', 'Extras'],
                color_discrete_sequence=["#9719BE", "#0054FF"], # Roxo e Azul
                line_shape='spline' # Essa configuração transforma linhas retas em curvas suaves!
            )
            
            # Ajustes finos de transparência e interface
            fig.update_layout(
                xaxis_title="",
                yaxis_title="Horas",
                legend_title_text="",
                margin=dict(l=0, r=0, t=10, b=0),
                plot_bgcolor="rgba(0,0,0,0)", # Fundo transparente para combinar com o Streamlit
                paper_bgcolor="rgba(0,0,0,0)",
                hovermode="x unified" # Mostra os dois valores quando você passa o mouse por cima
            )
            # Trava o eixo X como texto para respeitar a nossa ordenação
            fig.update_xaxes(type='category', showgrid=False)
            fig.update_yaxes(showgrid=True, gridcolor='rgba(128, 128, 128, 0.2)')

            # Renderiza o gráfico na tela
            st.plotly_chart(fig, use_container_width=True)
            
        st.markdown("---")

        # ==========================================
        # SEÇÃO 1: FALTAS E ATRASOS
        # ==========================================
        st.header("📌 Análise de Faltas e Atrasos")
        df_faltas_sorted = df_pandas.sort_values(by='Faltas_Num', ascending=False)
        colab_f, tempo_f, depto_f = df_faltas_sorted.iloc[0][['Colaborador', 'Faltas (HH:MM)', 'Departamento']]
        st.error(f"⚠️ **Maior volume de faltas/atrasos geral:** {colab_f} ({depto_f}) com **{tempo_f}**")

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("🏢 Faltas por Departamento")
            df_depto_f = df_pandas.groupby('Departamento')['Faltas_Num'].sum().sort_values(ascending=False)
            st.bar_chart(df_depto_f, color="#9719BE")
        with c2:
            st.subheader("📈 Top 5 Colaboradores (Faltas)")
            df_top5_f = df_faltas_sorted.head(5).copy()
            df_top5_f['Label'] = df_top5_f['Departamento'] + " | " + df_top5_f['Colaborador']
            st.bar_chart(df_top5_f.set_index('Label')['Faltas_Num'], color="#9719BE")

        st.markdown("---")

        # ==========================================
        # SEÇÃO 2: HORAS EXTRAS
        # ==========================================
        st.header("🚀 Análise de Horas Extras")
        df_extras_sorted = df_pandas.sort_values(by='Extras_Num', ascending=False)
        colab_e, tempo_e, depto_e = df_extras_sorted.iloc[0][['Colaborador', 'Extras (HH:MM)', 'Departamento']]
        st.success(f"⭐ **Maior volume de horas extras:** {colab_e} ({depto_e}) com **{tempo_e}**")

        c3, c4 = st.columns(2)
        with c3:
            st.subheader("🏢 Extras por Departamento")
            df_depto_e = df_pandas.groupby('Departamento')['Extras_Num'].sum().sort_values(ascending=False)
            st.bar_chart(df_depto_e, color="#0054FF")
        with c4:
            st.subheader("📈 Top 5 Colaboradores (Extras)")
            df_top5_e = df_extras_sorted.head(5).copy()
            df_top5_e['Label'] = df_top5_e['Departamento'] + " | " + df_top5_e['Colaborador']
            st.bar_chart(df_top5_e.set_index('Label')['Extras_Num'], color="#0054FF")

        # ==========================================
        # SEÇÃO 3: TABELA FINAL
        # ==========================================
        st.markdown("---")
        st.subheader("📋 Tabela Consolidada Geral")
        st.dataframe(
            df_pandas.drop(columns=['Faltas_Num', 'Extras_Num']),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.error("Não foi possível extrair dados. Verifique o formato do PDF.")