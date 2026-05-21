import streamlit as st
import tempfile
import os
import pandas as pd
from datetime import date
import altair as alt
from processing import PontoProcessor

# 1. Configuração da página
st.set_page_config(page_title="Dashboard RH - Horas Consolidadas", page_icon="⏱️", layout="wide")

# ==========================================
# BARRA LATERAL (SIDEBAR) - INSTRUÇÕES DE TEMA
# ==========================================
with st.sidebar:
    st.header("⚙️ Preferências")
    st.markdown("Este painel possui suporte nativo para **Modo Claro** e **Modo Escuro**.")
    st.info("💡 **Como alterar o tema:**\n\n1. Clique nos **3 pontinhos (⋮)** no canto superior direito da página.\n2. Vá em **Settings**.\n3. Em **Theme**, escolha *Light* ou *Dark*.")
    st.markdown("---")
    st.markdown("Desenvolvido para análise inteligente de jornada.")

# ==========================================
# CABEÇALHO PRINCIPAL
# ==========================================
st.title("⏱️ Validador Interativo de Ponto")
st.markdown("Filtre o período desejado no calendário. A tabela e os cartões recalculam instantaneamente as somas e dividem as equipes por **Abas (Tabs)**.")

arquivos_pdf = st.file_uploader("Selecione os arquivos PDF", type=["pdf"], accept_multiple_files=True)

if arquivos_pdf:
    with st.spinner("Lendo PDFs e mapeando os registros..."):
        caminhos_temporarios = []
        try:
            for arquivo in arquivos_pdf:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(arquivo.read())
                    caminhos_temporarios.append(tmp_file.name)
            
            processador = PontoProcessor(caminhos_temporarios)
            df_resultado = processador.execute_pipeline()
            
        finally:
            for caminho in caminhos_temporarios:
                if os.path.exists(caminho): 
                    os.remove(caminho)

    # --- RENDERIZAÇÃO NA TELA ---
    if not df_resultado.is_empty():
        df_pandas = df_resultado.to_pandas()

        # Funções para realizar as somas no Pandas
        def hhmm_to_min(time_str):
            if not isinstance(time_str, str) or ":" not in time_str: return 0
            h, m = map(int, time_str.split(':'))
            return h * 60 + m

        def min_to_hhmm(minutes):
            h = int(minutes // 60)
            m = int(minutes % 60)
            return f"{h:02d}:{m:02d}"

        # 1. Tratamento da coluna de Data para habilitar o Calendário
        df_pandas['Data_Obj'] = pd.to_datetime(df_pandas['Data'], format='%d/%m/%Y', errors='coerce')
        
        # Pega as datas corretas usando date.today() como proteção
        if not df_pandas['Data_Obj'].dropna().empty:
            min_date = df_pandas['Data_Obj'].min().date()
            max_date = df_pandas['Data_Obj'].max().date()
        else:
            min_date = date.today()
            max_date = date.today()

        st.markdown("---")
        
        col_cal1, col_cal2 = st.columns([1, 2])
        with col_cal1:
            st.subheader("📅 Período de Análise")
            periodo_selecionado = st.date_input(
                "Selecione o intervalo:",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
                format="DD/MM/YYYY"
            )

        # Só recalcula se as duas datas (início e fim) estiverem selecionadas
        if len(periodo_selecionado) == 2:
            dt_inicio, dt_fim = periodo_selecionado
            
            # Filtra os dados de acordo com o calendário
            mask = (df_pandas['Data_Obj'].dt.date >= dt_inicio) & (df_pandas['Data_Obj'].dt.date <= dt_fim)
            df_filtrado = df_pandas[mask].copy()

            # Converte as horas filtradas em minutos para poder somar
            df_filtrado['horas_min'] = df_filtrado['Horas Trabalhadas'].apply(hhmm_to_min)
            df_filtrado['faltas_min'] = df_filtrado['Faltas'].apply(hhmm_to_min)
            df_filtrado['extras_min'] = df_filtrado['Extras'].apply(hhmm_to_min)

            # --- PREPARAÇÃO DA TABELA CONSOLIDADA GERAL ---
            df_consolidado = df_filtrado.groupby(['Colaborador', 'Departamento']).agg(
                horas_sum=('horas_min', 'sum'),
                faltas_sum=('faltas_min', 'sum'),
                extras_sum=('extras_min', 'sum')
            ).reset_index()

            # Converte de volta para a máscara de relógio HH:MM para a Tabela
            df_consolidado['Horas Trabalhadas'] = df_consolidado['horas_sum'].apply(min_to_hhmm)
            df_consolidado['Faltas'] = df_consolidado['faltas_sum'].apply(min_to_hhmm)
            df_consolidado['Extras'] = df_consolidado['extras_sum'].apply(min_to_hhmm)

            df_display = df_consolidado[['Colaborador', 'Departamento', 'Horas Trabalhadas', 'Faltas', 'Extras']].sort_values('Colaborador')

            with col_cal2:
                st.write("") 
                st.success(f"✅ Filtro aplicado! Os resultados foram atualizados para o período selecionado.")

            # ==========================================
            # CRIAÇÃO DINÂMICA DE ABAS (TABS)
            # ==========================================
            lista_departamentos = sorted(df_display['Departamento'].unique().tolist())
            
            nomes_abas = ["📊 Visão Geral"] + [f"📂 {depto}" for depto in lista_departamentos]
            abas = st.tabs(nomes_abas)

            # --- ABA 0: VISÃO GERAL ---
            with abas[0]:
                st.markdown("### 📊 Resumo Global do Período")
                
                # Cálculos globais para os cards principais
                total_colaboradores = df_filtrado['Colaborador'].nunique()
                soma_global_horas = df_filtrado['horas_min'].sum()
                soma_global_faltas = df_filtrado['faltas_min'].sum()
                soma_global_extras = df_filtrado['extras_min'].sum()

                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns(4)
                    with c1: st.metric(label="👥 Colaboradores Únicos", value=total_colaboradores)
                    with c2: st.metric(label="⏱️ Total de Horas Trabalhadas", value=min_to_hhmm(soma_global_horas))
                    with c3: st.metric(label="⚠️ Total de Faltas", value=min_to_hhmm(soma_global_faltas))
                    with c4: st.metric(label="⭐ Total de Extras", value=min_to_hhmm(soma_global_extras))

                # ==========================================
                # GRÁFICO DE LINHAS (EVOLUÇÃO DIÁRIA EM TABS)
                # ==========================================
                st.markdown("---")
                st.markdown("### 📈 Evolução Diária da Empresa")
                
                # Prepara os dados agrupando por dia
                df_linha_diaria = df_filtrado.groupby('Data_Obj').agg(
                    horas=('horas_min', 'sum'),
                    faltas=('faltas_min', 'sum'),
                    extras=('extras_min', 'sum')
                ).reset_index()

                if not df_linha_diaria.empty:
                    # Converte para formato decimal para os gráficos individuais
                    df_linha_diaria['Horas Trabalhadas'] = df_linha_diaria['horas'] / 60.0
                    df_linha_diaria['Faltas'] = df_linha_diaria['faltas'] / 60.0
                    df_linha_diaria['Extras'] = df_linha_diaria['extras'] / 60.0

                    # Criação das sub-abas para os gráficos de linha
                    tab_ln_horas, tab_ln_faltas, tab_ln_extras = st.tabs(["⏱️ Linha - Horas", "⚠️ Linha - Faltas", "⭐ Linha - Extras"])

                    # 1. Evolução de Horas Trabalhadas (Verde)
                    with tab_ln_horas:
                        base_ln_horas = alt.Chart(df_linha_diaria).encode(
                            x=alt.X('Data_Obj:T', title='Data', axis=alt.Axis(format='%d/%m')),
                            y=alt.Y('Horas Trabalhadas:Q', title='Volume de Horas', stack=None),
                            tooltip=[
                                alt.Tooltip('Data_Obj:T', title='Data', format='%d/%m/%Y'),
                                alt.Tooltip('Horas Trabalhadas:Q', title='Horas Trabalhadas (Decimais)', format='.2f')
                            ]
                        )
                        area_ln_horas = base_ln_horas.mark_area(opacity=0.25, line=False, color='#2ECC71')
                        line_ln_horas = base_ln_horas.mark_line(point=True, strokeWidth=3, color='#2ECC71')
                        st.altair_chart(alt.layer(area_ln_horas, line_ln_horas).properties(height=320), use_container_width=True)

                    # 2. Evolução de Faltas (Vermelho)
                    with tab_ln_faltas:
                        base_ln_faltas = alt.Chart(df_linha_diaria).encode(
                            x=alt.X('Data_Obj:T', title='Data', axis=alt.Axis(format='%d/%m')),
                            y=alt.Y('Faltas:Q', title='Volume de Faltas', stack=None),
                            tooltip=[
                                alt.Tooltip('Data_Obj:T', title='Data', format='%d/%m/%Y'),
                                alt.Tooltip('Faltas:Q', title='Horas de Falta (Decimais)', format='.2f')
                            ]
                        )
                        area_ln_faltas = base_ln_faltas.mark_area(opacity=0.25, line=False, color='#E74C3C')
                        line_ln_faltas = base_ln_faltas.mark_line(point=True, strokeWidth=3, color='#E74C3C')
                        st.altair_chart(alt.layer(area_ln_faltas, line_ln_faltas).properties(height=320), use_container_width=True)

                    # 3. Evolução de Extras (Amarelo)
                    with tab_ln_extras:
                        base_ln_extras = alt.Chart(df_linha_diaria).encode(
                            x=alt.X('Data_Obj:T', title='Data', axis=alt.Axis(format='%d/%m')),
                            y=alt.Y('Extras:Q', title='Volume de Extras', stack=None),
                            tooltip=[
                                alt.Tooltip('Data_Obj:T', title='Data', format='%d/%m/%Y'),
                                alt.Tooltip('Extras:Q', title='Horas Extras (Decimais)', format='.2f')
                            ]
                        )
                        area_ln_extras = base_ln_extras.mark_area(opacity=0.25, line=False, color='#F1C40F')
                        line_ln_extras = base_ln_extras.mark_line(point=True, strokeWidth=3, color='#F1C40F')
                        st.altair_chart(alt.layer(area_ln_extras, line_ln_extras).properties(height=320), use_container_width=True)
                else:
                    st.info("Não há dados diários suficientes no período selecionado para traçar a evolução.")

                # ==========================================
                # GRÁFICOS TOP 5 (SUB-TABS)
                # ==========================================
                st.markdown("---")
                st.markdown("### 🏆 Top 5 Consultores")
                
                tab_graf_horas, tab_graf_faltas, tab_graf_extras = st.tabs(["⏱️ Mais Horas", "⚠️ Mais Faltas", "⭐ Mais Extras"])
                
                # 1. Gráfico de Horas
                with tab_graf_horas:
                    df_top_horas = df_consolidado.nlargest(5, 'horas_sum').copy()
                    if not df_top_horas.empty and df_top_horas['horas_sum'].sum() > 0:
                        df_top_horas['Horas Formato Decimal'] = df_top_horas['horas_sum'] / 60.0
                        grafico_horas = alt.Chart(df_top_horas).mark_bar(color='#2ECC71').encode(
                            x=alt.X('Colaborador:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
                            y=alt.Y('Horas Formato Decimal:Q', title='Horas Trabalhadas'),
                            tooltip=['Colaborador', 'Horas Trabalhadas']
                        ).properties(height=320)
                        st.altair_chart(grafico_horas, use_container_width=True)
                    else:
                        st.info("Não há registros de horas para este período.")

                # 2. Gráfico de Faltas
                with tab_graf_faltas:
                    df_top_faltas = df_consolidado.nlargest(5, 'faltas_sum').copy()
                    if not df_top_faltas.empty and df_top_faltas['faltas_sum'].sum() > 0:
                        df_top_faltas['Faltas Formato Decimal'] = df_top_faltas['faltas_sum'] / 60.0
                        grafico_faltas = alt.Chart(df_top_faltas).mark_bar(color='#E74C3C').encode(
                            x=alt.X('Colaborador:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
                            y=alt.Y('Faltas Formato Decimal:Q', title='Total de Faltas (Horas)'),
                            tooltip=['Colaborador', 'Faltas']
                        ).properties(height=320)
                        st.altair_chart(grafico_faltas, use_container_width=True)
                    else:
                        st.success("Nenhuma falta registrada neste período! 🎉")

                # 3. Gráfico de Extras
                with tab_graf_extras:
                    df_top_extras = df_consolidado.nlargest(5, 'extras_sum').copy()
                    if not df_top_extras.empty and df_top_extras['extras_sum'].sum() > 0:
                        df_top_extras['Extras Formato Decimal'] = df_top_extras['extras_sum'] / 60.0
                        grafico_extras = alt.Chart(df_top_extras).mark_bar(color='#F1C40F').encode(
                            x=alt.X('Colaborador:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
                            y=alt.Y('Extras Formato Decimal:Q', title='Horas Extras'),
                            tooltip=['Colaborador', 'Extras']
                        ).properties(height=320)
                        st.altair_chart(grafico_extras, use_container_width=True)
                    else:
                        st.info("Nenhuma hora extra registrada neste período.")

                # ==========================================
                # TABELA GLOBAL
                # ==========================================
                st.markdown("---")
                st.subheader("📋 Espelho Consolidado (Todos os Setores)")
                st.dataframe(df_display, use_container_width=True, hide_index=True)

                csv_export_global = df_display.to_csv(index=False, sep=";").encode('utf-8-sig')
                st.download_button(
                    label="📥 Baixar Visão Geral (CSV)",
                    data=csv_export_global,
                    file_name=f"Ponto_Global_{dt_inicio.strftime('%d-%m')}_a_{dt_fim.strftime('%d-%m')}.csv",
                    mime="text/csv",
                    type="primary",
                    key="btn_global"
                )

            # --- ABAS DE DEPARTAMENTOS ESPECÍFICOS ---
            for i, depto in enumerate(lista_departamentos):
                with abas[i + 1]:
                    st.markdown(f"### 📊 Resumo: {depto}")
                    
                    df_filtrado_depto = df_filtrado[df_filtrado['Departamento'] == depto]
                    
                    total_colab_depto = df_filtrado_depto['Colaborador'].nunique()
                    soma_horas_depto = df_filtrado_depto['horas_min'].sum()
                    soma_faltas_depto = df_filtrado_depto['faltas_min'].sum()
                    soma_extras_depto = df_filtrado_depto['extras_min'].sum()

                    with st.container(border=True):
                        c1, c2, c3, c4 = st.columns(4)
                        with c1: st.metric(label="👥 Colaboradores", value=total_colab_depto)
                        with c2: st.metric(label="⏱️ Horas Trabalhadas", value=min_to_hhmm(soma_horas_depto))
                        with c3: st.metric(label="⚠️ Faltas", value=min_to_hhmm(soma_faltas_depto))
                        with c4: st.metric(label="⭐ Extras", value=min_to_hhmm(soma_extras_depto))

                    st.markdown("---")
                    st.subheader(f"📋 Setor: {depto}")
                    
                    df_depto_show = df_display[df_display['Departamento'] == depto].drop(columns=['Departamento'])
                    st.dataframe(df_depto_show, use_container_width=True, hide_index=True)

                    csv_export_depto = df_depto_show.to_csv(index=False, sep=";").encode('utf-8-sig')
                    st.download_button(
                        label=f"📥 Baixar Tabela - {depto} (CSV)",
                        data=csv_export_depto,
                        file_name=f"Ponto_{depto.replace(' ', '_')}_{dt_inicio.strftime('%d-%m')}_a_{dt_fim.strftime('%d-%m')}.csv",
                        mime="text/csv",
                        type="secondary",
                        key=f"btn_{depto}"
                    )
            
    else:
        st.error("Não foi possível extrair dados válidos. Verifique se os arquivos seguem o formato padrão.")
