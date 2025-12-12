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
    
    # Migração para garantir suporte a 3 telefones (caso banco antigo exista)
    try:
        c.execute("ALTER TABLE alunos ADD COLUMN telefone3 TEXT")
    except sqlite3.OperationalError:
        pass

    # 2. NOVA TABELA DE ALIMENTOS
    c.execute('''
        CREATE TABLE IF NOT EXISTS alimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            valor REAL
        )
    ''')

    conn.commit()
    conn.close()

# --- FUNÇÕES DE ALIMENTOS ---
def add_alimento_db(nome, valor):
    conn = sqlite3.connect('cantina.db')
    c = conn.cursor()
    c.execute('INSERT INTO alimentos (nome, valor) VALUES (?, ?)', (nome, valor))
    conn.commit()
    conn.close()

def get_all_alimentos():
    conn = sqlite3.connect('cantina.db')
    df = pd.read_sql_query("SELECT * FROM alimentos", conn)
    conn.close()
    return df

def delete_alimento_db(id_alimento):
    conn = sqlite3.connect('cantina.db')
    c = conn.cursor()
    c.execute('DELETE FROM alimentos WHERE id=?', (id_alimento,))
    conn.commit()
    conn.close()

# --- FUNÇÕES DE ALUNOS (Mantidas) ---
def upsert_aluno(nome, serie, turma, turno, nasck, email, tel1, tel2, tel3, saldo_inicial):
    conn = sqlite3.connect('cantina.db')
    c = conn.cursor()

    # Verifica se aluno existe pelo NOME
    c.execute("SELECT id FROM alunos WHERE nome = ?", (nome,))
    data = c.fetchone()
    action = ""

    if data:
        # Atualiza apenas contatos e turma
        c.execute('''
            UPDATE alunos
            SET turma=?, email=?, telefone1=?, telefone2=?, telefone3=?
            WHERE nome=?
        ''', (turma, email, tel1, tel2, tel3, nome))
        action = "atualizado"
    else:
        # Insere novo
        c.execute('''
            INSERT INTO alunos (nome, serie, turma, turno, nascimento, email, telefone1, telefone2, telefone3, saldo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (nome, serie, turma, turno, str(nasck), email, tel1, tel2, tel3, saldo_inicial))
        action = "novo"

    conn.commit()
    conn.close()
    return action

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

        # ==========================================
        #       SUBMENU ALIMENTOS (NOVO)
        # ==========================================
        if st.session_state.get('submenu') == 'alimentos':
            st.info("Cadastro de Produtos / Cardápio")
            
            # Formulário de Cadastro
            with st.form("form_alimento"):
                st.write("Adicionar Novo Item:")
                col_n, col_v = st.columns([3, 1])
                with col_n:
                    nome_prod = st.text_input("Nome do Produto (ex: Salgado, Suco)")
                with col_v:
                    valor_prod = st.number_input("Valor (R$)", min_value=0.00, step=0.50, format="%.2f")
                
                if st.form_submit_button("CADASTRAR PRODUTO"):
                    if nome_prod:
                        add_alimento_db(nome_prod, valor_prod)
                        st.success(f"{nome_prod} cadastrado por R$ {valor_prod:.2f}")
                        st.rerun()
                    else:
                        st.warning("Digite o nome do produto.")

            # Lista de Produtos Cadastrados
            st.markdown("### Itens no Cardápio")
            df_alimentos = get_all_alimentos()
            
            if not df_alimentos.empty:
                # Exibe tabela bonitinha
                st.dataframe(df_alimentos[['id', 'nome', 'valor']], hide_index=True, use_container_width=True)
                
                # Opção de Excluir
                st.markdown("#### Excluir Item")
                lista_exclusao = df_alimentos['id'].astype(str) + " - " + df_alimentos['nome']
                item_to_delete = st.selectbox("Selecione para excluir:", lista_exclusao)
                
                if st.button("EXCLUIR ITEM SELECIONADO"):
                    id_del = int(item_to_delete.split(' - ')[0])
                    delete_alimento_db(id_del)
                    st.warning("Item removido do cardápio.")
                    st.rerun()
            else:
                st.info("Nenhum alimento cadastrado ainda.")

        # ==========================================
        #       SUBMENU USUÁRIO (MANTIDO)
        # ==========================================
        if st.session_state.get('submenu') == 'usuario':
            st.info("Gerenciamento de Usuários")
            opt_user = st.radio("Escolha uma ação:", 
                ["IMPORTAR ALUNOS VIA CSV", "NOVO ALUNO", "ATUALIZAR ALUNO"])

            if opt_user == "IMPORTAR ALUNOS VIA CSV":
                st.write("Selecione o arquivo CSV:")
                st.warning("Nota: Atualiza telefones/turma se aluno já existir. Mantém saldo.")
                uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
                
                if st.button("ENVIAR"):
                    if uploaded_file is not None:
                        try:
                            df_new = pd.read_csv(uploaded_file, sep=';', encoding='latin1')
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

    # Exibir tabela DEBUG (Opcional, pode remover depois)
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
