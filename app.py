import streamlit as st
import pandas as pd
import sqlite3
import shutil
import os
from datetime import datetime

# --- Configuração da Página ---
st.set_page_config(page_title="Cantina Peixinho Dourado", layout="centered")

# --- Configuração do Banco de Dados (SQLite) ---
DB_FILE = 'cantina.db'

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabela de ALUNOS
    c.execute('''
        CREATE TABLE IF NOT EXISTS alunos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            serie TEXT,
            turma TEXT,
            turno TEXT,
            nascimento TEXT,
            email TEXT,
            telefone1 TEXT,
            telefone2 TEXT,
            telefone3 TEXT,
            saldo REAL
        )
    ''')
    try:
        c.execute("ALTER TABLE alunos ADD COLUMN telefone3 TEXT")
    except sqlite3.OperationalError:
        pass

    # 2. Tabela de ALIMENTOS
    c.execute('''
        CREATE TABLE IF NOT EXISTS alimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            valor REAL
        )
    ''')

    # 3. Tabela de TRANSAÇÕES
    c.execute('''
        CREATE TABLE IF NOT EXISTS transacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aluno_id INTEGER,
            itens TEXT,
            valor_total REAL,
            data_hora TEXT
        )
    ''')

    conn.commit()
    conn.close()

# --- FUNÇÕES DE BANCO DE DADOS (LEITURA) ---

def get_all_alunos():
    conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql_query("SELECT * FROM alunos", conn)
    except:
        df = pd.DataFrame()
    conn.close()
    return df

def get_alunos_por_turma(turma):
    conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql_query("SELECT * FROM alunos WHERE turma = ? ORDER BY nome ASC", conn, params=(turma,))
    except:
        df = pd.DataFrame()
    conn.close()
    return df

def update_saldo_aluno(aluno_id, novo_saldo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE alunos SET saldo = ? WHERE id = ?", (novo_saldo, aluno_id))
    conn.commit()
    conn.close()

def registrar_venda(aluno_id, itens_str, valor_total):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    data_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    c.execute("INSERT INTO transacoes (aluno_id, itens, valor_total, data_hora) VALUES (?, ?, ?, ?)",
              (aluno_id, itens_str, valor_total, data_hora))
    conn.commit()
    conn.close()

def get_vendas_hoje_turma(turma):
    conn = sqlite3.connect(DB_FILE)
    hoje = datetime.now().strftime("%d/%m/%Y")
    query = '''
        SELECT a.nome, t.itens, t.valor_total
        FROM transacoes t
        JOIN alunos a ON t.aluno_id = a.id
        WHERE a.turma = ? AND t.data_hora LIKE ?
        ORDER BY t.id DESC
    '''
    try:
        df = pd.read_sql_query(query, conn, params=(turma, f"{hoje}%"))
    except:
        df = pd.DataFrame()
    conn.close()
    return df

# --- FUNÇÕES DE GERENCIAMENTO (ALIMENTOS) ---
def add_alimento_db(nome, valor):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO alimentos (nome, valor) VALUES (?, ?)', (nome, valor))
    conn.commit()
    conn.close()

def update_alimento_db(id_alimento, nome, valor):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE alimentos SET nome=?, valor=? WHERE id=?', (nome, valor, id_alimento))
    conn.commit()
    conn.close()

def delete_alimento_db(id_alimento):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM alimentos WHERE id=?', (id_alimento,))
    conn.commit()
    conn.close()

def get_all_alimentos():
    conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql_query("SELECT * FROM alimentos", conn)
    except:
        df = pd.DataFrame()
    conn.close()
    return df

# --- FUNÇÕES DE GERENCIAMENTO (ALUNOS) ---
def upsert_aluno(nome, serie, turma, turno, nasck, email, tel1, tel2, tel3, saldo_inicial):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id FROM alunos WHERE nome = ?", (nome,))
    data = c.fetchone()
    action = ""
    if data:
        c.execute('''UPDATE alunos SET turma=?, email=?, telefone1=?, telefone2=?, telefone3=? WHERE nome=?''', 
                  (turma, email, tel1, tel2, tel3, nome))
        action = "atualizado"
    else:
        c.execute('''INSERT INTO alunos (nome, serie, turma, turno, nascimento, email, telefone1, telefone2, telefone3, saldo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                  (nome, serie, turma, turno, str(nasck), email, tel1, tel2, tel3, saldo_inicial))
        action = "novo"
    conn.commit()
    conn.close()
    return action

def update_aluno_manual(id_aluno, nome, serie, turma, turno, email, tel1, tel2, tel3, saldo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''UPDATE alunos SET nome=?, serie=?, turma=?, turno=?, email=?, telefone1=?, telefone2=?, telefone3=?, saldo=? WHERE id=?''', 
              (nome, serie, turma, turno, email, tel1, tel2, tel3, saldo, id_aluno))
    conn.commit()
    conn.close()

def delete_aluno_db(id_aluno):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM alunos WHERE id=?", (id_aluno,))
    conn.commit()
    conn.close()

def delete_turma_db(turma_nome):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM alunos WHERE turma=?", (turma_nome,))
    count = c.rowcount
    conn.commit()
    conn.close()
    return count

# Inicializa o banco
init_db()

# --- Estado de Login ---
if 'logado' not in st.session_state:
    st.session_state['logado'] = False

# --- Tela de Login ---
def login_screen():
    st.title("Cantina Escolar do Centro Educacional Peixinho Dourado")
    st.write("Acesso ao Sistema")
    
    usuario = st.text_input("Login")
    
    if st.button("Entrar"):
        if usuario == "fvilhena":
            st.session_state['logado'] = True
            st.rerun()
        else:
            st.error("Usuário não autorizado. Use: fvilhena")

# --- Menu Principal ---
def main_menu():
    # --- BARRA LATERAL ---
    st.sidebar.title("Menu")
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("💾 Backup")
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "rb") as fp:
            st.sidebar.download_button("⬇️ BAIXAR DADOS", fp, "backup_cantina.db", "application/x-sqlite3")
    
    uploaded_db = st.sidebar.file_uploader("⬆️ RESTAURAR", type=["db", "sqlite3"])
    if uploaded_db and st.sidebar.button("CONFIRMAR RESTAURAÇÃO"):
        with open(DB_FILE, "wb") as f:
            f.write(uploaded_db.getbuffer())
        st.sidebar.success("Restaurado!")
        st.rerun()
            
    st.sidebar.markdown("---")
    if st.sidebar.button("Sair"):
        st.session_state['logado'] = False
        st.session_state['menu_atual'] = None
        st.rerun()

    # --- HEADER ---
    st.header("Painel Principal")
    st.write("Usuário logado: fvilhena")
    
    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)

    with col1:
        if st.button("CADASTRO", use_container_width=True):
            st.session_state['menu_atual'] = 'cadastro'
            st.session_state['submenu'] = None
    with col2:
        if st.button("COMPRAR REFEIÇÃO", use_container_width=True):
            st.session_state['menu_atual'] = 'comprar'
            if 'modo_compra' not in st.session_state: st.session_state['modo_compra'] = None
            if 'turma_selecionada' not in st.session_state: st.session_state['turma_selecionada'] = None
            if 'aluno_compra_id' not in st.session_state: st.session_state['aluno_compra_id'] = None
            if 'resumo_turma' not in st.session_state: st.session_state['resumo_turma'] = False
    with col3:
        btn_saldo = st.button("SALDO/HISTÓRICO", use_container_width=True)
    with col4:
        btn_recarga = st.button("RECARGA", use_container_width=True)

    # ==========================================
    #       MENU: CADASTRO
    # ==========================================
    if st.session_state.get('menu_atual') == 'cadastro':
        st.markdown("---")
        st.subheader("Menu de Cadastro")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("USUÁRIO", use_container_width=True): st.session_state['submenu'] = 'usuario'
        with c2:
            if st.button("ALIMENTOS", use_container_width=True): st.session_state['submenu'] = 'alimentos'

        # SUBMENU ALIMENTOS
        if st.session_state.get('submenu') == 'alimentos':
            st.info("Gerenciar Cardápio")
            acao_alim = st.radio("Selecione a ação:", ["NOVO ALIMENTO", "ALTERAR ALIMENTO", "EXCLUIR ALIMENTO"], horizontal=True)
            st.markdown("---")
            df_ali = get_all_alimentos()

            if acao_alim == "NOVO ALIMENTO":
                st.write("📝 **Cadastrar Novo Item**")
                with st.form("form_novo_alimento"):
                    nome_p = st.text_input("Nome do Produto")
                    valor_p = st.number_input("Valor (R$)", min_value=0.00, step=0.50)
                    if st.form_submit_button("CADASTRAR"):
                        add_alimento_db(nome_p, valor_p)
                        st.success("Alimento cadastrado com sucesso!")
                        st.rerun()
                if not df_ali.empty:
                    st.write("Itens Cadastrados:")
                    st.dataframe(df_ali[['nome', 'valor']], hide_index=True)

            elif acao_alim == "ALTERAR ALIMENTO":
                if df_ali.empty:
                    st.warning("Nenhum alimento cadastrado.")
                else:
                    st.write("✏️ **Editar Item Existente**")
                    df_ali['label'] = df_ali['id'].astype(str) + " - " + df_ali['nome'] + " (R$ " + df_ali['valor'].astype(str) + ")"
                    esc_ali = st.selectbox("Selecione o Alimento:", df_ali['label'].unique())
                    id_ali = int(esc_ali.split(' - ')[0])
                    dados_ali = df_ali[df_ali['id'] == id_ali].iloc[0]
                    with st.form("form_alterar_ali"):
                        n_n = st.text_input("Nome", value=dados_ali['nome'])
                        n_v = st.number_input("Valor (R$)", value=float(dados_ali['valor']), step=0.50)
                        if st.form_submit_button("SALVAR ALTERAÇÕES"):
                            update_alimento_db(id_ali, n_n, n_v)
                            st.success("Alimento atualizado!")
                            st.rerun()

            elif acao_alim == "EXCLUIR ALIMENTO":
                if df_ali.empty:
                    st.warning("Nenhum alimento cadastrado.")
                else:
                    st.write("🗑️ **Remover Item do Cardápio**")
                    df_ali['label'] = df_ali['id'].astype(str) + " - " + df_ali['nome']
                    esc_ali = st.selectbox("Selecione para EXCLUIR:", df_ali['label'].unique())
                    id_ali = int(esc_ali.split(' - ')[0])
                    if st.button("❌ CONFIRMAR EXCLUSÃO"):
                        delete_alimento_db(id_ali)
                        st.success("Alimento removido com sucesso!")
                        st.rerun()

        # SUBMENU USUÁRIO
        if st.session_state.get('submenu') == 'usuario':
            st.info("Gerenciar Alunos e Turmas")
            opt = st.radio("Ação:", ["IMPORTAR CSV", "NOVO ALUNO", "ATUALIZAR ALUNO", "EXCLUIR ALUNO", "EXCLUIR TURMA"])
            st.markdown("---")

            if opt == "IMPORTAR CSV":
                st.write("📂 **Importação em Lote**")
                up_csv = st.file_uploader("Arquivo CSV", type=['csv'])
                if up_csv and st.button("ENVIAR"):
                    try:
                        df = pd.read_csv(up_csv, sep=None, engine='python', encoding='latin1')
                        for col in df.select_dtypes(include=['object']):
                            df[col] = df[col].astype(str).str.replace('1Â', '1o', regex=False)
                            df[col] = df[col].astype(str).str.replace('Ã¢', 'â', regex=False)
                            df[col] = df[col].astype(str).str.replace('Ãº', 'ú', regex=False)
                            df[col] = df[col].astype(str).str.replace('Ã£', 'ã', regex=False)
                            df[col] = df[col].astype(str).str.replace('Ã©', 'é', regex=False)
                            df[col] = df[col].astype(str).str.replace('Ã¡', 'á', regex=False)
                            df[col] = df[col].astype(str).str.replace('Ã³', 'ó', regex=False)
                            df[col] = df[col].astype(str).str.replace('Ã', 'í', regex=False)
                            df[col] = df[col].astype(str).str.replace('°', '', regex=False)
                        
                        novos, atua = 0, 0
                        bar = st.progress(0)
                        for i, r in df.iterrows():
                            t1, t2, t3 = None, None, None
                            if 'Telefones' in r and pd.notna(r['Telefones']):
                                ps = str(r['Telefones']).split(' / ')
                                if len(ps)>0: t1=ps[0]
                                if len(ps)>1: t2=ps[1]
                                if len(ps)>2: t3=ps[2]
                            nasc = None
                            if 'Data de Nascimento' in r and pd.notna(r['Data de Nascimento']):
                                try: nasc = pd.to_datetime(r['Data de Nascimento'], dayfirst=True).date()
                                except: pass
                            res = upsert_aluno(r.get('Aluno',''), '', r.get('Turma',''), '', nasc, r.get('E-mail',''), t1, t2, t3, 0.0)
                            if res == "novo": novos+=1
                            else: atua+=1
                            bar.progress((i+1)/len(df))
                        st.success(f"{novos} novos, {atua} atualizados.")
                    except Exception as e: st.error(f"Erro: {e}")
            
            elif opt == "NOVO ALUNO":
                st.write("👤 **Cadastro Manual**")
                with st.form("new_aluno"):
                    nm = st.text_input("Nome")
                    tr = st.text_input("Turma")
                    sl = st.number_input("Saldo Inicial", value=0.0)
                    if st.form_submit_button("SALVAR"):
                        upsert_aluno(nm, '', tr, '', None, '', None, None, None, sl)
                        st.success("Aluno salvo!")

            elif opt == "ATUALIZAR ALUNO":
                st.write("✏️ **Editar Cadastro**")
                df_al = get_all_alunos()
                if not df_al.empty:
                    df_al = df_al.sort_values(by='nome')
                    df_al['lbl'] = df_al['id'].astype(str) + " - " + df_al['nome']
                    sel = st.selectbox("Buscar Aluno:", df_al['lbl'].unique())
                    id_a = int(sel.split(' - ')[0])
                    d = df_al[df_al['id']==id_a].iloc[0]
                    with st.form("up_al"):
                        nn = st.text_input("Nome", value=d['nome'])
                        nt = st.text_input("Turma", value=d['turma'])
                        ns = st.number_input("Saldo", value=float(d['saldo']))
                        if st.form_submit_button("ATUALIZAR"):
                            update_aluno_manual(id_a, nn, d['serie'], nt, d['turno'], d['email'], d['telefone1'], d['telefone2'], d['telefone3'], ns)
                            st.success("Atualizado!")
                            st.rerun()
                else: st.warning("Sem alunos.")

            elif opt == "EXCLUIR ALUNO":
                st.write("🗑️ **Excluir Único Aluno**")
                df_al = get_all_alunos()
                if not df_al.empty:
                    df_al = df_al.sort_values(by='nome')
                    df_al['lbl'] = df_al['nome'] + " | " + df_al['turma'].astype(str) + " (ID: " + df_al['id'].astype(str) + ")"
                    sel_del = st.selectbox("Selecione o aluno para excluir:", df_al['lbl'].unique())
                    id_del = int(sel_del.split('(ID: ')[1].replace(')', ''))
                    st.error("Atenção: Esta ação não pode ser desfeita.")
                    if st.button(f"❌ CONFIRMAR EXCLUSÃO DO ALUNO"):
                        delete_aluno_db(id_del)
                        st.success("Aluno excluído.")
                        st.rerun()
                else: st.warning("Sem alunos cadastrados.")

            elif opt == "EXCLUIR TURMA":
                st.write("🔥 **Excluir Turma Inteira**")
                df_al = get_all_alunos()
                if not df_al.empty:
                    turmas = sorted(df_al['turma'].dropna().astype(str).unique())
                    turma_del = st.selectbox("Selecione a Turma para APAGAR:", turmas)
                    qtd_alunos = len(df_al[df_al['turma'] == turma_del])
                    st.warning(f"⚠️ CUIDADO: Você está prestes a apagar a turma '{turma_del}' inteira.")
                    st.write(f"Isso removerá **{qtd_alunos} alunos** do sistema.")
                    if st.button("🧨 APAGAR TODOS OS ALUNOS DA TURMA"):
                        count = delete_turma_db(turma_del)
                        st.success(f"Operação realizada. {count} alunos removidos.")
                        st.rerun()
                else: st.warning("Sem turmas cadastradas.")

    # ==========================================
    #       MENU: COMPRAR REFEIÇÃO
    # ==========================================
    if st.session_state.get('menu_atual') == 'comprar':
        st.markdown("---")
        st.subheader("🛒 Venda de Refeição")

        if st.session_state.get('modo_compra') is None:
            c_aluno, c_turma = st.columns(2)
            with c_aluno:
                if st.button("🔍 BUSCA POR ALUNO", use_container_width=True):
                    st.session_state['modo_compra'] = 'aluno'
            with c_turma:
                if st.button("🏫 BUSCA POR TURMA", use_container_width=True):
                    st.session_state['modo_compra'] = 'turma'
                    st.session_state['resumo_turma'] = False

        # --- MODO 1: ALUNO ---
        if st.session_state.get('modo_compra') == 'aluno':
            st.info("Modo: Venda Individual")
            if st.button("⬅️ Voltar"):
                st.session_state['modo_compra'] = None
                st.rerun()
            
            df_alunos = get_all_alunos()
            if not df_alunos.empty:
                df_alunos = df_alunos.sort_values(by='nome')
                df_alunos['lbl'] = df_alunos['nome'] + " | Turma: " + df_alunos['turma'].astype(str)
                aluno_sel = st.selectbox("Selecione o Aluno:", df_alunos['lbl'].unique())
                idx = int(df_alunos[df_alunos['lbl'] == aluno_sel].iloc[0]['id'])
                realizar_venda_form(idx)
            else:
                st.warning("Nenhum aluno cadastrado.")

        # --- MODO 2: TURMA (COM TABELA) ---
        elif st.session_state.get('modo_compra') == 'turma':
            
            if st.session_state.get('turma_selecionada') is None:
                st.info("Modo: Venda por Turma")
                if st.button("⬅️ Voltar"):
                    st.session_state['modo_compra'] = None
                    st.rerun()
                
                df_alunos = get_all_alunos()
                if not df_alunos.empty:
                    turmas = sorted(df_alunos['turma'].dropna().astype(str).unique())
                    turma_escolhida = st.selectbox("Selecione a Turma:", turmas)
                    if st.button("ABRIR TURMA"):
                        st.session_state['turma_selecionada'] = turma_escolhida
                        st.session_state['resumo_turma'] = False
                        st.rerun()
                else: st.warning("Sem alunos cadastrados.")

            else:
                turma_atual = st.session_state['turma_selecionada']
                
                if st.session_state.get('resumo_turma'):
                    st.markdown(f"### 📋 Conferência: {turma_atual}")
                    st.info("Confira as vendas realizadas HOJE para esta turma antes de encerrar.")
                    df_vendas = get_vendas_hoje_turma(turma_atual)
                    if not df_vendas.empty:
                        st.dataframe(
                            df_vendas.rename(columns={'nome': 'Aluno', 'itens': 'Alimentos', 'valor_total': 'Valor (R$)'}),
                            hide_index=True,
                            use_container_width=True
                        )
                        total_dia = df_vendas['valor_total'].sum()
                        st.markdown(f"**Total da Turma Hoje: R$ {total_dia:.2f}**")
                    else: st.warning("Nenhuma venda registrada para esta turma hoje.")
                    
                    st.markdown("---")
                    col_conf, col_canc = st.columns(2)
                    with col_conf:
                        if st.button("✅ CONFIRMAR E FECHAR TURMA", type="primary"):
                            st.session_state['turma_selecionada'] = None
                            st.session_state['aluno_compra_id'] = None
                            st.session_state['resumo_turma'] = False
                            st.session_state['modo_compra'] = None
                            st.success("Turma encerrada com sucesso!")
                            st.rerun()
                    with col_canc:
                        if st.button("⬅️ Voltar para Vendas"):
                            st.session_state['resumo_turma'] = False
                            st.rerun()

                else:
                    # CABEÇALHO DA TURMA
                    c_head, c_btn = st.columns([3, 1])
                    with c_head: st.markdown(f"### 🏫 Turma: {turma_atual}")
                    with c_btn:
                        if st.button("🏁 ENCERRAR VENDAS DA TURMA", type="primary"):
                            st.session_state['resumo_turma'] = True
                            st.rerun()
                    
                    if st.session_state.get('aluno_compra_id') is None:
                        st.write("Selecione o aluno na lista abaixo:")
                        df_turma = get_alunos_por_turma(turma_atual)
                        
                        # --- TABELA DE ALUNOS (NOVO FORMATO) ---
                        # Cabeçalho da Tabela
                        h1, h2, h3 = st.columns([3, 1, 1])
                        h1.markdown("**Nome do Aluno**")
                        h2.markdown("**Saldo**")
                        h3.markdown("**Ação**")
                        st.markdown("<hr style='margin: 0px 0px 10px 0px;'>", unsafe_allow_html=True)
                        
                        # Linhas da Tabela
                        for index, row in df_turma.iterrows():
                            r1, r2, r3 = st.columns([3, 1, 1])
                            
                            # Nome
                            r1.write(f"{row['nome']}")
                            
                            # Saldo Colorido
                            cor = "green" if row['saldo'] >= 0 else "red"
                            r2.markdown(f"<span style='color:{cor}; font-weight:bold'>R$ {row['saldo']:.2f}</span>", unsafe_allow_html=True)
                            
                            # Botão de Seleção
                            if r3.button("VENDER", key=f"sel_{row['id']}"):
                                st.session_state['aluno_compra_id'] = row['id']
                                st.rerun()
                            
                            # Divisor sutil
                            st.markdown("<hr style='margin: 5px 0px; border-top: 1px dotted #eee;'>", unsafe_allow_html=True)

                    else:
                        id_aluno_compra = st.session_state['aluno_compra_id']
                        if st.button("⬅️ Cancelar e voltar para lista"):
                            st.session_state['aluno_compra_id'] = None
                            st.rerun()
                        realizar_venda_form(id_aluno_compra, modo_turma=True)

# --- AUXILIAR VENDA ---
def realizar_venda_form(aluno_id, modo_turma=False):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row 
    c = conn.cursor()
    c.execute("SELECT * FROM alunos WHERE id = ?", (aluno_id,))
    aluno = c.fetchone() 
    conn.close()
    
    if not aluno:
        st.error("Erro: Aluno não encontrado. Tente atualizar.")
        return

    saldo_atual = aluno['saldo']
    nome_aluno = aluno['nome']
    
    st.markdown(f"""
    <div style="padding:10px; background-color:#f0f2f6; border-radius:5px; margin-bottom:10px;">
        <h4>👤 {nome_aluno}</h4>
        <h2 style="color:{'green' if saldo_atual >=0 else 'red'}">Saldo: R$ {saldo_atual:.2f}</h2>
    </div>
    """, unsafe_allow_html=True)
    
    df_alimentos = get_all_alimentos()
    
    if df_alimentos.empty:
        st.warning("Cadastre alimentos primeiro!")
        return

    with st.form("form_venda_final"):
        col_header = st.columns([3, 1, 1])
        col_header[0].write("**Produto**")
        col_header[1].write("**Preço**")
        col_header[2].write("**Qtd**")
        
        quantidades = {}
        
        for index, row in df_alimentos.iterrows():
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.write(row['nome'])
            c2.write(f"R$ {row['valor']:.2f}")
            quantidades[row['id']] = c3.number_input(
                "Qtd", min_value=0, step=1, key=f"qtd_{row['id']}", label_visibility="collapsed"
            )
            st.markdown("<hr style='margin: 0px 0px 10px 0px; border-top: 1px dotted #bbb;'>", unsafe_allow_html=True)

        if st.form_submit_button("✅ CONFIRMAR E CALCULAR", type="primary"):
            total_compra = 0.0
            itens_comprados = []
            
            for prod_id, qtd in quantidades.items():
                if qtd > 0:
                    item = df_alimentos[df_alimentos['id'] == prod_id].iloc[0]
                    subtotal = item['valor'] * qtd
                    total_compra += subtotal
                    itens_comprados.append(f"{qtd}x {item['nome']}")

            if total_compra > 0:
                saldo_final = saldo_atual - total_compra
                update_saldo_aluno(aluno_id, saldo_final)
                registrar_venda(aluno_id, ", ".join(itens_comprados), total_compra)
                st.success(f"Venda de R$ {total_compra:.2f} realizada! Novo saldo: R$ {saldo_final:.2f}")
                
                if modo_turma: st.session_state['aluno_compra_id'] = None
                st.rerun()
            else:
                st.warning("Selecione pelo menos 1 item.")

# --- RUN ---
if st.session_state['logado']:
    main_menu()
else:
    login_screen()
