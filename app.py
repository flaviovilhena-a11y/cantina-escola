import streamlit as st
import pandas as pd
import sqlite3
import shutil
import os
from datetime import datetime, timedelta
from collections import Counter

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
            valor REAL,
            tipo TEXT
        )
    ''')
    try:
        c.execute("ALTER TABLE alimentos ADD COLUMN tipo TEXT")
        c.execute("UPDATE alimentos SET tipo = 'ALIMENTO' WHERE tipo IS NULL")
    except sqlite3.OperationalError:
        pass

    # 3. Tabela de TRANSAÇÕES (VENDAS)
    c.execute('''
        CREATE TABLE IF NOT EXISTS transacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aluno_id INTEGER,
            itens TEXT,
            valor_total REAL,
            data_hora TEXT
        )
    ''')

    # 4. Tabela de RECARGAS (CRÉDITOS)
    c.execute('''
        CREATE TABLE IF NOT EXISTS recargas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aluno_id INTEGER,
            valor REAL,
            data_hora TEXT,
            metodo_pagamento TEXT
        )
    ''')
    
    # Migração para garantir coluna metodo_pagamento
    try:
        c.execute("ALTER TABLE recargas ADD COLUMN metodo_pagamento TEXT")
    except sqlite3.OperationalError:
        pass

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

# --- NOVA FUNÇÃO: REGISTRAR RECARGA ---
def registrar_recarga(aluno_id, valor, metodo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    data_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    # 1. Registra no histórico de recargas
    c.execute("INSERT INTO recargas (aluno_id, valor, data_hora, metodo_pagamento) VALUES (?, ?, ?, ?)",
              (aluno_id, valor, data_hora, metodo))
    
    # 2. Atualiza o saldo do aluno (Crédito)
    # Busca saldo atual primeiro para garantir
    c.execute("SELECT saldo FROM alunos WHERE id = ?", (aluno_id,))
    saldo_atual = c.fetchone()[0]
    novo_saldo = saldo_atual + valor
    
    c.execute("UPDATE alunos SET saldo = ? WHERE id = ?", (novo_saldo, aluno_id))
    
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

def get_historico_preferencias(aluno_id):
    conn = sqlite3.connect(DB_FILE)
    query = "SELECT itens FROM transacoes WHERE aluno_id = ? ORDER BY id DESC LIMIT 10"
    cursor = conn.cursor()
    cursor.execute(query, (aluno_id,))
    rows = cursor.fetchall()
    conn.close()

    contador = Counter()
    for row in rows:
        itens_str = row[0]
        if itens_str:
            lista_itens = itens_str.split(", ")
            for item in lista_itens:
                try:
                    parts = item.split("x ")
                    if len(parts) == 2:
                        qtd = int(parts[0])
                        nome_produto = parts[1]
                        contador[nome_produto] += qtd
                except:
                    continue
    return contador

# --- FUNÇÃO DE EXTRATO UNIFICADO ---
def get_extrato_aluno(aluno_id, dias_filtro):
    conn = sqlite3.connect(DB_FILE)
    
    data_corte = None
    if dias_filtro != 'TODOS':
        hoje = datetime.now()
        delta = timedelta(days=int(dias_filtro))
        data_corte = hoje - delta

    # 1. Busca Vendas
    q_vendas = "SELECT data_hora, itens, valor_total FROM transacoes WHERE aluno_id = ?"
    cursor = conn.cursor()
    cursor.execute(q_vendas, (aluno_id,))
    vendas = cursor.fetchall()
    
    # 2. Busca Recargas (Agora com Metodo)
    q_recargas = "SELECT data_hora, valor, metodo_pagamento FROM recargas WHERE aluno_id = ?"
    cursor.execute(q_recargas, (aluno_id,))
    recargas = cursor.fetchall()
    conn.close()

    extrato = []

    # Processa Vendas
    for v in vendas:
        dt_obj = datetime.strptime(v[0], "%d/%m/%Y %H:%M:%S")
        if data_corte and dt_obj < data_corte:
            continue
        extrato.append({
            "Data": dt_obj,
            "Tipo": "COMPRA",
            "Descrição": v[1],
            "Valor": -v[2] # Negativo
        })

    # Processa Recargas
    for r in recargas:
        dt_obj = datetime.strptime(r[0], "%d/%m/%Y %H:%M:%S")
        if data_corte and dt_obj < data_corte:
            continue
        metodo = r[2] if r[2] else "Crédito"
        extrato.append({
            "Data": dt_obj,
            "Tipo": "RECARGA",
            "Descrição": f"Recarga via {metodo}",
            "Valor": r[1] # Positivo
        })

    if extrato:
        df = pd.DataFrame(extrato)
        df = df.sort_values(by="Data", ascending=False)
        df['Data'] = df['Data'].apply(lambda x: x.strftime("%d/%m/%Y %H:%M"))
        return df
    else:
        return pd.DataFrame()

# --- FUNÇÕES ALIMENTOS E ALUNOS (CADASTRO) ---
def add_alimento_db(nome, valor, tipo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO alimentos (nome, valor, tipo) VALUES (?, ?, ?)', (nome, valor, tipo))
    conn.commit()
    conn.close()

def update_alimento_db(id_alimento, nome, valor, tipo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE alimentos SET nome=?, valor=?, tipo=? WHERE id=?', (nome, valor, tipo, id_alimento))
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
        if st.button("SALDO/HISTÓRICO", use_container_width=True):
            st.session_state['menu_atual'] = 'historico'
            st.session_state['hist_aluno_id'] = None
    with col4:
        if st.button("RECARGA", use_container_width=True):
            st.session_state['menu_atual'] = 'recarga'
            st.session_state['modo_recarga'] = None # 'manual' ou 'pix'

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
                    tipo_p = st.selectbox("Tipo do Produto", ["ALIMENTO", "BEBIDA"])
                    if st.form_submit_button("CADASTRAR"):
                        add_alimento_db(nome_p, valor_p, tipo_p)
                        st.success("Cadastrado!")
                        st.rerun()
                if not df_ali.empty:
                    st.write("Itens Cadastrados:")
                    st.dataframe(df_ali[['nome', 'valor', 'tipo']], hide_index=True)

            elif acao_alim == "ALTERAR ALIMENTO":
                if df_ali.empty:
                    st.warning("Sem alimentos.")
                else:
                    st.write("✏️ **Editar Item**")
                    df_ali['label'] = df_ali['id'].astype(str) + " - " + df_ali['nome'] + " (R$ " + df_ali['valor'].astype(str) + ")"
                    esc_ali = st.selectbox("Selecione:", df_ali['label'].unique())
                    id_ali = int(esc_ali.split(' - ')[0])
                    dados_ali = df_ali[df_ali['id'] == id_ali].iloc[0]
                    with st.form("form_alterar_ali"):
                        n_n = st.text_input("Nome", value=dados_ali['nome'])
                        n_v = st.number_input("Valor (R$)", value=float(dados_ali['valor']), step=0.50)
                        tipo_atual = dados_ali['tipo'] if 'tipo' in dados_ali and dados_ali['tipo'] in ["ALIMENTO", "BEBIDA"] else "ALIMENTO"
                        idx_tipo = ["ALIMENTO", "BEBIDA"].index(tipo_atual)
                        n_t = st.selectbox("Tipo", ["ALIMENTO", "BEBIDA"], index=idx_tipo)
                        if st.form_submit_button("SALVAR"):
                            update_alimento_db(id_ali, n_n, n_v, n_t)
                            st.success("Atualizado!")
                            st.rerun()

            elif acao_alim == "EXCLUIR ALIMENTO":
                if df_ali.empty:
                    st.warning("Sem alimentos.")
                else:
                    st.write("🗑️ **Remover Item**")
                    df_ali['label'] = df_ali['id'].astype(str) + " - " + df_ali['nome']
                    esc_ali = st.selectbox("Selecione para EXCLUIR:", df_ali['label'].unique())
                    id_ali = int(esc_ali.split(' - ')[0])
                    if st.button("❌ CONFIRMAR EXCLUSÃO"):
                        delete_alimento_db(id_ali)
                        st.success("Removido!")
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
                        st.success("Salvo!")

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
                    sel_del = st.selectbox("Selecione o aluno:", df_al['lbl'].unique())
                    id_del = int(sel_del.split('(ID: ')[1].replace(')', ''))
                    st.error("Atenção: Ação irreversível.")
                    if st.button(f"❌ CONFIRMAR EXCLUSÃO"):
                        delete_aluno_db(id_del)
                        st.success("Excluído.")
                        st.rerun()
                else: st.warning("Sem alunos.")

            elif opt == "EXCLUIR TURMA":
                st.write("🔥 **Excluir Turma Inteira**")
                df_al = get_all_alunos()
                if not df_al.empty:
                    turmas = sorted(df_al['turma'].dropna().astype(str).unique())
                    turma_del = st.selectbox("Selecione a Turma:", turmas)
                    qtd = len(df_al[df_al['turma'] == turma_del])
                    st.warning(f"Isso removerá **{qtd} alunos**.")
                    if st.button("🧨 APAGAR TURMA"):
                        count = delete_turma_db(turma_del)
                        st.success(f"{count} alunos removidos.")
                        st.rerun()
                else: st.warning("Sem turmas.")

    # ==========================================
    #       MENU: RECARGA (NOVO)
    # ==========================================
    if st.session_state.get('menu_atual') == 'recarga':
        st.markdown("---")
        st.subheader("💰 Recarga de Créditos")

        c_man, c_pix = st.columns(2)
        with c_man:
            if st.button("📝 MANUAL (Dinheiro/Cartão)", use_container_width=True):
                st.session_state['modo_recarga'] = 'manual'
        with c_pix:
            if st.button("💠 PIX (QR CODE)", use_container_width=True):
                st.session_state['modo_recarga'] = 'pix'

        # --- MODO MANUAL ---
        if st.session_state.get('modo_recarga') == 'manual':
            st.info("Modo: Recarga Manual")
            df_alunos = get_all_alunos()
            if not df_alunos.empty:
                df_alunos = df_alunos.sort_values(by='nome')
                df_alunos['lbl'] = df_alunos['nome'] + " | Turma: " + df_alunos['turma'].astype(str)
                aluno_sel = st.selectbox("Selecione o Aluno:", df_alunos['lbl'].unique())
                
                # Extrai ID
                id_aluno = int(df_alunos[df_alunos['lbl'] == aluno_sel].iloc[0]['id'])
                
                with st.form("form_recarga_manual"):
                    val_recarga = st.number_input("Valor da Recarga (R$)", min_value=0.0, step=5.0)
                    metodo = st.selectbox("Forma de Pagamento", ["DINHEIRO", "PIX", "CARTÃO DE CRÉDITO", "CARTÃO DE DÉBITO"])
                    
                    if st.form_submit_button("✅ CONFIRMAR RECARGA"):
                        if val_recarga > 0:
                            registrar_recarga(id_aluno, val_recarga, metodo)
                            st.success(f"Recarga de R$ {val_recarga:.2f} realizada com sucesso!")
                        else:
                            st.warning("O valor deve ser maior que zero.")
            else:
                st.warning("Nenhum aluno cadastrado.")

        # --- MODO PIX (QR CODE) ---
        elif st.session_state.get('modo_recarga') == 'pix':
            st.info("Modo: Pix QR Code")
            df_alunos = get_all_alunos()
            if not df_alunos.empty:
                df_alunos = df_alunos.sort_values(by='nome')
                df_alunos['lbl'] = df_alunos['nome'] + " | Turma: " + df_alunos['turma'].astype(str)
                aluno_sel = st.selectbox("Selecione o Aluno:", df_alunos['lbl'].unique())
                id_aluno = int(df_alunos[df_alunos['lbl'] == aluno_sel].iloc[0]['id'])
                
                val_pix = st.number_input("Valor a pagar (R$)", min_value=0.0, step=5.0)
                
                if val_pix > 0:
                    # Simulação de QR Code
                    st.markdown("### Escaneie para pagar:")
                    # Utiliza API do Google Charts para gerar QR visualmente (Apenas visual, sem integração bancária real)
                    # Você pode colocar sua chave pix aqui
                    chave_pix = "sua_chave_pix_aqui" 
                    qr_data = f"00020126330014BR.GOV.BCB.PIX0111{chave_pix}520400005303986540{val_pix:.2f}5802BR5913CANTINA6006MANAUS62070503***6304"
                    
                    st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=PagamentoCantinaValor{val_pix}", caption="QR Code Ilustrativo")
                    st.write(f"Valor: **R$ {val_pix:.2f}**")
                    
                    if st.button("✅ CONFIRMAR RECEBIMENTO (PIX)"):
                        registrar_recarga(id_aluno, val_pix, "PIX (QR)")
                        st.success(f"Pagamento Pix de R$ {val_pix:.2f} confirmado!")
            else:
                st.warning("Nenhum aluno cadastrado.")

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
                    c_head, c_btn = st.columns([3, 1])
                    with c_head: st.markdown(f"### 🏫 Turma: {turma_atual}")
                    with c_btn:
                        if st.button("🏁 ENCERRAR VENDAS DA TURMA", type="primary"):
                            st.session_state['resumo_turma'] = True
                            st.rerun()
                    
                    if st.session_state.get('aluno_compra_id') is None:
                        st.write("Selecione o aluno na lista abaixo:")
                        df_turma = get_alunos_por_turma(turma_atual)
                        h1, h2, h3 = st.columns([3, 1, 1])
                        h1.markdown("**Nome do Aluno**")
                        h2.markdown("**Saldo**")
                        h3.markdown("**Ação**")
                        st.markdown("<hr style='margin: 0px 0px 10px 0px;'>", unsafe_allow_html=True)
                        for index, row in df_turma.iterrows():
                            r1, r2, r3 = st.columns([3, 1, 1])
                            r1.write(f"{row['nome']}")
                            cor = "green" if row['saldo'] >= 0 else "red"
                            r2.markdown(f"<span style='color:{cor}; font-weight:bold'>R$ {row['saldo']:.2f}</span>", unsafe_allow_html=True)
                            if r3.button("VENDER", key=f"sel_{row['id']}"):
                                st.session_state['aluno_compra_id'] = row['id']
                                st.rerun()
                            st.markdown("<hr style='margin: 5px 0px; border-top: 1px dotted #eee;'>", unsafe_allow_html=True)
                    else:
                        id_aluno_compra = st.session_state['aluno_compra_id']
                        if st.button("⬅️ Cancelar e voltar para lista"):
                            st.session_state['aluno_compra_id'] = None
                            st.rerun()
                        realizar_venda_form(id_aluno_compra, modo_turma=True)

    # ==========================================
    #       MENU: SALDO / HISTÓRICO
    # ==========================================
    if st.session_state.get('menu_atual') == 'historico':
        st.markdown("---")
        st.subheader("📜 Extrato e Histórico")

        # Seleção de Aluno
        if st.session_state.get('hist_aluno_id') is None:
            df_alunos = get_all_alunos()
            if not df_alunos.empty:
                df_alunos = df_alunos.sort_values(by='nome')
                df_alunos['lbl'] = df_alunos['nome'] + " | Turma: " + df_alunos['turma'].astype(str)
                sel = st.selectbox("Selecione o Aluno para ver o Extrato:", df_alunos['lbl'].unique())
                if st.button("VER SALDO E EXTRATO"):
                    st.session_state['hist_aluno_id'] = int(df_alunos[df_alunos['lbl'] == sel].iloc[0]['id'])
                    st.rerun()
            else:
                st.warning("Sem alunos cadastrados.")
        else:
            if st.button("⬅️ Trocar Aluno"):
                st.session_state['hist_aluno_id'] = None
                st.rerun()

            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM alunos WHERE id = ?", (st.session_state['hist_aluno_id'],))
            aluno = c.fetchone()
            conn.close()

            cor_saldo = "green" if aluno['saldo'] >= 0 else "red"
            st.markdown(f"""
                <div style="padding: 20px; background-color: #f0f2f6; border-radius: 10px; text-align: center; margin-bottom: 20px;">
                    <h3>Aluno: {aluno['nome']}</h3>
                    <p style="font-size: 18px;">Saldo Atual em Conta</p>
                    <h1 style="color: {cor_saldo}; font-size: 48px; margin: 0;">R$ {aluno['saldo']:.2f}</h1>
                </div>
            """, unsafe_allow_html=True)

            st.write("### Histórico de Movimentações")
            filtro = st.selectbox("Período:", ["ÚLTIMOS 7 DIAS", "ÚLTIMOS 30 DIAS", "ÚLTIMOS 60 DIAS", "TODO O HISTÓRICO DISPONÍVEL"])
            
            mapa_dias = {
                "ÚLTIMOS 7 DIAS": 7,
                "ÚLTIMOS 30 DIAS": 30,
                "ÚLTIMOS 60 DIAS": 60,
                "TODO O HISTÓRICO DISPONÍVEL": "TODOS"
            }
            dias_selecionados = mapa_dias[filtro]

            if st.button("EXIBIR HISTÓRICO", type="primary", use_container_width=True):
                df_extrato = get_extrato_aluno(aluno['id'], dias_selecionados)
                
                if not df_extrato.empty:
                    def highlight_vals(val):
                        color = 'red' if val < 0 else 'green'
                        return f'color: {color}; font-weight: bold'

                    st.dataframe(
                        df_extrato.style.map(highlight_vals, subset=['Valor'])
                                        .format({"Valor": "R$ {:.2f}"}),
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("Nenhuma movimentação encontrada para este período.")

# --- AUXILIAR VENDA (INTELIGENTE + SEPARADA POR TIPO) ---
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

    freq_dict = get_historico_preferencias(aluno_id)
    df_alimentos['freq'] = df_alimentos['nome'].map(freq_dict).fillna(0)
    df_alimentos = df_alimentos.sort_values(by=['freq', 'nome'], ascending=[False, True])
    
    if 'tipo' not in df_alimentos.columns: df_alimentos['tipo'] = 'ALIMENTO'
    df_bebidas = df_alimentos[df_alimentos['tipo'] == 'BEBIDA']
    df_comidas = df_alimentos[df_alimentos['tipo'] != 'BEBIDA']

    with st.form("form_venda_final"):
        quantidades = {}

        if not df_bebidas.empty:
            st.markdown("### 🥤 Bebidas")
            for index, row in df_bebidas.iterrows():
                c1, c2, c3 = st.columns([3, 1, 1])
                nome_display = f"⭐ {row['nome']}" if row['freq'] > 0 else row['nome']
                c1.write(nome_display)
                c2.write(f"R$ {row['valor']:.2f}")
                quantidades[row['id']] = c3.number_input("Qtd", min_value=0, step=1, key=f"qtd_{row['id']}", label_visibility="collapsed")
                st.markdown("<hr style='margin: 0px 0px 5px 0px; border-top: 1px dotted #ddd;'>", unsafe_allow_html=True)

        if not df_comidas.empty:
            st.markdown("### 🥪 Alimentos")
            for index, row in df_comidas.iterrows():
                c1, c2, c3 = st.columns([3, 1, 1])
                nome_display = f"⭐ {row['nome']}" if row['freq'] > 0 else row['nome']
                c1.write(nome_display)
                c2.write(f"R$ {row['valor']:.2f}")
                quantidades[row['id']] = c3.number_input("Qtd", min_value=0, step=1, key=f"qtd_{row['id']}", label_visibility="collapsed")
                st.markdown("<hr style='margin: 0px 0px 5px 0px; border-top: 1px dotted #ddd;'>", unsafe_allow_html=True)

        st.markdown("---")
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
