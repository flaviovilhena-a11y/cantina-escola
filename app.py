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

    conn.commit()
    conn.close()

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
        c.execute('''
            UPDATE alunos
            SET turma=?, email=?, telefone1=?, telefone2=?, telefone3=?
            WHERE nome=?
        ''', (turma, email, tel1, tel2, tel3, nome))
        action = "atualizado"
    else:
        c.execute('''
            INSERT INTO alunos (nome, serie, turma, turno, nascimento, email, telefone1, telefone2, telefone3, saldo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (nome, serie, turma, turno, str(nasck), email, tel1, tel2, tel3, saldo_inicial))
        action = "novo"

    conn.commit()
    conn.close()
    return action

def update_aluno_manual(id_aluno, nome, serie, turma, turno, email, tel1, tel2, tel3, saldo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        UPDATE alunos 
        SET nome=?, serie=?, turma=?, turno=?, email=?, telefone1=?, telefone2=?, telefone3=?, saldo=?
        WHERE id=?
    ''', (nome, serie, turma, turno, email, tel1, tel2, tel3, saldo, id_aluno))
    conn.commit()
    conn.close()

def get_all_alunos():
    conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql_query("SELECT * FROM alunos", conn)
    except:
        df = pd.DataFrame()
    conn.close()
    return df

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
    senha = st.text_input("Senha", type="password")
    
    if st.button("Entrar"):
        if (usuario == "admin" and senha == "1234") or \
           (usuario == "fvilhena" and senha == "m3r1d1ano"):
            st.session_state['logado'] = True
            st.rerun()
        else:
            st.error("Login ou senha incorretos")

# --- Menu Principal ---
def main_menu():
    # --- BARRA LATERAL (MENU + BACKUP) ---
    st.sidebar.title("Menu")
    
    # Seção de Backup
    st.sidebar.markdown("---")
    st.sidebar.subheader("💾 Backup de Segurança")
    st.sidebar.info("A nuvem gratuita pode limpar os dados ao reiniciar. Baixe seu backup regularmente!")
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "rb") as fp:
            st.sidebar.download_button(
                label="⬇️ BAIXAR DADOS (Backup)",
                data=fp,
                file_name="backup_cantina.db",
                mime="application/x-sqlite3"
            )
    else:
        st.sidebar.warning("Nenhum dado para baixar ainda.")
    
    uploaded_db = st.sidebar.file_uploader("⬆️ RESTAURAR DADOS", type=["db", "sqlite", "sqlite3"])
    if uploaded_db is not None:
        if st.sidebar.button("CONFIRMAR RESTAURAÇÃO"):
            with open(DB_FILE, "wb") as f:
                f.write(uploaded_db.getbuffer())
            st.sidebar.success("Banco de dados restaurado! A página irá recarregar.")
            st.rerun()
            
    st.sidebar.markdown("---")
    
    if st.sidebar.button("Sair"):
        st.session_state['logado'] = False
        st.rerun()

    # --- ÁREA PRINCIPAL ---
    st.header("Painel Principal")
    st.write("Usuário logado: Administrador")
    
    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)

    with col1:
        btn_cadastro = st.button("CADASTRO", use_container_width=True)
    with col2:
        btn_comprar = st.button("COMPRAR REFEIÇÃO", use_container_width=True)
    with col3:
        btn_saldo = st.button("SALDO/HISTÓRICO", use_container_width=True)
    with col4:
        btn_recarga = st.button("RECARGA", use_container_width=True)

    # --- Lógica do Botão CADASTRO ---
    if btn_cadastro or st.session_state.get('menu_atual') == 'cadastro':
        st.session_state['menu_atual'] = 'cadastro'
        st.markdown("---")
        st.subheader("Menu de Cadastro")
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("USUÁRIO", use_container_width=True):
                st.session_state['submenu'] = 'usuario'
        with c2:
            if st.button("ALIMENTOS", use_container_width=True):
                st.session_state['submenu'] = 'alimentos'

        # ==========================================
        #       SUBMENU ALIMENTOS
        # ==========================================
        if st.session_state.get('submenu') == 'alimentos':
            st.info("Cadastro de Produtos / Cardápio")
            
            with st.expander("➕ Adicionar Novo Item", expanded=False):
                with st.form("form_novo_alimento"):
                    col_n, col_v = st.columns([3, 1])
                    with col_n:
                        nome_prod = st.text_input("Nome do Produto (ex: Salgado)")
                    with col_v:
                        valor_prod = st.number_input("Valor (R$)", min_value=0.00, step=0.50, format="%.2f")
                    
                    if st.form_submit_button("CADASTRAR"):
                        if nome_prod:
                            add_alimento_db(nome_prod, valor_prod)
                            st.success(f"{nome_prod} cadastrado!")
                            st.rerun()

            st.markdown("---")
            st.subheader("Gerenciar Cardápio")
            
            df_alimentos = get_all_alimentos()
            
            if not df_alimentos.empty:
                df_alimentos['label'] = df_alimentos['id'].astype(str) + " - " + df_alimentos['nome'] + " (R$ " + df_alimentos['valor'].astype(str) + ")"
                
                escolha_alimento = st.selectbox("Selecione um item para EDITAR ou EXCLUIR:", df_alimentos['label'].unique())
                id_sel_alimento = int(escolha_alimento.split(' - ')[0])
                item_dados = df_alimentos[df_alimentos['id'] == id_sel_alimento].iloc[0]
                
                with st.form("form_editar_alimento"):
                    col_ed_n, col_ed_v = st.columns([3, 1])
                    with col_ed_n:
                        novo_nome = st.text_input("Nome", value=item_dados['nome'])
                    with col_ed_v:
                        novo_valor = st.number_input("Valor (R$)", value=float(item_dados['valor']), step=0.50)
                    
                    c_upd, c_del = st.columns(2)
                    with c_upd:
                        if st.form_submit_button("💾 SALVAR ALTERAÇÕES"):
                            update_alimento_db(id_sel_alimento, novo_nome, novo_valor)
                            st.success("Item atualizado!")
                            st.rerun()
                    with c_del:
                        if st.form_submit_button("🗑️ EXCLUIR ITEM"):
                            delete_alimento_db(id_sel_alimento)
                            st.warning("Item removido.")
                            st.rerun()
                
                st.markdown("### Lista Completa")
                st.dataframe(df_alimentos[['nome', 'valor']], hide_index=True, use_container_width=True)
            else:
                st.info("Nenhum alimento cadastrado ainda.")

        # ==========================================
        #       SUBMENU USUÁRIO
        # ==========================================
        if st.session_state.get('submenu') == 'usuario':
            st.info("Gerenciamento de Usuários")
            opt_user = st.radio("Escolha uma ação:", 
                ["IMPORTAR ALUNOS VIA CSV", "NOVO ALUNO", "ATUALIZAR ALUNO"])

            if opt_user == "IMPORTAR ALUNOS VIA CSV":
                st.write("Selecione o arquivo CSV:")
                st.warning("Nota: Substitui automaticamente 'Â' por 'o'. Atualiza dados se aluno já existir.")
                uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
                
                if st.button("ENVIAR"):
                    if uploaded_file is not None:
                        try:
                            # 1. Leitura Inteligente do CSV
                            df_new = pd.read_csv(uploaded_file, sep=None, engine='python', encoding='latin1')
                            
                            # 2. LIMPEZA AUTOMÁTICA (Substitui Â por o)
                            # Aplica a substituição apenas nas colunas de texto (object)
                            obj_cols = df_new.select_dtypes(include=['object']).columns
                            for col in obj_cols:
                                df_new[col] = df_new[col].astype(str).str.replace('Â', 'o', regex=False)
                            
                            # 3. Processamento Normal
                            novos, atualizados = 0, 0
                            progress_bar = st.progress(0)
                            total_rows = len(df_new)
                            
                            for index, row in df_new.iterrows():
                                t1, t2, t3 = None, None, None
                                if 'Telefones' in row and pd.notna(row['Telefones']):
                                    parts = str(row['Telefones']).split(' / ')
                                    if len(parts) > 0: t1 = parts[0]
                                    if len(parts) > 1: t2 = parts[1]
                                    if len(parts) > 2: t3 = parts[2]
                                
                                nasck_val = None
                                if 'Data de Nascimento' in row and pd.notna(row['Data de Nascimento']):
                                    try:
                                        nasck_val = pd.to_datetime(row['Data de Nascimento'], dayfirst=True).date()
                                    except:
                                        nasck_val = None

                                res = upsert_aluno(
                                    nome=row.get('Aluno', ''), serie='', turma=row.get('Turma', ''), turno='', 
                                    nasck=nasck_val, email=row.get('E-mail', ''), 
                                    tel1=t1, tel2=t2, tel3=t3, saldo_inicial=0.00
                                )
                                if res == "novo": novos += 1
                                else: atualizados += 1
                                progress_bar.progress((index + 1) / total_rows)
                            
                            st.success(f"Concluído! {novos} novos, {atualizados} atualizados.")
                        except Exception as e:
                            st.error(f"Falha na importação: {e}")

            elif opt_user == "NOVO ALUNO":
                with st.form("form_novo"):
                    st.write("Dados do Aluno:")
                    nome = st.text_input("NOME")
                    serie = st.text_input("SÉRIE")
                    turma = st.text_input("TURMA")
                    turno = st.selectbox("TURNO", ["Matutino", "Vespertino", "Integral"])
                    nascimento = st.date_input("DATA DE NASCIMENTO")
                    email = st.text_input("EMAIL")
                    c_tel1, c_tel2, c_tel3 = st.columns(3)
                    with c_tel1: tel1 = st.text_input("TELEFONE 1")
                    with c_tel2: tel2 = st.text_input("TELEFONE 2")
                    with c_tel3: tel3 = st.text_input("TELEFONE 3")
                    saldo = st.number_input("SALDO INICIAL", value=0.00)

                    if st.form_submit_button("SALVAR"):
                        res = upsert_aluno(nome, serie, turma, turno, nascimento, email, tel1, tel2, tel3, saldo)
                        if res == "novo": st.success("Novo aluno cadastrado!")
                        else: st.info("Aluno já existia. Dados atualizados.")

            elif opt_user == "ATUALIZAR ALUNO":
                df_alunos = get_all_alunos()
                if df_alunos.empty:
                    st.warning("Nenhum aluno cadastrado.")
                else:
                    df_alunos['label'] = df_alunos['id'].astype(str) + " - " + df_alunos['nome']
                    escolha = st.selectbox("Selecione o aluno:", df_alunos['label'].unique())
                    id_sel = int(escolha.split(' - ')[0])
                    dados = df_alunos[df_alunos['id'] == id_sel].iloc[0]

                    with st.form("form_update"):
                        st.write(f"Editando: {dados['nome']}")
                        new_nome = st.text_input("NOME", value=dados['nome'])
                        new_serie = st.text_input("SÉRIE", value=dados['serie'] if dados['serie'] else "")
                        new_turma = st.text_input("TURMA", value=dados['turma'] if dados['turma'] else "")
                        
                        idx_turno = 0
                        opcoes_turno = ["Matutino", "Vespertino", "Integral"]
                        if dados['turno'] in opcoes_turno: idx_turno = opcoes_turno.index(dados['turno'])
                        new_turno = st.selectbox("TURNO", opcoes_turno, index=idx_turno)
                        
                        new_email = st.text_input("EMAIL", value=dados['email'] if dados['email'] else "")
                        c_t1, c_t2, c_t3 = st.columns(3)
                        
                        v_t1 = dados['telefone1'] if 'telefone1' in dados and dados['telefone1'] else ""
                        v_t2 = dados['telefone2'] if 'telefone2' in dados and dados['telefone2'] else ""
                        v_t3 = dados['telefone3'] if 'telefone3' in dados and dados['telefone3'] else ""

                        with c_t1: new_tel1 = st.text_input("TELEFONE 1", value=v_t1)
                        with c_t2: new_tel2 = st.text_input("TELEFONE 2", value=v_t2)
                        with c_t3: new_tel3 = st.text_input("TELEFONE 3", value=v_t3)
                        
                        new_saldo = st.number_input("SALDO", value=float(dados['saldo']) if dados['saldo'] else 0.00)

                        if st.form_submit_button("ATUALIZAR DADOS"):
                            update_aluno_manual(id_sel, new_nome, new_serie, new_turma, new_turno, new_email, new_tel1, new_tel2, new_tel3, new_saldo)
                            st.success("Dados atualizados!")
                            st.rerun()

    # DEBUG
    st.markdown("---")
    with st.expander("Ver Base de Dados (Admin)"):
        st.write("Alunos:")
        st.dataframe(get_all_alunos())
        st.write("Alimentos:")
        st.dataframe(get_all_alimentos())

# --- Controle de Fluxo ---
if st.session_state['logado']:
    main_menu()
else:
    login_screen()
