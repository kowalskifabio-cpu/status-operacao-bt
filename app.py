import streamlit as st
from streamlit_gsheets import GSheetsConnection
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, date, timedelta
import os
import time
import re

# Configuração da Página
st.set_page_config(page_title="Status - Gestão Integral por Item", layout="wide", page_icon="🏗️")

# --- 1. CONEXÕES (HÍBRIDA: SHEETS + SUPABASE) ---
@st.cache_resource
def init_supabase():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except:
        return None

supabase = init_supabase()
conn = st.connection("gsheets", type=GSheetsConnection)

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

# --- FUNÇÃO DE AUXÍLIO PARA ORDENAÇÃO ---
def extrair_numero_item(texto):
    try:
        nums = re.findall(r'\d+', str(texto))
        return int(nums[0]) if nums else 9999
    except:
        return 9999

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
                        df_users = temp_conn.read(worksheet="Usuarios", ttl="10m")
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
    
    @st.cache_data(ttl=15)
    def load_pedidos():
        df = conn.read(worksheet="Pedidos")
        df = df.dropna(subset=['ID_Item'])
        df['ID_Item'] = df['ID_Item'].astype(str).str.strip()
        df['sort_num'] = df['Item'].apply(extrair_numero_item)
        return df.drop_duplicates(subset=['ID_Item'], keep='first')

    @st.cache_data(ttl=60)
    def load_historico():
        try:
            df = conn.read(worksheet="Pedidos_Concluidos")
            return df
        except:
            return pd.DataFrame()

    df_global = load_pedidos()
    df_concluidos_global = load_historico()

    def salvar_no_supabase(id_item, novo_status, row_dados=None):
        try:
            payload = {"id_item": str(id_item), "status_atual": str(novo_status)}
            if row_dados is not None:
                payload.update({
                    "ctr": str(row_dados['CTR']),
                    "obra": str(row_dados.get('Obra', '')),
                    "item_projeto": str(row_dados.get('Item', '')),
                    "pedido": str(row_dados['Pedido']),
                    "dono": str(row_dados['Dono']),
                    "data_entrega": str(row_dados['Data_Entrega']) if pd.notnull(row_dados['Data_Entrega']) else None,
                    "quantidade": float(row_dados.get('Quantidade', 0)) if pd.notnull(row_dados.get('Quantidade', 0)) else 0,
                    "unidade": str(row_dados.get('Unidade', 'un'))
                })
            supabase.table("pedidos").upsert(payload).execute()
        except Exception as e: pass

    def atualizar_status_lote(lista_ids, novo_status, df_referencia):
        df_update = conn.read(worksheet="Pedidos", ttl=0)
        df_update.loc[df_update['ID_Item'].isin(lista_ids), 'Status_Atual'] = novo_status
        df_update = df_update.drop_duplicates(subset=['ID_Item'], keep='first')
        conn.update(worksheet="Pedidos", data=df_update)
        for id_item in lista_ids:
            try:
                row = df_referencia[df_referencia['ID_Item'] == id_item].iloc[0]
                salvar_no_supabase(id_item, novo_status, row)
            except: continue
        st.cache_data.clear() 

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
    
    opcoes_menu = [
        "📉 Monitor por Pedido (CTR)", 
        "📊 Resumo e Prazos (Itens)", 
        "📈 Indicadores de Performance", 
        "🚨 Auditoria", 
        "🛠️ Portão de Retrabalho",
        "✅ Gate 1: Aceite Técnico", 
        "💰 Gate 2: Material", 
        "🏭 Gate 3: Production", 
        "🚛 Gate 4: Entrega", 
        "⚠️ Alteração de Pedido",
        "📥 Importar Itens (Sistema)",
        "🛠️ Recuperação de Pedidos",
        "⚙️ SINCRONIZAÇÃO SUPABASE",
        "🏁 Concluir Pedidos (Baixa)"
    ]

    if papel_usuario == "Dono do Pedido (DP)":
        for item in ["🚨 Auditoria", "📈 Indicadores de Performance", "🛠️ Portão de Retrabalho", "🛠️ Recuperação de Pedidos", "⚙️ SINCRONIZAÇÃO SUPABASE", "🏁 Concluir Pedidos (Baixa)"]:
            if item in opcoes_menu: opcoes_menu.remove(item)
        
    menu = st.sidebar.radio("Navegação", opcoes_menu)

    # --- ABA: CONCLUIR PEDIDOS (BAIXA DEFINITIVA) ---
    if menu == "🏁 Concluir Pedidos (Baixa)":
        st.header("🏁 Baixa Definitiva de Pedidos")
        st.info("Pedidos concluídos saem da lista de atrasados e vão para o histórico de entregas.")
        
        if papel_usuario not in ["Gerência Geral", "PCP"]:
            st.error("Acesso restrito ao PCP e Gerência.")
        else:
            df_concluir = df_global[df_global['Status_Atual'] == "CONCLUÍDO ✅"]
            if df_concluir.empty:
                st.warning("Não há itens marcados como 'CONCLUÍDO ✅' para dar baixa no sistema.")
            else:
                ctr_lista = [""] + sorted(df_concluir['CTR'].unique().tolist())
                ctr_sel = st.selectbox("Selecione a CTR para dar baixa:", ctr_lista)
                
                if ctr_sel:
                    itens_baixa = df_concluir[df_concluir['CTR'] == ctr_sel]
                    selecionados = st.multiselect("Selecione os itens para arquivar:", 
                                                  options=itens_baixa['ID_Item'].tolist(), 
                                                  format_func=lambda x: f"{itens_baixa[itens_baixa['ID_Item'] == x]['Pedido'].iloc[0]}",
                                                  default=itens_baixa['ID_Item'].tolist())
                    
                    if selecionados:
                        if st.button("🚀 DAR BAIXA E ARQUIVAR SELECIONADOS"):
                            df_pedidos = conn.read(worksheet="Pedidos", ttl=0)
                            try:
                                df_historico = conn.read(worksheet="Pedidos_Concluidos", ttl=0)
                            except:
                                df_historico = pd.DataFrame(columns=df_pedidos.columns.tolist() + ["Data_Finalizacao", "Performance"])
                            
                            rows_to_move = df_pedidos[df_pedidos['ID_Item'].isin(selecionados)].copy()
                            rows_to_move['Data_Finalizacao'] = datetime.now().strftime("%d/%m/%Y %H:%M")
                            
                            hoje = date.today()
                            def calcular_performance(row):
                                try:
                                    entrega = pd.to_datetime(row['Data_Entrega']).date()
                                    return "NO PRAZO" if hoje <= entrega else "ATRASADO"
                                except: return "S/D"
                            
                            rows_to_move['Performance'] = rows_to_move.apply(calcular_performance, axis=1)
                            
                            df_final_hist = pd.concat([df_historico, rows_to_move], ignore_index=True)
                            df_final_pedidos = df_pedidos[~df_pedidos['ID_Item'].isin(selecionados)]
                            
                            conn.update(worksheet="Pedidos_Concluidos", data=df_final_hist)
                            conn.update(worksheet="Pedidos", data=df_final_pedidos)
                            
                            for id_item in selecionados:
                                try:
                                    supabase.table("pedidos").update({"status_atual": "ARQUIVADO"}).eq("id_item", id_item).execute()
                                except: pass
                            
                            st.success(f"✅ {len(selecionados)} itens arquivados com sucesso!")
                            st.cache_data.clear()
                            time.sleep(1.5)
                            st.rerun()

    # --- FUNÇÃO DE CHECKLIST (GATES) ---
    def checklist_gate(gate_id, aba, itens_checklist, responsavel_r, executor_e, msg_bloqueio, proximo_status, objetivo, momento, df_p):
        st.header(f"Ficha de Controle: {gate_id}")
        st.markdown(f"**Objetivo:** {objetivo} | **Momento:** {momento}")
        st.info(f"⚖️ **R:** {responsavel_r} | 🔨 **E:** {executor_e}")
        
        try:
            status_requerido = "Aguardando Gate 1" if gate_id == "GATE 1" else \
                               "Aguardando Materiais (G2)" if gate_id == "GATE 2" else \
                               "Aguardando Produção (G3)" if gate_id == "GATE 3" else \
                               "Aguardando Entrega (G4)"

            ctrs_com_itens_pendentes = df_p[df_p['Status_Atual'] == status_requerido]['CTR'].unique().tolist()
            ctr_lista = [""] + sorted(ctrs_com_itens_pendentes)
            ctr_sel = st.selectbox(f"Selecione a CTR para {gate_id}", ctr_lista, key=f"ctr_gate_{aba}")
            
            if ctr_sel:
                itens_pendentes = df_p[(df_p['CTR'] == ctr_sel) & (df_p['Status_Atual'] == status_requerido)].sort_values(by='sort_num')
                if itens_pendentes.empty:
                    st.info(f"Não há mais itens pendentes.")
                    return

                selecionados = st.multiselect("Itens disponíveis para validação:", 
                                              options=itens_pendentes['ID_Item'].tolist(), 
                                              format_func=lambda x: f"{itens_pendentes[itens_pendentes['ID_Item'] == x]['Pedido'].iloc[0]}", 
                                              default=itens_pendentes['ID_Item'].tolist(), 
                                              key=f"multi_{aba}")
                
                if selecionados:
                    pode_assinar = (papel_usuario == responsavel_r or papel_usuario == executor_e or papel_usuario == "Gerência Geral")
                    if papel_usuario == "Consulta": pode_assinar = False

                    with st.form(f"form_batch_{aba}"):
                        respostas = {}
                        for secao, itens in itens_checklist.items():
                            st.markdown(f"#### 🔹 {secao}")
                            for item in itens: 
                                respostas[item] = st.checkbox(item, key=f"chk_{gate_id}_{aba}_{item.replace(' ', '_')}")
                        
                        obs = st.text_area("Observações Técnicas")
                        if st.form_submit_button("VALIDAR LOTE SELECIONADO 🚀", disabled=not pode_assinar):
                            if not all(respostas.values()): st.error(f"❌ BLOQUEIO: {msg_bloqueio}")
                            else:
                                df_gate = conn.read(worksheet=aba, ttl="1m")
                                novas_linhas = []
                                logs_auditoria = []
                                for id_item in selecionados:
                                    # CAPTURA O DONO DO ITEM PARA A AUDITORIA
                                    dono_item = itens_pendentes[itens_pendentes['ID_Item'] == id_item]['Dono'].iloc[0]
                                    
                                    nova = {"Data": datetime.now().strftime("%d/%m/%Y %H:%M"), "ID_Item": id_item, "Validado_Por": st.session_state.user_display, "Obs": obs}
                                    nova.update(respostas); novas_linhas.append(nova)
                                    item_nome = itens_pendentes[itens_pendentes['ID_Item'] == id_item]['Pedido'].iloc[0]
                                    logs_auditoria.append({
                                        "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                        "Pedido": item_nome, "Usuario": st.session_state.user_display,
                                        "Dono": dono_item,
                                        "O que mudou": f"GATE: Avanço para {proximo_status}. Obs: {obs}",
                                        "Impacto no Prazo": "Não", "Impacto Financeiro": "Não", "CTR": ctr_sel
                                    })
                                conn.update(worksheet=aba, data=pd.concat([df_gate, pd.DataFrame(novas_linhas)], ignore_index=True))
                                df_alt = conn.read(worksheet="Alteracoes", ttl="1m")
                                conn.update(worksheet="Alteracoes", data=pd.concat([df_alt, pd.DataFrame(logs_auditoria)], ignore_index=True))
                                atualizar_status_lote(selecionados, proximo_status, df_p)
                                st.success(f"🚀 {len(selecionados)} itens validados!")
                                disparar_foguete(); time.sleep(1); st.rerun()
        except Exception as e: st.error(f"Erro: {e}")

    # --- PÁGINAS DO MONITOR ---

    if menu == "📉 Monitor por Pedido (CTR)":
        st.header("📉 Monitor de Produção por CTR")
        try:
            df_p = df_global.copy()
            c_f1, c_f2 = st.columns(2)
            filtro_gestor = c_f1.multiselect("Filtrar por Gestor", sorted(df_p['Dono'].unique()))
            filtro_ctr = c_f2.multiselect("Filtrar por CTR", sorted(df_p['CTR'].unique()))
            if filtro_gestor: df_p = df_p[df_p['Dono'].isin(filtro_gestor)]
            if filtro_ctr: df_p = df_p[df_p['CTR'].isin(filtro_ctr)]
            df_p['Data_Entrega_DT'] = pd.to_datetime(df_p['Data_Entrega'], errors='coerce')
            ctrs = df_p.groupby('CTR').agg({'ID_Item': 'count', 'Data_Entrega_DT': 'min', 'Dono': 'first'}).reset_index()
            
            for _, row in ctrs.sort_values(by='Data_Entrega_DT').iterrows():
                ctr_sel = row['CTR']
                itens_obra = df_p[df_p['CTR'] == ctr_sel].sort_values(by='sort_num').copy()
                total_itens = len(itens_obra)
                dias = (row['Data_Entrega_DT'].date() - date.today()).days if pd.notnull(row['Data_Entrega_DT']) else None
                with st.container():
                    c1, c2, c3 = st.columns([4, 3, 3])
                    c1.markdown(f"### {ctr_sel}")
                    c1.write(f"📅 Entrega Crítica: {row['Data_Entrega_DT'].strftime('%d/%m/%Y') if pd.notnull(row['Data_Entrega_DT']) else 'S/D'}")
                    c2.markdown(f"👤 **Gestor:** {row['Dono']}")
                    with c2.popover(f"🔍 Detalhar Itens ({total_itens})", use_container_width=True):
                        for _, item in itens_obra.iterrows():
                            i_dt = pd.to_datetime(item['Data_Entrega'], errors='coerce')
                            i_dias = (i_dt.date() - date.today()).days if pd.notnull(i_dt) else None
                            cor = "#28a745" if i_dias is not None and i_dias > 3 else "#FF0000" if i_dias is not None else "grey"
                            circulo = f'<span class="semaforo" style="background-color: {cor};"></span>'
                            st.markdown(f"{circulo} **{item['Pedido']}** | 📍 {item['Status_Atual']} | 📅 {i_dt.strftime('%d/%m') if pd.notnull(i_dt) else 'S/D'}", unsafe_allow_html=True)
                            
                            # --- BOTÃO DE RETRABALHO (MELHORIA SOLICITADA) ---
                            if item['Status_Atual'] != "⚠️ Em Retrabalho":
                                with st.expander("🚨 Sinalizar Retrabalho"):
                                    motivo_ret = st.text_input("Motivo do Retrabalho", key=f"ret_{item['ID_Item']}")
                                    if st.button("CONFIRMAR RETRABALHO", key=f"btn_ret_{item['ID_Item']}"):
                                        if not motivo_ret: st.warning("Descreva o motivo.")
                                        else:
                                            # Atualiza no Sheets e Supabase
                                            atualizar_status_lote([item['ID_Item']], "⚠️ Em Retrabalho", df_p)
                                            # Log de Auditoria
                                            df_alt = conn.read(worksheet="Alteracoes", ttl=0)
                                            log_r = {
                                                "Data": datetime.now().strftime("%d/%m/%Y %H:%M"), 
                                                "Pedido": item['Pedido'], 
                                                "Usuario": st.session_state.user_display, 
                                                "Dono": item['Dono'],
                                                "O que mudou": f"ENTRADA RETRABALHO: {motivo_ret}", 
                                                "Impacto no Prazo": "Sim", 
                                                "Impacto Financeiro": "Sim", 
                                                "CTR": ctr_sel
                                            }
                                            conn.update(worksheet="Alteracoes", data=pd.concat([df_alt, pd.DataFrame([log_r])], ignore_index=True))
                                            # Log de Histórico de Retrabalho para BI
                                            try:
                                                df_hist_ret = conn.read(worksheet="Historico_Retrabalho", ttl=0)
                                                log_h = {"Data": log_r['Data'], "ID_Item": item['ID_Item'], "Pedido": item['Pedido'], "Dono": item['Dono'], "CTR": ctr_sel, "Motivo_Entrada": motivo_ret}
                                                conn.update(worksheet="Historico_Retrabalho", data=pd.concat([df_hist_ret, pd.DataFrame([log_h])], ignore_index=True))
                                            except: pass
                                            st.success("Item movido para retrabalho!"); time.sleep(1); st.rerun()

                    if dias is None: status_html = '<span style="color: grey;">⚪ SEM DATA</span>'
                    elif dias < 0: status_html = f'<div class="alerta-pulsante">❌ ATRASO CRÍTICO</div>'
                    elif dias <= 3: status_html = f'<div class="alerta-pulsante">🔴 URGENTE</div>'
                    else: status_html = '<div class="no-prazo">🟢 NO PRAZO</div>'
                    c3.markdown(status_html, unsafe_allow_html=True)
                    st.markdown("---")

            if not df_concluidos_global.empty:
                st.markdown("### 🏁 Histórico de Pedidos Concluídos")
                with st.expander("Ver itens arquivados desta consulta"):
                    df_c_filtro = df_concluidos_global.copy()
                    if filtro_ctr: df_c_filtro = df_c_filtro[df_c_filtro['CTR'].isin(filtro_ctr)]
                    if filtro_gestor: df_c_filtro = df_c_filtro[df_c_filtro['Dono'].isin(filtro_gestor)]
                    if df_c_filtro.empty: st.info("Nenhum item concluído para os filtros.")
                    else: st.dataframe(df_c_filtro[['CTR', 'Pedido', 'Dono', 'Data_Finalizacao', 'Performance']], use_container_width=True)

        except Exception as e: st.error(f"Erro no monitor: {e}")

    elif menu == "📊 Resumo e Prazos (Itens)":
        st.header("🚦 Monitor de Produção (Itens)")
        try:
            df_p = df_global.copy().sort_values(by=['Data_Entrega', 'sort_num'])
            c_f1, c_f2 = st.columns(2)
            filtro_gestor = c_f1.multiselect("Filtrar por Gestor", sorted(df_p['Dono'].unique()), key="f_gest_itens")
            filtro_ctr = c_f2.multiselect("Filtrar por CTR", sorted(df_p['CTR'].unique()), key="f_ctr_itens")
            if filtro_gestor: df_p = df_p[df_p['Dono'].isin(filtro_gestor)]
            if filtro_ctr: df_p = df_p[df_p['CTR'].isin(filtro_ctr)]
            df_p['Data_Entrega'] = pd.to_datetime(df_p['Data_Entrega'], errors='coerce')
            for idx, row in df_p.iterrows():
                dias = (row['Data_Entrega'].date() - date.today()).days if pd.notnull(row['Data_Entrega']) else None
                status_html = ""
                if dias is None: status_html = '<span style="color: grey;">⚪ SEM DATA</span>'
                elif dias < 0: status_html = f'<div class="alerta-pulsante">❌ ATRASO ({abs(dias)}d)</div>'
                elif dias <= 3: status_html = f'<div class="alerta-pulsante">🔴 URGENTE ({dias}d)</div>'
                else: status_html = '<div class="no-prazo">🟢 NO PRAZO</div>'
                c1, c2, c3, c4 = st.columns([2, 4, 2, 2])
                with c1: st.write(f"**{row['CTR']}**")
                with c2: st.write(f"**{row['Pedido']}**\n👤 {row['Dono']}")
                with c3: st.write(f"📍 {row['Status_Atual']}\n📅 {row['Data_Entrega'].strftime('%d/%m/%Y') if pd.notnull(row['Data_Entrega']) else 'S/D'}")
                with c4: st.markdown(status_html, unsafe_allow_html=True)
                st.markdown("---")

            if not df_concluidos_global.empty:
                st.markdown("### 🏁 Itens Arquivados")
                with st.expander("Clique para expandir o histórico de baixas"):
                    df_c_filtro = df_concluidos_global.copy()
                    if filtro_ctr: df_c_filtro = df_c_filtro[df_c_filtro['CTR'].isin(filtro_ctr)]
                    if filtro_gestor: df_c_filtro = df_c_filtro[df_c_filtro['Dono'].isin(filtro_gestor)]
                    st.dataframe(df_c_filtro[['CTR', 'Pedido', 'Data_Entrega', 'Data_Finalizacao', 'Performance']], use_container_width=True)

        except Exception as e: st.error(f"Erro no monitor: {e}")

    # --- ABA: RETRABALHO (MELHORIA SOLICITADA) ---
    elif menu == "🛠️ Portão de Retrabalho":
        st.header("🛠️ Gestão de Retrabalho")
        df_ret = df_global[df_global['Status_Atual'] == "⚠️ Em Retrabalho"]
        if df_ret.empty:
            st.success("Nenhum item em retrabalho no momento.")
        else:
            ctrs_ret = [""] + sorted(df_ret['CTR'].unique().tolist())
            ctr_sel = st.selectbox("Selecione a CTR com retrabalho:", ctrs_ret)
            if ctr_sel:
                itens_pend = df_ret[df_ret['CTR'] == ctr_sel]
                selecionados = st.multiselect("Itens para validar:", options=itens_pend['ID_Item'].tolist(), format_func=lambda x: f"{itens_pend[itens_pend['ID_Item'] == x]['Pedido'].iloc[0]}")
                if selecionados:
                    with st.form("form_retrabalho"):
                        st.markdown("#### ✅ Checklist de Qualidade")
                        c1 = st.checkbox("Peça Danificada Identificada")
                        c2 = st.checkbox("Material Solicitado")
                        c3 = st.checkbox("Prioridade Produção Confirmada")
                        obs_ret = st.text_area("Observações do Reparo")
                        proximo_gate = st.selectbox("Retornar para qual portão?", ["Aguardando Produção (G3)", "Aguardando Entrega (G4)"])
                        
                        if st.form_submit_button("CONCLUIR RETRABALHO 🛠️"):
                            if not all([c1, c2, c3]): st.error("Valide todo o checklist.")
                            else:
                                # Registro na aba Checklist_Retrabalho
                                try:
                                    df_chk = conn.read(worksheet="Checklist_Retrabalho", ttl=0)
                                    novas_chks = [{"Data": datetime.now().strftime("%d/%m/%Y %H:%M"), "ID_Item": i, "Validado_Por": st.session_state.user_display, "Obs": obs_ret} for i in selecionados]
                                    conn.update(worksheet="Checklist_Retrabalho", data=pd.concat([df_chk, pd.DataFrame(novas_chks)], ignore_index=True))
                                except: pass
                                
                                # Atualiza status final (Opção A: Rápida)
                                atualizar_status_lote(selecionados, proximo_gate, df_ret)
                                st.success("Itens reintroduzidos no fluxo!"); time.sleep(1); st.rerun()

    elif menu == "✅ Gate 1: Aceite Técnico":
        itens = {"Informações Comerciais": ["Pedido registrado", "Cliente identificado", "Tipo de obra definido", "Responsável identificado"], "Escopo Técnico": ["Projeto mínimo recebido", "Ambientes definidos", "Materiais principais", "Itens fora do padrão"], "Prazo (prévia)": ["Prazo solicitado registrado", "Prazo avaliado", "Risco de prazo"], "Governança": ["Dono do Pedido definido", "PCP validou viabilidade", "Aprovado formalmente"]}
        checklist_gate("GATE 1", "Checklist_G1", itens, "Dono do Pedido (DP)", "PCP", "Projeto incompleto ➡️ BLOQUEADO", "Aguardando Materiais (G2)", "Impedir entrada mal definida", "Antes do plano", df_global)

    elif menu == "💰 Gate 2: Material":
        itens = {"Materiais": ["Lista validada", "Quantidades conferidas", "Materiais especiais"], "Compras": ["Fornecedores definidos", "Lead times confirmados", "Datas registradas"], "Financeiro": ["Impacto caixa validado", "Compra autorizada", "Forma de pagamento"]}
        checklist_gate("GATE 2", "Checklist_G2", itens, "Financeiro", "Compras", "Falta material ➡️ PARADO", "Aguardando Produção (G3)", "Fábrica sem parada", "Na montagem", df_global)

    elif menu == "🏭 Gate 3: Production":
        itens = {"Planejamento": ["Sequenciado", "Capacidade validada", "Gargalo identificado", "Gargalo protegido"], "Projeto": ["Projeto técnico liberado", "Medidas conferidas", "Versão registrada"], "Comunicação": ["Produção ciente", "Prazo interno registrado", "Alterações registradas"]}
        checklist_gate("GATE 3", "Checklist_G3", itens, "PCP", "Produção", "Sem plano ➡️ BLOQUEADO", "Aguardando Entrega (G4)", "Produzir planejado", "No corte", df_global)

    elif menu == "🚛 Gate 4: Entrega":
        itens = {"Produto": ["Produção concluída", "Qualidade conferida", "Separados por pedido"], "Logística": ["Checklist carga", "Frota definida", "Rota planejada"], "Prazo": ["Data validada", "Cliente informado", "Equipe montagem alinhada"]}
        checklist_gate("GATE 4", "Checklist_G4", itens, "Dono do Pedido (DP)", "Logística", "Erro acabamento ➡️ NÃO carrega", "CONCLUÍDO ✅", "Entrega perfeita", "Na carga", df_global)

    # --- ABA: INDICADORES (MELHORIA SOLICITADA: FILTRO PERÍODO) ---
    elif menu == "📈 Indicadores de Performance":
        st.header("📈 Dashboard de Indicadores")
        try:
            df_p = df_global.copy()
            df_h = df_concluidos_global.copy()
            
            # FILTROS DE TOPO (PERÍODO E GESTOR)
            c_p1, c_p2, c_p3 = st.columns([2, 2, 4])
            data_ini = c_p1.date_input("Início", value=date.today() - timedelta(days=30))
            data_fim = c_p2.date_input("Fim", value=date.today())
            
            todos_gestores = sorted(list(set(df_p['Dono'].unique()) | set(df_h['Dono'].unique() if not df_h.empty else [])))
            gestor_sel = c_p3.multiselect("🔍 Filtrar por Dono do Pedido", todos_gestores, key="filtro_bi_gestor")
            
            # FILTRO DE PERÍODO NO HISTÓRICO DE RETRABALHO
            try:
                df_hist_r = conn.read(worksheet="Historico_Retrabalho", ttl=10)
                df_hist_r['dt_obj'] = pd.to_datetime(df_hist_r['Data'], dayfirst=True).dt.date
                df_hist_r = df_hist_r[(df_hist_r['dt_obj'] >= data_ini) & (df_hist_r['dt_obj'] <= data_fim)]
                if gestor_sel: df_hist_r = df_hist_r[df_hist_r['Dono'].isin(gestor_sel)]
                total_ret = len(df_hist_r)
            except: total_ret = 0

            if gestor_sel:
                df_p = df_p[df_p['Dono'].isin(gestor_sel)]
                if not df_h.empty: df_h = df_h[df_h['Dono'].isin(gestor_sel)]

            st.subheader("🚧 Fluxo de Itens por Portão")
            gates_count = df_p['Status_Atual'].value_counts()
            c_g1, c_g2, c_g3, c_g4, c_r = st.columns(5)
            c_g1.metric("Gate 1", gates_count.get("Aguardando Gate 1", 0))
            c_g2.metric("Gate 2", gates_count.get("Aguardando Materiais (G2)", 0))
            c_g3.metric("Gate 3", gates_count.get("Aguardando Produção (G3)", 0))
            c_g4.metric("Gate 4", gates_count.get("Aguardando Entrega (G4)", 0))
            c_r.metric("⚠️ Retrabalhos (No Período)", total_ret)

            st.markdown("---")
            st.subheader("📊 Performance de Entregas (Arquivados)")
            if df_h.empty: st.info("Sem dados históricos para este filtro.")
            else:
                perf_counts = df_h['Performance'].value_counts()
                c_graf1, c_graf2 = st.columns(2)
                with c_graf1: 
                    st.write("**Eficiência de Prazo**")
                    st.bar_chart(perf_counts)
                with c_graf2:
                    taxa = (perf_counts.get("NO PRAZO", 0) / len(df_h) * 100) if len(df_h) > 0 else 0
                    st.metric("Taxa de Eficiência", f"{taxa:.1f}%")
                    st.write(f"Total: {len(df_h)} | ✅ No Prazo: {perf_counts.get('NO PRAZO', 0)} | ❌ Atraso: {perf_counts.get('ATRASADO', 0)}")
        except Exception as e: st.error(f"Erro nos indicadores: {e}")

    # --- ABA: AUDITORIA (MELHORIA SOLICITADA: FILTROS AVANÇADOS) ---
    elif menu == "🚨 Auditoria":
        st.header("🚨 Auditoria de Alterações")
        try:
            df_aud = conn.read(worksheet="Alteracoes", ttl="1m")
            # TRATAMENTO DE DATA PARA FILTRO
            df_aud['temp_date'] = pd.to_datetime(df_aud['Data'], format="%d/%m/%Y %H:%M", errors='coerce')
            df_aud = df_aud.sort_values(by='temp_date', ascending=False)
            
            # FILTROS AVANÇADOS
            with st.expander("🔍 Filtros de Auditoria", expanded=True):
                c1, c2, c3 = st.columns(3)
                f_ini = c1.date_input("De", value=date.today() - timedelta(days=7))
                f_fim = c2.date_input("Até", value=date.today())
                f_ctr = c3.multiselect("Filtrar CTR", sorted(df_aud['CTR'].dropna().unique()))
                
                c4, c5, c6 = st.columns(3)
                f_prazo = c4.multiselect("Impacto no Prazo", ["Sim", "Não"])
                f_finan = c5.multiselect("Impacto Financeiro", ["Sim", "Não"])
                f_dono = c6.multiselect("Dono (Gestor)", sorted(df_aud['Dono'].dropna().unique()))

            # APLICAÇÃO DOS FILTROS
            mask = (df_aud['temp_date'].dt.date >= f_ini) & (df_aud['temp_date'].dt.date <= f_fim)
            if f_ctr: mask &= df_aud['CTR'].isin(f_ctr)
            if f_prazo: mask &= df_aud['Impacto no Prazo'].isin(f_prazo)
            if f_finan: mask &= df_aud['Impacto Financeiro'].isin(f_finan)
            if f_dono: mask &= df_aud['Dono'].isin(f_dono)
            
            df_final_aud = df_aud[mask].drop(columns=['temp_date'])
            st.dataframe(df_final_aud, use_container_width=True)
            
        except Exception as e: st.error(f"Erro na auditoria: {e}")

    elif menu == "⚠️ Alteração de Pedido":
        st.header("🔄 Alteração de Pedido em Lote")
        if papel_usuario not in ["Gerência Geral", "PCP"]: st.error("Acesso negado.")
        else:
            try:
                df_p = df_global.copy()
                df_p['Data_Entrega_Str'] = pd.to_datetime(df_p['Data_Entrega'], errors='coerce').dt.strftime('%Y-%m-%d').fillna('')
                ctr_lista = [""] + sorted(df_p['CTR'].unique().tolist())
                ctr_sel = st.selectbox("Selecione a CTR para Alteração", ctr_lista, key="ctr_alteracao")
                if ctr_sel:
                    itens_da_ctr = df_p[df_p['CTR'] == ctr_sel]
                    selecionados = st.multiselect("Selecione os itens:", options=itens_da_ctr['ID_Item'].tolist(), format_func=lambda x: f"{itens_da_ctr[itens_da_ctr['ID_Item'] == x]['Pedido'].iloc[0]}", default=itens_da_ctr['ID_Item'].tolist())
                    if selecionados:
                        with st.form("form_alteracao_lote"):
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
                                    df_save = conn.read(worksheet="Pedidos", ttl=0)
                                    df_save.loc[df_save['ID_Item'].isin(selecionados), 'Dono'] = novo_gestor
                                    df_save.loc[df_save['ID_Item'].isin(selecionados), 'Data_Entrega'] = nova_data.strftime('%Y-%m-%d')
                                    df_save = df_save.drop_duplicates(subset=['ID_Item'], keep='first')
                                    conn.update(worksheet="Pedidos", data=df_save)
                                    st.cache_data.clear()
                                    df_alt = conn.read(worksheet="Alteracoes", ttl=0)
                                    
                                    # CAPTURA LOGS COM CAMPO DONO CORRETO
                                    logs = []
                                    for id_item in selecionados:
                                        item_nome = df_save[df_save['ID_Item'] == id_item]['Pedido'].iloc[0]
                                        logs.append({
                                            "Data": datetime.now().strftime("%d/%m/%Y %H:%M"), 
                                            "Pedido": item_nome, 
                                            "CTR": ctr_sel, 
                                            "Usuario": st.session_state.user_display, 
                                            "Dono": novo_gestor,
                                            "O que mudou": f"LOTE: Data {nova_data} / Gestor {novo_gestor}. Motivo: {motivo}", 
                                            "Impacto no Prazo": imp_prazo, 
                                            "Impacto Financeiro": imp_financeiro
                                        })
                                    conn.update(worksheet="Alteracoes", data=pd.concat([df_alt, pd.DataFrame(logs)], ignore_index=True))
                                    for id_item in selecionados:
                                        row_alt = df_save[df_save['ID_Item'] == id_item].iloc[0]
                                        salvar_no_supabase(id_item, row_alt['Status_Atual'], row_alt)
                                    st.success("✅ Pedido atualizado!")
                                    disparar_foguete(); time.sleep(1.5); st.rerun()
            except Exception as e: st.error(f"Erro: {e}")

    elif menu == "📥 Importar Itens (Sistema)":
        st.header("📥 Importar Itens da Marcenaria")
        if papel_usuario not in ["Gerência Geral", "PCP"]: st.error("Acesso negado.")
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
                            if str(uid) not in df_base['ID_Item'].astype(str).values:
                                payload_novo = {"ID_Item": uid, "CTR": r['Centro de custo'], "Obra": r['Obra'], "Item": r['Item'], "Pedido": r['Produto'], "Dono": r['Gestor'], "Status_Atual": "Aguardando Gate 1", "Data_Entrega": dt_limpa, "Quantidade": r['Quantidade'], "Unidade": r['Unidade']}
                                novos.append(payload_novo)
                        if novos: 
                            final_df = pd.concat([df_base, pd.DataFrame(novos)], ignore_index=True)
                            final_df = final_df.drop_duplicates(subset=['ID_Item'], keep='first')
                            conn.update(worksheet="Pedidos", data=final_df)
                            for n in novos:
                                salvar_no_supabase(n['ID_Item'], "Aguardando Gate 1", n)
                            st.success(f"✅ {len(novos)} novos itens importados!")
                        else: st.warning("⚠️ Nenhum item novo encontrado.")
                        st.cache_data.clear()
                except Exception as e: st.error(f"Erro na importação: {e}")

    elif menu == "⚙️ SINCRONIZAÇÃO SUPABASE":
        st.header("⚙️ Sincronização em Massa")
        if st.button("🚀 FORÇAR SINCRONIZAÇÃO GERAL"):
            for idx, row in df_global.iterrows():
                salvar_no_supabase(row['ID_Item'], row['Status_Atual'], row)
            st.success("Base do Supabase atualizada com sucesso!")

    elif menu == "🛠️ Recuperação de Pedidos":
        st.header("🛠️ Recuperação e Limpeza de Dados")
        if st.button("⚠️ EXECUTAR LIMPEZA DE DUPLICADOS NA PLANILHA ⚠️"):
            df_clean = conn.read(worksheet="Pedidos", ttl=0)
            df_clean = df_clean.drop_duplicates(subset=['ID_Item'], keep='first')
            conn.update(worksheet="Pedidos", data=df_clean)
            st.success("Limpeza concluída!")
            st.cache_data.clear(); st.rerun()
