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

# --- FUNÇÕES DE BANCO DE DADOS ---

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

def get_aluno_by_id(aluno_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM alunos WHERE id = ?", (aluno_id,))
    data = c.fetchone()
    conn.close()
    return data

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

# --- Funções Alimentos e Upsert ---
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
            st.session_state['modo_compra'] = None
            st.session_state['turma_selecionada'] = None
            st.session_state['aluno_compra_id'] = None
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
            st.info("Cadastro de Produtos / Cardápio")
            with st.expander("➕ Adicionar Novo Item"):
                with st.form("form_novo_alimento"):
                    nome_p = st.text_input("Nome")
                    valor_p = st.number_input("Valor", min_value=0.00, step=0.50)
                    if st.form_submit_button("CADASTRAR"):
                        add_alimento_db(nome_p, valor_p)
                        st.success("Cadastrado!")
                        st.rerun()
            
            st.markdown("### Cardápio Atual")
            df_ali = get_all_alimentos()
            if not df_ali.empty:
                df_ali['label'] = df_ali['id'].astype(str) + " - " + df_ali['nome'] + " (R$ " + df_ali['valor'].astype(str) + ")"
                esc_ali = st.selectbox("Editar/Excluir:", df_ali['label'].unique())
                id_ali = int(esc_ali.split(' - ')[0])
                dados_ali = df_ali[df_ali['id'] == id_ali].iloc[0]
                
                with st.form("edit_ali"):
                    n_n = st.text_input("Nome", value=dados_ali['nome'])
                    n_v = st.number_input("Valor", value=float(dados_ali['valor']))
                    c_s, c_d = st.columns(2)
                    if c_s.form_submit_button("SALVAR"):
                        update_alimento_db(id_ali, n_n, n_v)
                        st.rerun()
                    if c_d.form_submit_button("EXCLUIR"):
                        delete_alimento_db(id_ali)
                        st.rerun()

        # SUBMENU USUÁRIO
        if st.session_state.get('submenu') == 'usuario':
            opt = st.radio("Ação:", ["IMPORTAR CSV", "NOVO ALUNO", "ATUALIZAR ALUNO"])
            if opt == "IMPORTAR CSV":
                up_csv = st.file_uploader("Arquivo CSV", type=['csv'])
                if up_csv and st.button("ENVIAR"):
                    try:
                        df = pd.read_csv(up_csv, sep=None, engine='python', encoding='latin1')
                        
                        # --- LIMPEZA DE CARACTERES ESTRANHOS ---
                        # Corrige nomes como VenÃ¢ncio (â) e AraÃºjo (ú)
                        for col in df.select_dtypes(include=['object']):
                            # 1. Â -> o (para 1º ano)
                            df[col] = df[col].astype(str).str.replace('1Â', '1o', regex=False)
                            # 2. Corrige UTF-8 mal interpretado (Mojibake)
                            df[col] = df[col].astype(str).str.replace('Ã¢', 'â', regex=False) # ex: Venâncio
                            df[col] = df[col].astype(str).str.replace('Ãº', 'ú', regex=False) # ex: Araújo
                            df[col] = df[col].astype(str).str.replace('Ã£', 'ã', regex=False) # ex: Irmão
                            df[col] = df[col].astype(str).str.replace('Ã©', 'é', regex=False) # ex: José
                            df[col] = df[col].astype(str).str.replace('Ã¡', 'á', regex=False) 
                            df[col] = df[col].astype(str).str.replace('Ã³', 'ó', regex=False)
                            df[col] = df[col].astype(str).str.replace('Ã', 'í', regex=False)  # as vezes í aparece só como Ã
                            # 3. Limpeza final do grau
                            df[col] = df[col].astype(str).str.replace('°', '', regex=False)
                        # ----------------------------------------
                        
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
                with st.form("new_aluno"):
                    nm = st.text_input("Nome")
                    tr = st.text_input("Turma")
                    sl = st.number_input("Saldo", value=0.0)
                    if st.form_submit_button("SALVAR"):
                        upsert_aluno(nm, '', tr, '', None, '', None, None, None, sl)
                        st.success("Salvo!")

            elif opt == "ATUALIZAR ALUNO":
                df_al = get_all_alunos()
                if not df_al.empty:
                    df_al = df_al.sort_values(by='nome')
                    df_al['lbl'] = df_al['id'].astype(str) + " - " + df_al['nome']
                    sel = st.selectbox("Aluno:", df_al['lbl'].unique())
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
                idx = df_alunos[df_alunos['lbl'] == aluno_sel].iloc[0]['id']
                realizar_venda_form(idx)
            else:
                st.warning("Nenhum aluno cadastrado.")

        # --- MODO 2: TURMA ---
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
                        st.rerun()
                else:
                    st.warning("Sem alunos cadastrados.")

            else:
                turma_atual = st.session_state['turma_selecionada']
                c_head, c_btn = st.columns([3, 1])
                with c_head: st.markdown(f"### 🏫 Turma: {turma_atual}")
                with c_btn:
                    if st.button("❌ ENCERRAR VENDAS DA TURMA", type="primary"):
                        st.session_state['turma_selecionada'] = None
                        st.session_state['aluno_compra_id'] = None
                        st.rerun()
                
                if st.session_state.get('aluno_compra_id') is None:
                    st.write("Selecione o aluno para iniciar a venda:")
                    df_turma = get_alunos_por_turma(turma_atual)
                    
                    cols = st.columns(2)
                    for i, (index, row) in enumerate(df_turma.iterrows()):
                        label_btn = f"{row['nome']} (R$ {row['saldo']:.2f})"
                        with cols[i % 2]:
                            if st.button(label_btn, key=f"btn_{row['id']}", use_container_width=True):
                                st.session_state['aluno_compra_id'] = row['id']
                                st.rerun()
                else:
                    id_aluno_compra = st.session_state['aluno_compra_id']
                    if st.button("⬅️ Cancelar e voltar para lista"):
                        st.session_state['aluno_compra_id'] = None
                        st.rerun()
                    realizar_venda_form(id_aluno_compra, modo_turma=True)

# --- AUXILIAR VENDA (ATUALIZADA: TABELA COM QUANTIDADE) ---
def realizar_venda_form(aluno_id, modo_turma=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM alunos WHERE id = ?", (aluno_id,))
    aluno = c.fetchone() 
    conn.close()
    
    saldo_atual = aluno[10]
    nome_aluno = aluno[1]
    
    st.markdown(f"""
    <div style="padding:10px; background-color:#f0f2f6; border-radius:5px;">
        <h4>👤 {nome_aluno}</h4>
        <h2 style="color:{'green' if saldo_atual >=0 else 'red'}">Saldo: R$ {saldo_atual:.2f}</h2>
    </div>
    """, unsafe_allow_html=True)
    
    st.write("")
    st.write("📦 **Selecione os itens e quantidades:**")
    df_alimentos = get_all_alimentos()
    
    if df_alimentos.empty:
        st.warning("Cadastre alimentos primeiro!")
        return

    # --- TABELA DE SELEÇÃO DE ITENS (NOVA LÓGICA) ---
    with st.form("form_venda_final"):
        col_header = st.columns([3, 1, 1])
        col_header[0].write("**Produto**")
        col_header[1].write("**Preço**")
        col_header[2].write("**Qtd**")
        
        # Dicionário para armazenar quantidades
        quantidades = {}
        
        # Itera sobre produtos e cria inputs
        for index, row in df_alimentos.iterrows():
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.write(row['nome'])
            c2.write(f"R$ {row['valor']:.2f}")
            # Input numérico para quantidade (começa em 0)
            quantidades[row['id']] = c3.number_input(
                "Qtd", 
                min_value=0, 
                step=1, 
                key=f"qtd_{row['id']}", 
                label_visibility="collapsed"
            )
            st.markdown("<hr style='margin: 0px 0px 10px 0px; border-top: 1px dotted #bbb;'>", unsafe_allow_html=True)

        if st.form_submit_button("✅ CONFIRMAR E CALCULAR", type="primary"):
            total_compra = 0.0
            itens_comprados = []
            
            # Calcula total varrendo as quantidades preenchidas
            for prod_id, qtd in quantidades.items():
                if qtd > 0:
                    # Acha o produto original
                    item = df_alimentos[df_alimentos['id'] == prod_id].iloc[0]
                    subtotal = item['valor'] * qtd
                    total_compra += subtotal
                    itens_comprados.append(f"{qtd}x {item['nome']}")

            if total_compra > 0:
                saldo_final = saldo_atual - total_compra
                
                # Executa venda
                update_saldo_aluno(aluno_id, saldo_final)
                registrar_venda(aluno_id, ", ".join(itens_comprados), total_compra)
                
                st.success(f"Venda de R$ {total_compra:.2f} realizada! Novo saldo: R$ {saldo_final:.2f}")
                
                # Reseta estado se necessário
                if modo_turma: st.session_state['aluno_compra_id'] = None
                st.rerun()
            else:
                st.warning("Selecione pelo menos 1 item.")

# --- RUN ---
if st.session_state['logado']:
    main_menu()
else:
    login_screen()
