import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- Configuração da Página ---
st.set_page_config(page_title="Cantina Peixinho Dourado", layout="centered")

# --- Configuração do Banco de Dados (SQLite) ---
def init_db():
    conn = sqlite3.connect('cantina.db')
    c = conn.cursor()
    
    # Cria a tabela base
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
    
    # Migração para garantir suporte a 3 telefones
    try:
        c.execute("ALTER TABLE alunos ADD COLUMN telefone3 TEXT")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

# --- NOVA FUNÇÃO INTELIGENTE (Importação com Verificação) ---
def upsert_aluno(nome, serie, turma, turno, nasck, email, tel1, tel2, tel3, saldo_inicial):
    conn = sqlite3.connect('cantina.db')
    c = conn.cursor()

    # 1. Verifica se o aluno já existe pelo NOME
    c.execute("SELECT id FROM alunos WHERE nome = ?", (nome,))
    data = c.fetchone()

    action = ""

    if data:
        # --- CENÁRIO A: ALUNO EXISTE -> ATUALIZAR DADOS (MANTENDO SALDO) ---
        # O ID do aluno é data[0]
        # Atualizamos apenas o que foi solicitado: Turma, Email, Telefones.
        # Preservamos: Saldo, Série, Turno e Nascimento (a menos que queira mudar tudo, mas o foco é contato)
        c.execute('''
            UPDATE alunos
            SET turma=?, email=?, telefone1=?, telefone2=?, telefone3=?
            WHERE nome=?
        ''', (turma, email, tel1, tel2, tel3, nome))
        action = "atualizado"
    else:
        # --- CENÁRIO B: ALUNO NOVO -> INSERIR ---
        c.execute('''
            INSERT INTO alunos (nome, serie, turma, turno, nascimento, email, telefone1, telefone2, telefone3, saldo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (nome, serie, turma, turno, str(nasck), email, tel1, tel2, tel3, saldo_inicial))
        action = "novo"

    conn.commit()
    conn.close()
    return action

# Função para atualizar aluno manualmente (Menu Editar)
def update_aluno_manual(id_aluno, nome, serie, turma, turno, email, tel1, tel2, tel3, saldo):
    conn = sqlite3.connect('cantina.db')
    c = conn.cursor()
    c.execute('''
        UPDATE alunos 
        SET nome=?, serie=?, turma=?, turno=?, email=?, telefone1=?, telefone2=?, telefone3=?, saldo=?
        WHERE id=?
    ''', (nome, serie, turma, turno, email, tel1, tel2, tel3, saldo, id_aluno))
    conn.commit()
    conn.close()

# Função para ler todos os alunos
def get_all_alunos():
    conn = sqlite3.connect('cantina.db')
    df = pd.read_sql_query("SELECT * FROM alunos", conn)
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
    st.sidebar.title("Menu")
    if st.sidebar.button("Sair"):
        st.session_state['logado'] = False
        st.rerun()

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

        # --- Submenu USUÁRIO ---
        if st.session_state.get('submenu') == 'usuario':
            st.info("Gerenciamento de Usuários (Banco de Dados Local)")
            
            opt_user = st.radio("Escolha uma ação:", 
                ["IMPORTAR ALUNOS VIA CSV", "NOVO ALUNO", "ATUALIZAR ALUNO"])

            # 1. IMPORTAR CSV (Com verificação de Duplicidade)
            if opt_user == "IMPORTAR ALUNOS VIA CSV":
                st.write("Selecione o arquivo CSV:")
                st.warning("Nota: Se o aluno já existir, apenas Turma, Email e Telefones serão atualizados. O Saldo será mantido.")
                uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
                
                if st.button("ENVIAR"):
                    if uploaded_file is not None:
                        try:
                            df_new = pd.read_csv(uploaded_file, sep=';', encoding='latin1')
                            
                            novos = 0
                            atualizados = 0
                            
                            progress_bar = st.progress(0)
                            total_rows = len(df_new)
                            
                            for index, row in df_new.iterrows():
                                # Tratamento Telefones
                                t1, t2, t3 = None, None, None
                                if 'Telefones' in row and pd.notna(row['Telefones']):
                                    parts = str(row['Telefones']).split(' / ')
                                    if len(parts) > 0: t1 = parts[0]
                                    if len(parts) > 1: t2 = parts[1]
                                    if len(parts) > 2: t3 = parts[2]
                                
                                # Tratamento Data
                                nasck_val = None
                                if 'Data de Nascimento' in row and pd.notna(row['Data de Nascimento']):
                                    try:
                                        nasck_val = pd.to_datetime(row['Data de Nascimento'], dayfirst=True).date()
                                    except:
                                        nasck_val = None

                                # CHAMA A NOVA FUNÇÃO DE UPSERT
                                resultado = upsert_aluno(
                                    nome=row.get('Aluno', ''),
                                    serie='', 
                                    turma=row.get('Turma', ''),
                                    turno='', 
                                    nasck=nasck_val,
                                    email=row.get('E-mail', ''),
                                    tel1=t1,
                                    tel2=t2,
                                    tel3=t3,
                                    saldo_inicial=0.00 # Só usado se for novo aluno
                                )
                                
                                if resultado == "novo":
                                    novos += 1
                                else:
                                    atualizados += 1
                                
                                # Atualiza barra de progresso
                                progress_bar.progress((index + 1) / total_rows)
                            
                            st.success(f"Processo concluído! {novos} novos alunos cadastrados e {atualizados} alunos atualizados.")
                            
                        except Exception as e:
                            st.error(f"Falha na importação: {e}")

            # 2. NOVO ALUNO
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
                        # Usa a mesma lógica, se já existir ele avisa ou atualiza
                        res = upsert_aluno(nome, serie, turma, turno, nascimento, email, tel1, tel2, tel3, saldo)
                        if res == "novo":
                            st.success("Novo aluno cadastrado!")
                        else:
                            st.info("Este aluno já existia. Os dados de contato foram atualizados.")

            # 3. ATUALIZAR ALUNO (Manual)
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
                        if dados['turno'] in opcoes_turno:
                            idx_turno = opcoes_turno.index(dados['turno'])
                        new_turno = st.selectbox("TURNO", opcoes_turno, index=idx_turno)
                        
                        new_email = st.text_input("EMAIL", value=dados['email'] if dados['email'] else "")
                        
                        c_t1, c_t2, c_t3 = st.columns(3)
                        val_t1 = dados['telefone1'] if 'telefone1' in dados and dados['telefone1'] else ""
                        val_t2 = dados['telefone2'] if 'telefone2' in dados and dados['telefone2'] else ""
                        val_t3 = dados['telefone3'] if 'telefone3' in dados and dados['telefone3'] else ""

                        with c_t1: new_tel1 = st.text_input("TELEFONE 1", value=val_t1)
                        with c_t2: new_tel2 = st.text_input("TELEFONE 2", value=val_t2)
                        with c_t3: new_tel3 = st.text_input("TELEFONE 3", value=val_t3)
                        
                        new_saldo = st.number_input("SALDO", value=float(dados['saldo']) if dados['saldo'] else 0.00)

                        if st.form_submit_button("ATUALIZAR DADOS"):
                            update_aluno_manual(id_sel, new_nome, new_serie, new_turma, new_turno, new_email, new_tel1, new_tel2, new_tel3, new_saldo)
                            st.success("Dados atualizados com sucesso!")
                            st.rerun()

    # Exibir tabela para conferência
    st.markdown("---")
    with st.expander("Ver Banco de Dados Completo"):
        df_view = get_all_alunos()
        st.dataframe(df_view)

# --- Controle de Fluxo ---
if st.session_state['logado']:
    main_menu()
else:
    login_screen()
