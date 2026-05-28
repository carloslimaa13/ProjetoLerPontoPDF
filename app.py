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
        
        # Garante que a coluna Status exista, mesmo que vazia
        if 'Status' not in df_pandas.columns:
            df_pandas['Status'] = ""
            
        # Pega as datas corretas usando date.today() como proteção
        if not df_pandas['Data_Obj'].dropna().empty:
            min_date = df_pandas['Data_Obj'].min().date()
            max_date = df_pandas['Data_Obj'].max().date()
        else:
            min_date = date.today()
            max_date = date.today()

        st.markdown("---")
        
        # ==========================================
        # FILTROS SUPERIORES
        # ==========================================
        col_filtro1, col_filtro2, col_filtro3 = st.columns([1.5, 2, 1.5])
        
        with col_filtro1:
            st.subheader("📅 Período de Análise")
            periodo_selecionado = st.date_input(
                "Selecione o intervalo:",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
                format="DD/MM/YYYY"
            )

        with col_filtro2:
            st.subheader("👤 Consultor")
            lista_consultores = sorted(df_pandas['Colaborador'].dropna().unique().tolist())
            consultores_selecionados = st.multiselect(
                "Selecione (deixe vazio para exibir todos):",
                options=lista_consultores,
                default=[]
            )

        # Só recalcula se as duas datas (início e fim) estiverem selecionadas
        if len(periodo_selecionado) == 2:
            dt_inicio, dt_fim = periodo_selecionado
            
            # Filtra os dados de acordo com o calendário
            mask_data = (df_pandas['Data_Obj'].dt.date >= dt_inicio) & (df_pandas['Data_Obj'].dt.date <= dt_fim)
            df_filtrado = df_pandas[mask_data].copy()

            # Filtra os dados de acordo com os consultores selecionados
            if consultores_selecionados:
                df_filtrado = df_filtrado[df_filtrado['Colaborador'].isin(consultores_selecionados)]

            # Proteção caso o filtro retorne vazio
            if df_filtrado.empty:
                st.warning("⚠️ Nenhum dado encontrado para os filtros selecionados.")
            else:
                with col_filtro3:
                    st.write("")
                    st.write("") # Espaçamento para alinhar com os inputs
                    st.success(f"✅ Exibindo resultados de **{df_filtrado['Colaborador'].nunique()} consultor(es)**.")

                # ==========================================
                # CÁLCULOS MATEMÁTICOS E LÓGICOS
                # ==========================================
                df_filtrado['normais_min'] = df_filtrado['Normais'].apply(hhmm_to_min)
                df_filtrado['faltas_min'] = df_filtrado['Faltas'].apply(hhmm_to_min)
                df_filtrado['extras_min'] = df_filtrado['Extras'].apply(hhmm_to_min)
                df_filtrado['trabalhadas_min'] = df_filtrado['normais_min'] + df_filtrado['extras_min']

                # Lógica 1: Folgas de Seg a Sex e Férias
                def conta_dias_ausencia(row):
                    status = str(row['Status']).upper()
                    if pd.isna(row['Data_Obj']): return 0
                    dia_semana = row['Data_Obj'].weekday() # 0=Seg, 4=Sex, 5=Sáb, 6=Dom
                    
                    if "FERIAS" in status or "FÉRIAS" in status:
                        return 1
                    if "FOLGA" in status and dia_semana < 5:
                        return 1
                    return 0

                # Lógica 2: Faltas Não Justificadas
                def conta_falta_injustificada(row):
                    status = str(row['Status']).upper()
                    faltas_min = row.get('faltas_min', 0)
                    
                    justificativas_aprovadas = [
                        "ABN DIR", "ATESD M", "ATESD", "CASAR", "FERIAS", "FÉRIAS", 
                        "FOLGA", "INT JUD", "LMT", "OBITO M", "ÓBITO M", "VIS. CL", "VIS CL", "FERIADO"
                    ]
                    
                    for just in justificativas_aprovadas:
                        if just in status:
                            return 0 # Justificado
                    
                    tem_texto = any(c.isalpha() for c in status)
                    if tem_texto:
                        return 1
                        
                    if faltas_min >= 480:
                        return 1
                        
                    return 0

                # Lógica 3: Faltas Totais (Soma de tudo)
                def conta_falta_total(row):
                    status = str(row['Status']).upper()
                    faltas_min = row.get('faltas_min', 0)
                    
                    # Ignoramos descansos oficiais para não gerar "falsas faltas" no fim de semana
                    if "FOLGA" in status or "FERIADO" in status or "FERIAS" in status or "FÉRIAS" in status:
                        return 0
                        
                    # Se tiver qualquer outro texto (Atestado, Licença, etc)
                    tem_texto = any(c.isalpha() for c in status)
                    if tem_texto:
                        return 1
                        
                    # Se a linha estiver em branco e com 8h de falta
                    if faltas_min >= 480:
                        return 1
                        
                    return 0

                df_filtrado['dias_inativos_val'] = df_filtrado.apply(conta_dias_ausencia, axis=1)
                df_filtrado['faltas_injustificadas_val'] = df_filtrado.apply(conta_falta_injustificada, axis=1)
                df_filtrado['faltas_totais_val'] = df_filtrado.apply(conta_falta_total, axis=1)

                # --- PREPARAÇÃO DA TABELA CONSOLIDADA GERAL ---
                df_consolidado = df_filtrado.groupby(['Colaborador', 'Departamento']).agg(
                    normais_sum=('normais_min', 'sum'),
                    faltas_sum=('faltas_min', 'sum'),
                    extras_sum=('extras_min', 'sum'),
                    trabalhadas_sum=('trabalhadas_min', 'sum'),
                    dias_inativos_sum=('dias_inativos_val', 'sum'),
                    faltas_injust_sum=('faltas_injustificadas_val', 'sum'),
                    faltas_totais_sum=('faltas_totais_val', 'sum') 
                ).reset_index()

                # Converte de volta para a máscara de relógio HH:MM para a Tabela
                df_consolidado['Normais'] = df_consolidado['normais_sum'].apply(min_to_hhmm)
                df_consolidado['Faltas (Horas)'] = df_consolidado['faltas_sum'].apply(min_to_hhmm)
                df_consolidado['Extras'] = df_consolidado['extras_sum'].apply(min_to_hhmm)
                df_consolidado['Horas Trabalhadas'] = df_consolidado['trabalhadas_sum'].apply(min_to_hhmm)
                
                df_consolidado['Folgas (Semana) / Férias'] = df_consolidado['dias_inativos_sum']
                df_consolidado['Faltas Não Justificadas'] = df_consolidado['faltas_injust_sum']
                df_consolidado['Faltas Totais'] = df_consolidado['faltas_totais_sum']

                # Define a ordem de exibição das colunas na tabela final
                df_display = df_consolidado[['Colaborador', 'Departamento', 'Normais', 'Faltas (Horas)', 'Extras', 'Horas Trabalhadas', 'Folgas (Semana) / Férias', 'Faltas Não Justificadas', 'Faltas Totais']].sort_values('Colaborador')

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
                    soma_global_normais = df_filtrado['normais_min'].sum()
                    soma_global_faltas = df_filtrado['faltas_min'].sum()
                    soma_global_extras = df_filtrado['extras_min'].sum()
                    soma_global_trabalhadas = df_filtrado['trabalhadas_min'].sum()
                    soma_global_inativos = df_filtrado['dias_inativos_val'].sum()
                    soma_global_injustificadas = df_filtrado['faltas_injustificadas_val'].sum()
                    soma_global_totais = df_filtrado['faltas_totais_val'].sum()

                    with st.container(border=True):
                        c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)
                        with c1: st.metric(label="👥 Colaboradores", value=total_colaboradores)
                        with c2: st.metric(label="⏱️ Normais", value=min_to_hhmm(soma_global_normais))
                        with c3: st.metric(label="⚠️ Faltas (h)", value=min_to_hhmm(soma_global_faltas))
                        with c4: st.metric(label="⭐ Extras", value=min_to_hhmm(soma_global_extras))
                        with c5: st.metric(label="💼 Trabalhadas", value=min_to_hhmm(soma_global_trabalhadas))
                        with c6: st.metric(label="🏖️ Folgas/Férias", value=soma_global_inativos)
                        with c7: st.metric(label="❌ Não Justif.", value=soma_global_injustificadas)
                        with c8: st.metric(label="📋 Faltas Totais", value=soma_global_totais)

                    # ==========================================
                    # GRÁFICO DE LINHAS GERAL
                    # ==========================================
                    st.markdown("---")
                    st.markdown("### 📈 Evolução Diária da Empresa")
                    
                    df_linha_diaria = df_filtrado.groupby('Data_Obj').agg(
                        trabalhadas=('trabalhadas_min', 'sum'),
                        faltas=('faltas_min', 'sum'),
                        extras=('extras_min', 'sum'),
                        inativos=('dias_inativos_val', 'sum'),
                        injustificadas=('faltas_injustificadas_val', 'sum'),
                        totais=('faltas_totais_val', 'sum')
                    ).reset_index()

                    if not df_linha_diaria.empty:
                        df_linha_diaria['Horas Trabalhadas'] = df_linha_diaria['trabalhadas'] / 60.0
                        df_linha_diaria['Faltas'] = df_linha_diaria['faltas'] / 60.0
                        df_linha_diaria['Extras'] = df_linha_diaria['extras'] / 60.0
                        df_linha_diaria['Folgas/Férias'] = df_linha_diaria['inativos']
                        df_linha_diaria['Faltas Não Justificadas'] = df_linha_diaria['injustificadas']
                        df_linha_diaria['Faltas Totais'] = df_linha_diaria['totais']

                        tab_ln_trabalhadas, tab_ln_faltas, tab_ln_extras, tab_ln_inat, tab_ln_injust, tab_ln_tot = st.tabs([
                            "⏱️ Trabalhadas", "⚠️ Faltas (h)", "⭐ Extras", "🏖️ Folgas/Férias", "❌ Não Justificadas", "📋 Faltas Totais"
                        ])

                        with tab_ln_trabalhadas:
                            base_ln_trabalhadas = alt.Chart(df_linha_diaria).encode(
                                x=alt.X('Data_Obj:T', title='Data', axis=alt.Axis(format='%d/%m')),
                                y=alt.Y('Horas Trabalhadas:Q', title='Volume de Horas Trabalhadas', stack=None),
                                tooltip=[alt.Tooltip('Data_Obj:T', title='Data', format='%d/%m/%Y'), alt.Tooltip('Horas Trabalhadas:Q', title='Horas Trabalhadas', format='.2f')]
                            )
                            st.altair_chart(alt.layer(base_ln_trabalhadas.mark_area(opacity=0.25, line=False, color='#2ECC71'), base_ln_trabalhadas.mark_line(point=True, strokeWidth=3, color='#2ECC71')).properties(height=320), use_container_width=True)

                        with tab_ln_faltas:
                            base_ln_faltas = alt.Chart(df_linha_diaria).encode(
                                x=alt.X('Data_Obj:T', title='Data', axis=alt.Axis(format='%d/%m')),
                                y=alt.Y('Faltas:Q', title='Volume de Faltas', stack=None),
                                tooltip=[alt.Tooltip('Data_Obj:T', title='Data', format='%d/%m/%Y'), alt.Tooltip('Faltas:Q', title='Faltas', format='.2f')]
                            )
                            st.altair_chart(alt.layer(base_ln_faltas.mark_area(opacity=0.25, line=False, color='#E74C3C'), base_ln_faltas.mark_line(point=True, strokeWidth=3, color='#E74C3C')).properties(height=320), use_container_width=True)

                        with tab_ln_extras:
                            base_ln_extras = alt.Chart(df_linha_diaria).encode(
                                x=alt.X('Data_Obj:T', title='Data', axis=alt.Axis(format='%d/%m')),
                                y=alt.Y('Extras:Q', title='Volume de Extras', stack=None),
                                tooltip=[alt.Tooltip('Data_Obj:T', title='Data', format='%d/%m/%Y'), alt.Tooltip('Extras:Q', title='Extras', format='.2f')]
                            )
                            st.altair_chart(alt.layer(base_ln_extras.mark_area(opacity=0.25, line=False, color='#F1C40F'), base_ln_extras.mark_line(point=True, strokeWidth=3, color='#F1C40F')).properties(height=320), use_container_width=True)
                            
                        with tab_ln_inat:
                            base_ln_inat = alt.Chart(df_linha_diaria).encode(
                                x=alt.X('Data_Obj:T', title='Data', axis=alt.Axis(format='%d/%m')),
                                y=alt.Y('Folgas/Férias:Q', title='Qtd de Folgas/Férias (Dias)', stack=None),
                                tooltip=[alt.Tooltip('Data_Obj:T', title='Data', format='%d/%m/%Y'), alt.Tooltip('Folgas/Férias:Q', title='Dias', format='.0f')]
                            )
                            st.altair_chart(alt.layer(base_ln_inat.mark_area(opacity=0.25, line=False, color='#3498DB'), base_ln_inat.mark_line(point=True, strokeWidth=3, color='#3498DB')).properties(height=320), use_container_width=True)

                        with tab_ln_injust:
                            base_ln_injust = alt.Chart(df_linha_diaria).encode(
                                x=alt.X('Data_Obj:T', title='Data', axis=alt.Axis(format='%d/%m')),
                                y=alt.Y('Faltas Não Justificadas:Q', title='Qtd Não Justificadas (Dias)', stack=None),
                                tooltip=[alt.Tooltip('Data_Obj:T', title='Data', format='%d/%m/%Y'), alt.Tooltip('Faltas Não Justificadas:Q', title='Dias', format='.0f')]
                            )
                            st.altair_chart(alt.layer(base_ln_injust.mark_area(opacity=0.25, line=False, color='#E67E22'), base_ln_injust.mark_line(point=True, strokeWidth=3, color='#E67E22')).properties(height=320), use_container_width=True)

                        with tab_ln_tot:
                            base_ln_tot = alt.Chart(df_linha_diaria).encode(
                                x=alt.X('Data_Obj:T', title='Data', axis=alt.Axis(format='%d/%m')),
                                y=alt.Y('Faltas Totais:Q', title='Qtd Faltas Totais (Dias)', stack=None),
                                tooltip=[alt.Tooltip('Data_Obj:T', title='Data', format='%d/%m/%Y'), alt.Tooltip('Faltas Totais:Q', title='Dias', format='.0f')]
                            )
                            st.altair_chart(alt.layer(base_ln_tot.mark_area(opacity=0.25, line=False, color='#34495E'), base_ln_tot.mark_line(point=True, strokeWidth=3, color='#34495E')).properties(height=320), use_container_width=True)

                    else:
                        st.info("Não há dados diários suficientes no período selecionado para traçar a evolução.")

                    # ==========================================
                    # GRÁFICOS BARRAS TOP 5 GERAL
                    # ==========================================
                    st.markdown("---")
                    st.markdown("### 🏆 Top 5 Consultores")
                    
                    tab_graf_trabalhadas, tab_graf_faltas, tab_graf_extras, tab_graf_inat, tab_graf_injust, tab_graf_tot = st.tabs([
                        "💼 Mais Trabalhadas", "⚠️ Mais Faltas (h)", "⭐ Mais Extras", "🏖️ Mais Folgas/Férias", "❌ Mais Não Justif.", "📋 Mais Faltas Totais"
                    ])
                    
                    with tab_graf_trabalhadas:
                        df_top_trabalhadas = df_consolidado.nlargest(5, 'trabalhadas_sum').copy()
                        if not df_top_trabalhadas.empty and df_top_trabalhadas['trabalhadas_sum'].sum() > 0:
                            df_top_trabalhadas['Trabalhadas Formato Decimal'] = df_top_trabalhadas['trabalhadas_sum'] / 60.0
                            grafico_trabalhadas = alt.Chart(df_top_trabalhadas).mark_bar(color='#2ECC71').encode(
                                x=alt.X('Colaborador:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
                                y=alt.Y('Trabalhadas Formato Decimal:Q', title='Horas Trabalhadas'),
                                tooltip=[alt.Tooltip('Colaborador', title='Colaborador'), alt.Tooltip('Horas Trabalhadas', title='Horas Trabalhadas')]
                            ).properties(height=320)
                            st.altair_chart(grafico_trabalhadas, use_container_width=True)
                        else:
                            st.info("Não há registros para este período.")

                    with tab_graf_faltas:
                        df_top_faltas = df_consolidado.nlargest(5, 'faltas_sum').copy()
                        if not df_top_faltas.empty and df_top_faltas['faltas_sum'].sum() > 0:
                            df_top_faltas['Faltas Formato Decimal'] = df_top_faltas['faltas_sum'] / 60.0
                            grafico_faltas = alt.Chart(df_top_faltas).mark_bar(color='#E74C3C').encode(
                                x=alt.X('Colaborador:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
                                y=alt.Y('Faltas Formato Decimal:Q', title='Total de Faltas (Horas)'),
                                tooltip=[alt.Tooltip('Colaborador', title='Colaborador'), alt.Tooltip('Faltas (Horas)', title='Faltas (Horas)')]
                            ).properties(height=320)
                            st.altair_chart(grafico_faltas, use_container_width=True)
                        else:
                            st.success("Nenhuma falta (em horas) registrada neste período! 🎉")

                    with tab_graf_extras:
                        df_top_extras = df_consolidado.nlargest(5, 'extras_sum').copy()
                        if not df_top_extras.empty and df_top_extras['extras_sum'].sum() > 0:
                            df_top_extras['Extras Formato Decimal'] = df_top_extras['extras_sum'] / 60.0
                            grafico_extras = alt.Chart(df_top_extras).mark_bar(color='#F1C40F').encode(
                                x=alt.X('Colaborador:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
                                y=alt.Y('Extras Formato Decimal:Q', title='Horas Extras'),
                                tooltip=[alt.Tooltip('Colaborador', title='Colaborador'), alt.Tooltip('Extras', title='Extras')]
                            ).properties(height=320)
                            st.altair_chart(grafico_extras, use_container_width=True)
                        else:
                            st.info("Nenhuma hora extra registrada neste período.")
                            
                    with tab_graf_inat:
                        df_top_inat = df_consolidado.nlargest(5, 'dias_inativos_sum').copy()
                        if not df_top_inat.empty and df_top_inat['dias_inativos_sum'].sum() > 0:
                            grafico_inat = alt.Chart(df_top_inat).mark_bar(color='#3498DB').encode(
                                x=alt.X('Colaborador:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
                                y=alt.Y('dias_inativos_sum:Q', title='Qtd de Folgas/Férias (Dias)'),
                                tooltip=[alt.Tooltip('Colaborador', title='Colaborador'), alt.Tooltip('dias_inativos_sum', title='Dias')]
                            ).properties(height=320)
                            st.altair_chart(grafico_inat, use_container_width=True)
                        else:
                            st.info("Não há registros de Folgas/Férias para este período.")
                            
                    with tab_graf_injust:
                        df_top_injust = df_consolidado.nlargest(5, 'faltas_injust_sum').copy()
                        if not df_top_injust.empty and df_top_injust['faltas_injust_sum'].sum() > 0:
                            grafico_injust = alt.Chart(df_top_injust).mark_bar(color='#E67E22').encode(
                                x=alt.X('Colaborador:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
                                y=alt.Y('faltas_injust_sum:Q', title='Qtd Não Justificadas (Dias)'),
                                tooltip=[alt.Tooltip('Colaborador', title='Colaborador'), alt.Tooltip('faltas_injust_sum', title='Dias')]
                            ).properties(height=320)
                            st.altair_chart(grafico_injust, use_container_width=True)
                        else:
                            st.success("Nenhuma falta não justificada neste período! 🎉")
                            
                    with tab_graf_tot:
                        df_top_tot = df_consolidado.nlargest(5, 'faltas_totais_sum').copy()
                        if not df_top_tot.empty and df_top_tot['faltas_totais_sum'].sum() > 0:
                            grafico_tot = alt.Chart(df_top_tot).mark_bar(color='#34495E').encode(
                                x=alt.X('Colaborador:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
                                y=alt.Y('faltas_totais_sum:Q', title='Qtd Faltas Totais (Dias)'),
                                tooltip=[alt.Tooltip('Colaborador', title='Colaborador'), alt.Tooltip('faltas_totais_sum', title='Dias')]
                            ).properties(height=320)
                            st.altair_chart(grafico_tot, use_container_width=True)
                        else:
                            st.success("Nenhuma falta total neste período! 🎉")

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
                        soma_normais_depto = df_filtrado_depto['normais_min'].sum()
                        soma_faltas_depto = df_filtrado_depto['faltas_min'].sum()
                        soma_extras_depto = df_filtrado_depto['extras_min'].sum()
                        soma_total_depto = df_filtrado_depto['trabalhadas_min'].sum()
                        soma_inativos_depto = df_filtrado_depto['dias_inativos_val'].sum()
                        soma_injustificadas_depto = df_filtrado_depto['faltas_injustificadas_val'].sum()
                        soma_totais_depto = df_filtrado_depto['faltas_totais_val'].sum()

                        with st.container(border=True):
                            c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)
                            with c1: st.metric(label="👥 Colab.", value=total_colab_depto)
                            with c2: st.metric(label="⏱️ Normais", value=min_to_hhmm(soma_normais_depto))
                            with c3: st.metric(label="⚠️ Faltas (h)", value=min_to_hhmm(soma_faltas_depto))
                            with c4: st.metric(label="⭐ Extras", value=min_to_hhmm(soma_extras_depto))
                            with c5: st.metric(label="💼 Trabalhadas", value=min_to_hhmm(soma_total_depto))
                            with c6: st.metric(label="🏖️ Folgas/Férias", value=soma_inativos_depto)
                            with c7: st.metric(label="❌ Não Justif.", value=soma_injustificadas_depto)
                            with c8: st.metric(label="📋 Totais", value=soma_totais_depto)

                        # ==========================================
                        # GRÁFICO DE LINHAS SETORIAL
                        # ==========================================
                        st.markdown("---")
                        st.markdown(f"### 📈 Evolução Diária - {depto}")
                        
                        df_linha_diaria_depto = df_filtrado_depto.groupby('Data_Obj').agg(
                            trabalhadas=('trabalhadas_min', 'sum'),
                            faltas=('faltas_min', 'sum'),
                            extras=('extras_min', 'sum'),
                            inativos=('dias_inativos_val', 'sum'),
                            injustificadas=('faltas_injustificadas_val', 'sum'),
                            totais=('faltas_totais_val', 'sum')
                        ).reset_index()

                        if not df_linha_diaria_depto.empty:
                            df_linha_diaria_depto['Horas Trabalhadas'] = df_linha_diaria_depto['trabalhadas'] / 60.0
                            df_linha_diaria_depto['Faltas'] = df_linha_diaria_depto['faltas'] / 60.0
                            df_linha_diaria_depto['Extras'] = df_linha_diaria_depto['extras'] / 60.0
                            df_linha_diaria_depto['Folgas/Férias'] = df_linha_diaria_depto['inativos']
                            df_linha_diaria_depto['Faltas Não Justificadas'] = df_linha_diaria_depto['injustificadas']
                            df_linha_diaria_depto['Faltas Totais'] = df_linha_diaria_depto['totais']

                            tab_ln_trab_d, tab_ln_faltas_d, tab_ln_extras_d, tab_ln_inat_d, tab_ln_injust_d, tab_ln_tot_d = st.tabs([
                                "⏱️ Trabalhadas", "⚠️ Faltas (h)", "⭐ Extras", "🏖️ Folgas/Férias", "❌ Não Justificadas", "📋 Faltas Totais"
                            ])

                            with tab_ln_trab_d:
                                base_ln_trab_d = alt.Chart(df_linha_diaria_depto).encode(
                                    x=alt.X('Data_Obj:T', title='Data', axis=alt.Axis(format='%d/%m')),
                                    y=alt.Y('Horas Trabalhadas:Q', title='Volume de Horas Trabalhadas', stack=None),
                                    tooltip=[alt.Tooltip('Data_Obj:T', title='Data', format='%d/%m/%Y'), alt.Tooltip('Horas Trabalhadas:Q', title='Horas Trabalhadas', format='.2f')]
                                )
                                st.altair_chart(alt.layer(base_ln_trab_d.mark_area(opacity=0.25, line=False, color='#2ECC71'), base_ln_trab_d.mark_line(point=True, strokeWidth=3, color='#2ECC71')).properties(height=320), use_container_width=True)

                            with tab_ln_faltas_d:
                                base_ln_faltas_d = alt.Chart(df_linha_diaria_depto).encode(
                                    x=alt.X('Data_Obj:T', title='Data', axis=alt.Axis(format='%d/%m')),
                                    y=alt.Y('Faltas:Q', title='Volume de Faltas', stack=None),
                                    tooltip=[alt.Tooltip('Data_Obj:T', title='Data', format='%d/%m/%Y'), alt.Tooltip('Faltas:Q', title='Faltas', format='.2f')]
                                )
                                st.altair_chart(alt.layer(base_ln_faltas_d.mark_area(opacity=0.25, line=False, color='#E74C3C'), base_ln_faltas_d.mark_line(point=True, strokeWidth=3, color='#E74C3C')).properties(height=320), use_container_width=True)

                            with tab_ln_extras_d:
                                base_ln_extras_d = alt.Chart(df_linha_diaria_depto).encode(
                                    x=alt.X('Data_Obj:T', title='Data', axis=alt.Axis(format='%d/%m')),
                                    y=alt.Y('Extras:Q', title='Volume de Extras', stack=None),
                                    tooltip=[alt.Tooltip('Data_Obj:T', title='Data', format='%d/%m/%Y'), alt.Tooltip('Extras:Q', title='Extras', format='.2f')]
                                )
                                st.altair_chart(alt.layer(base_ln_extras_d.mark_area(opacity=0.25, line=False, color='#F1C40F'), base_ln_extras_d.mark_line(point=True, strokeWidth=3, color='#F1C40F')).properties(height=320), use_container_width=True)
                                
                            with tab_ln_inat_d:
                                base_ln_inat_d = alt.Chart(df_linha_diaria_depto).encode(
                                    x=alt.X('Data_Obj:T', title='Data', axis=alt.Axis(format='%d/%m')),
                                    y=alt.Y('Folgas/Férias:Q', title='Qtd de Folgas/Férias (Dias)', stack=None),
                                    tooltip=[alt.Tooltip('Data_Obj:T', title='Data', format='%d/%m/%Y'), alt.Tooltip('Folgas/Férias:Q', title='Dias', format='.0f')]
                                )
                                st.altair_chart(alt.layer(base_ln_inat_d.mark_area(opacity=0.25, line=False, color='#3498DB'), base_ln_inat_d.mark_line(point=True, strokeWidth=3, color='#3498DB')).properties(height=320), use_container_width=True)

                            with tab_ln_injust_d:
                                base_ln_injust_d = alt.Chart(df_linha_diaria_depto).encode(
                                    x=alt.X('Data_Obj:T', title='Data', axis=alt.Axis(format='%d/%m')),
                                    y=alt.Y('Faltas Não Justificadas:Q', title='Qtd Não Justificadas (Dias)', stack=None),
                                    tooltip=[alt.Tooltip('Data_Obj:T', title='Data', format='%d/%m/%Y'), alt.Tooltip('Faltas Não Justificadas:Q', title='Dias', format='.0f')]
                                )
                                st.altair_chart(alt.layer(base_ln_injust_d.mark_area(opacity=0.25, line=False, color='#E67E22'), base_ln_injust_d.mark_line(point=True, strokeWidth=3, color='#E67E22')).properties(height=320), use_container_width=True)

                            with tab_ln_tot_d:
                                base_ln_tot_d = alt.Chart(df_linha_diaria_depto).encode(
                                    x=alt.X('Data_Obj:T', title='Data', axis=alt.Axis(format='%d/%m')),
                                    y=alt.Y('Faltas Totais:Q', title='Qtd Faltas Totais (Dias)', stack=None),
                                    tooltip=[alt.Tooltip('Data_Obj:T', title='Data', format='%d/%m/%Y'), alt.Tooltip('Faltas Totais:Q', title='Dias', format='.0f')]
                                )
                                st.altair_chart(alt.layer(base_ln_tot_d.mark_area(opacity=0.25, line=False, color='#34495E'), base_ln_tot_d.mark_line(point=True, strokeWidth=3, color='#34495E')).properties(height=320), use_container_width=True)

                        else:
                            st.info("Não há dados diários suficientes no período selecionado para traçar a evolução.")

                        # ==========================================
                        # GRÁFICOS BARRAS TOP 5 SETORIAL
                        # ==========================================
                        st.markdown("---")
                        st.markdown(f"### 🏆 Top 5 Consultores - {depto}")
                        
                        df_consolidado_depto = df_consolidado[df_consolidado['Departamento'] == depto]
                        
                        tab_bar_trab_d, tab_bar_faltas_d, tab_bar_extras_d, tab_bar_inat_d, tab_bar_injust_d, tab_bar_tot_d = st.tabs([
                            "💼 Mais Trabalhadas", "⚠️ Mais Faltas (h)", "⭐ Mais Extras", "🏖️ Mais Folgas/Férias", "❌ Mais Não Justif.", "📋 Mais Faltas Totais"
                        ])
                        
                        with tab_bar_trab_d:
                            df_top_trab_d = df_consolidado_depto.nlargest(5, 'trabalhadas_sum').copy()
                            if not df_top_trab_d.empty and df_top_trab_d['trabalhadas_sum'].sum() > 0:
                                df_top_trab_d['Trabalhadas Formato Decimal'] = df_top_trab_d['trabalhadas_sum'] / 60.0
                                graf_trab_d = alt.Chart(df_top_trab_d).mark_bar(color='#2ECC71').encode(
                                    x=alt.X('Colaborador:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
                                    y=alt.Y('Trabalhadas Formato Decimal:Q', title='Horas Trabalhadas'),
                                    tooltip=[alt.Tooltip('Colaborador', title='Colaborador'), alt.Tooltip('Horas Trabalhadas', title='Horas Trabalhadas')]
                                ).properties(height=320)
                                st.altair_chart(graf_trab_d, use_container_width=True)
                            else:
                                st.info("Não há registros para este período.")

                        with tab_bar_faltas_d:
                            df_top_faltas_d = df_consolidado_depto.nlargest(5, 'faltas_sum').copy()
                            if not df_top_faltas_d.empty and df_top_faltas_d['faltas_sum'].sum() > 0:
                                df_top_faltas_d['Faltas Formato Decimal'] = df_top_faltas_d['faltas_sum'] / 60.0
                                graf_faltas_d = alt.Chart(df_top_faltas_d).mark_bar(color='#E74C3C').encode(
                                    x=alt.X('Colaborador:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
                                    y=alt.Y('Faltas Formato Decimal:Q', title='Total de Faltas (Horas)'),
                                    tooltip=[alt.Tooltip('Colaborador', title='Colaborador'), alt.Tooltip('Faltas (Horas)', title='Faltas (Horas)')]
                                ).properties(height=320)
                                st.altair_chart(graf_faltas_d, use_container_width=True)
                            else:
                                st.success("Nenhuma falta (em horas) registrada neste período! 🎉")

                        with tab_bar_extras_d:
                            df_top_extras_d = df_consolidado_depto.nlargest(5, 'extras_sum').copy()
                            if not df_top_extras_d.empty and df_top_extras_d['extras_sum'].sum() > 0:
                                df_top_extras_d['Extras Formato Decimal'] = df_top_extras_d['extras_sum'] / 60.0
                                graf_extras_d = alt.Chart(df_top_extras_d).mark_bar(color='#F1C40F').encode(
                                    x=alt.X('Colaborador:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
                                    y=alt.Y('Extras Formato Decimal:Q', title='Horas Extras'),
                                    tooltip=[alt.Tooltip('Colaborador', title='Colaborador'), alt.Tooltip('Extras', title='Extras')]
                                ).properties(height=320)
                                st.altair_chart(graf_extras_d, use_container_width=True)
                            else:
                                st.info("Nenhuma hora extra registrada neste período.")
                                
                        with tab_bar_inat_d:
                            df_top_inat_d = df_consolidado_depto.nlargest(5, 'dias_inativos_sum').copy()
                            if not df_top_inat_d.empty and df_top_inat_d['dias_inativos_sum'].sum() > 0:
                                graf_inat_d = alt.Chart(df_top_inat_d).mark_bar(color='#3498DB').encode(
                                    x=alt.X('Colaborador:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
                                    y=alt.Y('dias_inativos_sum:Q', title='Qtd de Folgas/Férias (Dias)'),
                                    tooltip=[alt.Tooltip('Colaborador', title='Colaborador'), alt.Tooltip('dias_inativos_sum', title='Dias')]
                                ).properties(height=320)
                                st.altair_chart(graf_inat_d, use_container_width=True)
                            else:
                                st.info("Não há registros de Folgas/Férias para este período.")
                                
                        with tab_bar_injust_d:
                            df_top_injust_d = df_consolidado_depto.nlargest(5, 'faltas_injust_sum').copy()
                            if not df_top_injust_d.empty and df_top_injust_d['faltas_injust_sum'].sum() > 0:
                                graf_injust_d = alt.Chart(df_top_injust_d).mark_bar(color='#E67E22').encode(
                                    x=alt.X('Colaborador:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
                                    y=alt.Y('faltas_injust_sum:Q', title='Qtd Não Justificadas (Dias)'),
                                    tooltip=[alt.Tooltip('Colaborador', title='Colaborador'), alt.Tooltip('faltas_injust_sum', title='Dias')]
                                ).properties(height=320)
                                st.altair_chart(graf_injust_d, use_container_width=True)
                            else:
                                st.success("Nenhuma falta não justificada neste período! 🎉")
                                
                        with tab_bar_tot_d:
                            df_top_tot_d = df_consolidado_depto.nlargest(5, 'faltas_totais_sum').copy()
                            if not df_top_tot_d.empty and df_top_tot_d['faltas_totais_sum'].sum() > 0:
                                graf_tot_d = alt.Chart(df_top_tot_d).mark_bar(color='#34495E').encode(
                                    x=alt.X('Colaborador:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
                                    y=alt.Y('faltas_totais_sum:Q', title='Qtd Faltas Totais (Dias)'),
                                    tooltip=[alt.Tooltip('Colaborador', title='Colaborador'), alt.Tooltip('faltas_totais_sum', title='Dias')]
                                ).properties(height=320)
                                st.altair_chart(graf_tot_d, use_container_width=True)
                            else:
                                st.success("Nenhuma falta total neste período! 🎉")

                        # ==========================================
                        # TABELA SETORIAL
                        # ==========================================
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
