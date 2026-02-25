import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date, timedelta
import os
import time

# Configuração da Página
st.set_page_config(page_title="Status - Gestão Integral por Item", layout="wide", page_icon="🏗️")

# --- FUNÇÃO DE AUTO-REFRESH (5 MINUTOS) ---
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

refresh_interval = 300 
if time.time() - st.session_state.last_refresh > refresh_interval:
    st.session_state.last_refresh = time.time()
    st.rerun()

# --- ESTILIZAÇÃO E ANIMAÇÕES (CSS) ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    h1, h2, h3 { color: #634D3E !important; }
    .stButton>button { background-color: #634D3E; color: white; border-radius: 5px; width: 100%; }
    .stInfo { background-color: #f0f2f6; border-left: 5px solid #B59572; }
    
    @keyframes pulse-red {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(255, 0, 0, 0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(255, 0, 0, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(255, 0, 0, 0); }
    }
    
    .alerta-pulsante {
        color: white; 
        background-color: #FF0000; 
        padding: 8px;
        border-radius: 5px; 
        font-weight: bold; 
        animation: pulse-red 2s infinite;
        text-align: center;
        display: block;
    }

    .no-prazo {
        color: white;
        background-color: #28a745;
        padding: 8px;
        border-radius: 5px;
        font-weight: bold;
        text-align: center;
        display: block;
    }

    .semaforo {
        height: 12px;
        width: 12px;
        border-radius: 50%;
        display: inline-block;
        margin-right: 5px;
    }

    @keyframes rocket-launch {
        0% { transform: translateY(100vh) translateX(0px); opacity: 1; }
        50% { transform: translateY(50vh) translateX(20px); }
        100% { transform: translateY(-100vh) translateX(-20px); opacity: 0; }
    }
    .rocket-container {
        position: fixed; bottom: -100px; left: 50%; font-size: 50px;
        z-index: 9999; animation: rocket-launch 3s ease-in forwards;
    }
    </style>
    """, unsafe_allow_html=True)

def disparar_foguete():
    st.markdown('<div class="rocket-container">🚀</div>', unsafe_allow_html=True)

# --- SISTEMA DE LOGIN HÍBRIDO ---
def login():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.title("🔐 Acesso Restrito - Gestão de Gates")
        col_l, col_r = st.columns(2)
        with col_l:
            user = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")
            if st.button("Entrar"):
                if user == st.secrets["credentials"]["master_user"] and \
                   password == st.secrets["credentials"]["master_password"]:
                    st.session_state.authenticated = True
                    st.session_state.user_role = "MASTER"
                    st.session_state.user_display = "Administrador (Master)" 
                    st.session_state.papel_real = "Gerência Geral"
                    st.rerun()
                else:
                    try:
                        temp_conn = st.connection("gsheets", type=GSheetsConnection)
                        df_users = temp_conn.read(worksheet="Usuarios", ttl="1m")
                        df_users['Usuario'] = df_users['Usuario'].astype(str).str.strip()
                        df_users['Senha'] = df_users['Senha'].astype(str).str.strip()
                        user_match = df_users[(df_users['Usuario'] == user) & (df_users['Senha'] == password)]
                        if not user_match.empty:
                            st.session_state.authenticated = True
                            st.session_state.user_role = "USER"
                            nome_na_tabela = user_match['Nome'].iloc[0] if 'Nome' in user_match.columns else user
                            st.session_state.user_display = nome_na_tabela if pd.notnull(nome_na_tabela) else user
                            st.session_state.papel_real = user_match['Papel'].iloc[0]
                            st.rerun()
                        else: st.error("Usuário ou senha inválidos")
                    except Exception as e: st.error(f"Erro ao conectar com tabela de usuários: {e}")
        return False
    return True

if login():
    conn = st.connection("gsheets", type=GSheetsConnection)

    def atualizar_status_lote(lista_ids, novo_status):
        df_pedidos = conn.read(worksheet="Pedidos", ttl=0)
        df_pedidos.loc[df_pedidos['ID_Item'].isin(lista_ids), 'Status_Atual'] = novo_status
        conn.update(worksheet="Pedidos", data=df_pedidos)

    # --- MENU LATERAL ---
    if os.path.exists("Status Apresentação.png"):
        st.sidebar.image("Status Apresentação.png", use_container_width=True)
    else: st.sidebar.title("STATUS MARCENARIA")

    st.sidebar.markdown(f"**👤 {st.session_state.user_display}**")
    papel_usuario = st.session_state.papel_real
    st.sidebar.info(f"Função: {papel_usuario}")
    
    if st.sidebar.button("Log Out"):
        st.session_state.authenticated = False
        st.rerun()

    st.sidebar.markdown("---")
    
    opcoes_menu = ["📊 Resumo e Prazos (Itens)", "📈 Indicadores de Performance", "📉 Monitor por Pedido (CTR)", "🚨 Auditoria", "📥 Importar Itens (Sistema)", "✅ Gate 1: Aceite Técnico", "🏭 Gate 2: Produção", "💰 Gate 3: Material", "🚛 Gate 4: Entrega", "⚠️ Alteração de Pedido"]
    if papel_usuario == "Dono do Pedido (DP)":
        if "🚨 Auditoria" in opcoes_menu: opcoes_menu.remove("🚨 Auditoria")
        if "📈 Indicadores de Performance" in opcoes_menu: opcoes_menu.remove("📈 Indicadores de Performance")
        
    menu = st.sidebar.radio("Navegação", opcoes_menu)

    # --- FUNÇÃO DE GESTÃO DE GATES (CORRIGIDA) ---
    def checklist_gate(gate_id, aba, itens_checklist, responsavel_r, executor_e, msg_bloqueio, proximo_status, objetivo, momento):
        st.header(f"Ficha de Controle: {gate_id}")
        st.markdown(f"**Objetivo:** {objetivo} | **Momento:** {momento}")
        st.info(f"⚖️ **R:** {responsavel_r} | 🔨 **E:** {executor_e}")
        
        try:
            df_pedidos = conn.read(worksheet="Pedidos", ttl="2m")
            status_requerido = "Aguardando Gate 1" if gate_id == "GATE 1" else \
                               "Aguardando Produção (G2)" if gate_id == "GATE 2" else \
                               "Aguardando Materiais (G3)" if gate_id == "GATE 3" else \
                               "Aguardando Entrega (G4)"

            ctr_lista = [""] + sorted(df_pedidos['CTR'].unique().tolist())
            ctr_sel = st.selectbox(f"Selecione a CTR para {gate_id}", ctr_lista, key=f"ctr_gate_{aba}")
            
            if ctr_sel:
                itens_pendentes = df_pedidos[(df_pedidos['CTR'] == ctr_sel) & (df_pedidos['Status_Atual'] == status_requerido)]
                if itens_pendentes.empty:
                    st.success(f"Não há itens pendentes para o {gate_id} nesta CTR.")
                    return

                selecionados = st.multiselect("Itens disponíveis:", options=itens_pendentes['ID_Item'].tolist(), format_func=lambda x: itens_pendentes[itens_pendentes['ID_Item'] == x]['Pedido'].iloc[0], default=itens_pendentes['ID_Item'].tolist(), key=f"multi_{aba}")
                
                if selecionados:
                    pode_assinar = (papel_usuario == responsavel_r or papel_usuario == executor_e or papel_usuario == "Gerência Geral")
                    if papel_usuario == "Consulta": pode_assinar = False

                    with st.form(f"form_batch_{aba}"):
                        respostas = {}
                        for secao, itens in itens_checklist.items():
                            st.markdown(f"#### 🔹 {secao}")
                            for item in itens: 
                                # CHAVE ÚNICA PARA EVITAR ERRO DE ID REPETIDO
                                respostas[item] = st.checkbox(item, key=f"chk_{gate_id}_{aba}_{item.replace(' ', '_')}")
                        
                        obs = st.text_area("Observações Técnicas")
                        btn_label = "VALIDAR LOTE SELECIONADO 🚀" if pode_assinar else "ACESSO APENAS PARA LEITURA"
                        
                        if st.form_submit_button(btn_label, disabled=not pode_assinar):
                            if not all(respostas.values()): st.error(f"❌ BLOQUEIO: {msg_bloqueio}")
                            else:
                                df_gate = conn.read(worksheet=aba, ttl=0)
                                novas_linhas = []
                                logs_auditoria = []
                                for id_item in selecionados:
                                    nova = {"Data": datetime.now().strftime("%d/%m/%Y %H:%M"), "ID_Item": id_item, "Validado_Por": st.session_state.user_display, "Obs": obs}
                                    nova.update(respostas); novas_linhas.append(nova)
                                    item_nome = itens_pendentes[itens_pendentes['ID_Item'] == id_item]['Pedido'].iloc[0]
                                    logs_auditoria.append({
                                        "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                        "Pedido": item_nome,
                                        "Usuario": st.session_state.user_display,
                                        "O que mudou": f"GATE: Avanço para {proximo_status}. Obs: {obs}",
                                        "Impacto no Prazo": "Não",
                                        "Impacto Financeiro": "Não",
                                        "CTR": ctr_sel
                                    })
                                conn.update(worksheet=aba, data=pd.concat([df_gate, pd.DataFrame(novas_linhas)], ignore_index=True))
                                df_alt = conn.read(worksheet="Alteracoes", ttl=0)
                                conn.update(worksheet="Alteracoes", data=pd.concat([df_alt, pd.DataFrame(logs_auditoria)], ignore_index=True))
                                atualizar_status_lote(selecionados, proximo_status)
                                st.success(f"🚀 {len(selecionados)} itens validados!")
                                disparar_foguete(); time.sleep(1); st.rerun()
        except Exception as e: st.error(f"Erro: {e}")

    # --- PÁGINAS ---

    if menu == "📊 Resumo e Prazos (Itens)":
        st.header("🚦 Monitor de Produção (Itens)")
        try:
            df_p = conn.read(worksheet="Pedidos", ttl="5m")
            df_p['Data_Entrega'] = pd.to_datetime(df_p['Data_Entrega'], errors='coerce')
            for idx, row in df_p.sort_values(by='Data_Entrega', na_position='last').iterrows():
                dias = (row['Data_Entrega'].date() - date.today()).days if pd.notnull(row['Data_Entrega']) else None
                status_html = ""
                if dias is None: status_html = '<span style="color: grey;">⚪ SEM DATA</span>'
                elif dias < 0: status_html = f'<div class="alerta-pulsante">❌ ATRASADO ({abs(dias)}d)</div>'
                elif dias <= 3: status_html = f'<div class="alerta-pulsante">🔴 URGENTE ({dias}d)</div>'
                else: status_html = '<div class="no-prazo">🟢 NO PRAZO</div>'
                c1, c2, c3, c4 = st.columns([2, 4, 2, 2])
                with c1: st.write(f"**{row['CTR']}**")
                with c2: st.write(f"**{row['Pedido']}**\n👤 {row['Dono']}")
                with c3: st.write(f"📍 {row['Status_Atual']}\n📅 {row['Data_Entrega'].strftime('%d/%m/%Y') if pd.notnull(row['Data_Entrega']) else 'S/D'}")
                with c4: st.markdown(status_html, unsafe_allow_html=True)
                st.markdown("---")
        except Exception as e: st.error(f"Erro no monitor: {e}")

    elif menu == "📉 Monitor por Pedido (CTR)":
        st.header("📉 Monitor de Produção por CTR")
        try:
            df_p = conn.read(worksheet="Pedidos", ttl="5m")
            df_p['Data_Entrega_DT'] = pd.to_datetime(df_p['Data_Entrega'], errors='coerce')
            ctrs = df_p.groupby('CTR').agg({'ID_Item': 'count', 'Data_Entrega_DT': 'min', 'Dono': 'first'}).reset_index()
            for _, row in ctrs.sort_values(by='Data_Entrega_DT').iterrows():
                ctr_sel = row['CTR']
                itens_obra = df_p[df_p['CTR'] == ctr_sel].copy()
                total_itens = len(itens_obra)
                dias = (row['Data_Entrega_DT'].date() - date.today()).days if pd.notnull(row['Data_Entrega_DT']) else None
                with st.container():
                    c1, c2, c3 = st.columns([4, 3, 3])
                    c1.markdown(f"### {ctr_sel}")
                    c1.write(f"📅 Entrega Crítica: {row['Data_Entrega_DT'].strftime('%d/%m/%Y') if pd.notnull(row['Data_Entrega_DT']) else 'S/D'}")
                    c2.markdown(f"👤 **Gestor:** {row['Dono']}")
                    with c2.popover(f"🔍 Detalhar Itens ({total_itens})", use_container_width=True):
                        for _, item in itens_obra.iterrows():
                            i_dias = (pd.to_datetime(item['Data_Entrega']).date() - date.today()).days if pd.notnull(item['Data_Entrega']) else None
                            cor = "#28a745" if i_dias is not None and i_dias > 3 else "#FF0000" if i_dias is not None else "grey"
                            circulo = f'<span class="semaforo" style="background-color: {cor};"></span>'
                            st.markdown(f"{circulo} **{item['Pedido']}** | 📅 {pd.to_datetime(item['Data_Entrega']).strftime('%d/%m') if pd.notnull(item['Data_Entrega']) else 'S/D'}", unsafe_allow_html=True)
                    if dias is None: status_html = '<span style="color: grey;">⚪ SEM DATA</span>'
                    elif dias < 0: status_html = f'<div class="alerta-pulsante">❌ ATRASO CRÍTICO</div>'
                    elif dias <= 3: status_html = f'<div class="alerta-pulsante">🔴 URGENTE</div>'
                    else: status_html = '<div class="no-prazo">🟢 NO PRAZO</div>'
                    c3.markdown(status_html, unsafe_allow_html=True)
                    st.markdown("---")
        except Exception as e: st.error(f"Erro no monitor por pedido: {e}")

    elif menu == "📈 Indicadores de Performance":
        st.header("📈 Dashboard de Indicadores")
        try:
            df_p = conn.read(worksheet="Pedidos", ttl="1m")
            df_aud = conn.read(worksheet="Alteracoes", ttl="1m")
            df_aud['DT_Filtro'] = pd.to_datetime(df_aud['Data'], format="%d/%m/%Y %H:%M", errors='coerce')
            anos = sorted(df_aud['DT_Filtro'].dt.year.dropna().unique().tolist(), reverse=True)
            meses = {1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}
            c_f1, c_f2 = st.columns(2)
            ano_sel = c_f1.selectbox("Ano", anos if anos else [datetime.now().year])
            mes_sel_num = c_f2.selectbox("Mês", list(meses.keys()), format_func=lambda x: meses[x], index=datetime.now().month-1)
            df_aud_f = df_aud[(df_aud['DT_Filtro'].dt.year == ano_sel) & (df_aud['DT_Filtro'].dt.month == mes_sel_num)]
            
            st.subheader("🚧 Fluxo de Itens por Portão")
            gates_count = df_p['Status_Atual'].value_counts()
            c_g1, c_g2, c_g3, c_g4, c_g5 = st.columns(5)
            c_g1.metric("Gate 1", gates_count.get("Aguardando Gate 1", 0))
            c_g2.metric("Gate 2", gates_count.get("Aguardando Produção (G2)", 0))
            c_g3.metric("Gate 3", gates_count.get("Aguardando Materiais (G3)", 0))
            c_g4.metric("Gate 4", gates_count.get("Aguardando Entrega (G4)", 0))
            c_g5.metric("Concluídos", gates_count.get("CONCLUÍDO ✅", 0))
            
            st.markdown("---")
            st.subheader(f"📊 Performance - {meses[mes_sel_num]}/{ano_sel}")
            df_p['Entrega_DT'] = pd.to_datetime(df_p['Data_Entrega'], errors='coerce')
            itens_mes = df_p[(df_p['Entrega_DT'].dt.year == ano_sel) & (df_p['Entrega_DT'].dt.month == mes_sel_num)]
            atrasados = len(itens_mes[(itens_mes['Entrega_DT'].dt.date < date.today()) & (itens_mes['Status_Atual'] != "CONCLUÍDO ✅")])
            no_prazo = len(itens_mes) - atrasados
            alterados_ids = df_aud_f[df_aud_f['O que mudou'].str.contains("LOTE:", na=False)]['Pedido'].unique()
            com_imp_financeiro = len(df_aud_f[df_aud_f['Impacto Financeiro'] == "Sim"])
            com_imp_prazo = len(df_aud_f[df_aud_f['Impacto no Prazo'] == "Sim"])
            passaram_limpos = len(itens_mes) - len(alterados_ids)
            
            m1, m2, m3 = st.columns(3)
            m1.metric("No Prazo", f"{no_prazo}")
            m2.metric("Atrasados", f"{atrasados}", delta_color="inverse")
            m3.metric("Sem Alterações (Limpos)", f"{max(0, passaram_limpos)}")
            
            m4, m5, m6 = st.columns(3)
            m4.metric("Impacto Financeiro 💰", f"{com_imp_financeiro}", delta_color="inverse")
            m5.metric("Impacto no Prazo ⏰", f"{com_imp_prazo}", delta_color="inverse")
            m6.metric("Total de Itens Alterados", f"{len(alterados_ids)}")
        except Exception as e: st.error(f"Erro nos indicadores: {e}")

    elif menu == "📥 Importar Itens (Sistema)":
        st.header("📥 Importar Itens da Marcenaria")
        if papel_usuario not in ["Gerência Geral", "PCP"]: st.error("Apenas PCP ou Gerência podem importar novos dados.")
        else:
            up = st.file_uploader("Arquivo egsDataGrid", type=["csv", "xlsx"])
            if up:
                try:
                    df_up = pd.read_csv(up) if up.name.endswith('csv') else pd.read_excel(up)
                    if st.button("Confirmar Importação"):
                        df_base = conn.read(worksheet="Pedidos", ttl=0)
                        novos = []
                        for _, r in df_up.iterrows():
                            uid = f"{r['Centro de custo']}-{r['Id Programação']}"
                            dt_crua = pd.to_datetime(r['Data Entrega'], errors='coerce')
                            dt_limpa = dt_crua.strftime('%Y-%m-%d') if pd.notnull(dt_crua) else ""
                            if uid not in df_base['ID_Item'].astype(str).values:
                                novos.append({"ID_Item": uid, "CTR": r['Centro de custo'], "Obra": r['Obra'], "Item": r['Item'], "Pedido": r['Produto'], "Dono": r['Gestor'], "Status_Atual": "Aguardando Gate 1", "Data_Entrega": dt_limpa, "Quantidade": r['Quantidade'], "Unidade": r['Unidade']})
                        if novos: conn.update(worksheet="Pedidos", data=pd.concat([df_base, pd.DataFrame(novos)], ignore_index=True)); st.success("Importado!")
                except Exception as e: st.error(f"Erro na importação: {e}")

    elif menu == "⚠️ Alteração de Pedido":
        st.header("🔄 Alteração de Pedido em Lote")
        if papel_usuario not in ["Gerência Geral", "PCP"]: st.error("Acesso negado.")
        else:
            try:
                df_p = conn.read(worksheet="Pedidos", ttl="1m")
                df_p['Data_Entrega_Str'] = pd.to_datetime(df_p['Data_Entrega'], errors='coerce').dt.strftime('%Y-%m-%d').fillna('')
                ctr_lista = [""] + sorted(df_p['CTR'].unique().tolist())
                ctr_sel = st.selectbox("Selecione a CTR para Alteração", ctr_lista, key="ctr_alteracao")
                if ctr_sel:
                    itens_da_ctr = df_p[df_p['CTR'] == ctr_sel]
                    selecionados = st.multiselect("Selecione os itens:", options=itens_da_ctr['ID_Item'].tolist(), format_func=lambda x: f"{itens_da_ctr[itens_da_ctr['ID_Item'] == x]['Pedido'].iloc[0]}", default=itens_da_ctr['ID_Item'].tolist())
                    if selecionados:
                        with st.form("form_alteracao_lote"):
                            st.info(f"Alterando {len(selecionados)} itens")
                            col1, col2 = st.columns(2)
                            gestor_atual = itens_da_ctr[itens_da_ctr['ID_Item'] == selecionados[0]]['Dono'].iloc[0]
                            novo_gestor = col1.text_input("Novo Gestor", value=gestor_atual)
                            data_at = itens_da_ctr[itens_da_ctr['ID_Item'] == selecionados[0]]['Data_Entrega_Str'].iloc[0]
                            try: data_sug = datetime.strptime(data_at, '%Y-%m-%d').date() if data_at else date.today()
                            except: data_sug = date.today()
                            nova_data = col2.date_input("Nova Data", value=data_sug)
                            st.markdown("#### ⚖️ Impactos da Alteração")
                            c_imp1, c_imp2 = st.columns(2)
                            imp_prazo = c_imp1.radio("Impacto no Prazo?", ["Não", "Sim"], horizontal=True)
                            imp_financeiro = c_imp2.radio("Impacto Financeiro?", ["Não", "Sim"], horizontal=True)
                            motivo = st.text_area("Motivo da Alteração")
                            if st.form_submit_button("APLICAR ALTERAÇÕES EM LOTE 🚀"):
                                if not motivo: st.error("❌ Descreva o motivo")
                                else:
                                    df_p.loc[df_p['ID_Item'].isin(selecionados), 'Dono'] = novo_gestor
                                    df_p.loc[df_p['ID_Item'].isin(selecionados), 'Data_Entrega'] = nova_data.strftime('%Y-%m-%d')
                                    df_save = df_p.drop(columns=['Data_Entrega_Str'])
                                    conn.update(worksheet="Pedidos", data=df_save)
                                    df_alt = conn.read(worksheet="Alteracoes", ttl=0)
                                    logs = [{"Data": datetime.now().strftime("%d/%m/%Y %H:%M"), "Pedido": df_p[df_p['ID_Item']==id]['Pedido'].iloc[0], "CTR": ctr_sel, "Usuario": st.session_state.user_display, "O que mudou": f"LOTE: Data {nova_data} / Gestor {novo_gestor}. Motivo: {motivo}", "Impacto no Prazo": imp_prazo, "Impacto Financeiro": imp_financeiro} for id in selecionados]
                                    conn.update(worksheet="Alteracoes", data=pd.concat([df_alt, pd.DataFrame(logs)], ignore_index=True))
                                    st.success("Atualizados!"); disparar_foguete(); time.sleep(1); st.rerun()
            except Exception as e: st.error(f"Erro: {e}")

    elif menu == "🚨 Auditoria":
        st.header("🚨 Auditoria")
        try:
            df_aud = conn.read(worksheet="Alteracoes", ttl="1m")
            df_aud['temp_date'] = pd.to_datetime(df_aud['Data'], format="%d/%m/%Y %H:%M", errors='coerce')
            df_aud = df_aud.sort_values(by='temp_date', ascending=False).drop(columns=['temp_date'])
            st.table(df_aud)
        except Exception as e: st.error(f"Erro na auditoria: {e}")

    # --- EXECUÇÃO DOS GATES ---
    elif menu == "✅ Gate 1: Aceite Técnico":
        itens = {"Informações Comerciais": ["Pedido registrado", "Cliente identificado", "Tipo de obra definido", "Responsável identificado"], "Escopo Técnico": ["Projeto mínimo recebido", "Ambientes definidos", "Materiais principais", "Itens fora do padrão"], "Prazo (prévia)": ["Prazo solicitado registrado", "Prazo avaliado", "Risco de prazo"], "Governança": ["Dono do Pedido definido", "PCP validou viabilidade", "Aprovado formalmente"]}
        checklist_gate("GATE 1", "Checklist_G1", itens, "Dono do Pedido (DP)", "PCP", "Projeto incompleto ➡️ BLOQUEADO", "Aguardando Produção (G2)", "Impedir entrada mal definida", "Antes do plano")

    elif menu == "🏭 Gate 2: Produção":
        itens = {"Planejamento": ["Sequenciado", "Capacidade validada", "Gargalo identificado", "Gargalo protegido"], "Projeto": ["Projeto técnico liberado", "Medidas conferidas", "Versão registrada"], "Comunicação": ["Produção ciente", "Prazo interno registrado", "Alterações registradas"]}
        checklist_gate("GATE 2", "Checklist_G2", itens, "PCP", "Produção", "Sem plano ➡️ BLOQUEADO", "Aguardando Materiais (G3)", "Produzir planejado", "No corte")

    elif menu == "💰 Gate 3: Material":
        itens = {"Materiais": ["Lista validada", "Quantidades conferidas", "Materiais especiais"], "Compras": ["Fornecedores definidos", "Lead times confirmados", "Datas registradas"], "Financeiro": ["Impacto caixa validado", "Compra autorizada", "Forma de pagamento"]}
        checklist_gate("GATE 3", "Checklist_G3", itens, "Financeiro", "Compras", "Falta material ➡️ PARADO", "Aguardando Entrega (G4)", "Fábrica sem parada", "Na montagem")

    elif menu == "🚛 Gate 4: Entrega":
        itens = {"Produto": ["Produção concluída", "Qualidade conferida", "Separados por pedido"], "Logística": ["Checklist carga", "Frota definida", "Rota planejada"], "Prazo": ["Data validada", "Cliente informado", "Equipe montagem alinhada"]}
        checklist_gate("GATE 4", "Checklist_G4", itens, "Dono do Pedido (DP)", "Logística", "Erro acabamento ➡️ NÃO carrega", "CONCLUÍDO ✅", "Entrega perfeita", "Na carga")
