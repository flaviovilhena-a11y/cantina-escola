import streamlit as st
import pandas as pd
from datetime import date

# --- Configuração da Página (Nuvem/Navegador) ---
st.set_page_config(page_title="Cantina Escolar", layout="centered")

# --- Simulação de Banco de Dados (Session State) ---
if 'logado' not in st.session_state:
    st.session_state['logado'] = False

# Definição das colunas
if 'db_alunos' not in st.session_state:
    st.session_state['db_alunos'] = pd.DataFrame(columns=[
        "NOME", "SÉRIE", "TURMA", "TURNO", 
        "NASCIMENTO", "SALDO", "EMAIL", "TELEFONE 1", "TELEFONE 2"
    ])

# --- Tela de Login ---
def login_screen():
    st.title("Bem-vindo à Cantina Escolar")
    
    st.write("Por favor, faça o login para acessar o sistema.")
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
    st.write(f"Usuário logado: Administrador")
    
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

        # --- Lógica do Botão USUÁRIO ---
        if st.session_state.get('submenu') == 'usuario':
            st.info("Gerenciamento de Usuários")
            
            opt_user = st.radio("Escolha uma ação:", 
                ["IMPORTAR ALUNOS VIA CSV", "NOVO ALUNO", "ATUALIZAR ALUNO"])

            # 1. IMPORTAR ALUNOS VIA CSV (CORRIGIDO ENCODING)
            if opt_user == "IMPORTAR ALUNOS VIA CSV":
                st.write("Selecione o arquivo CSV (Listagem de Alunos):")
                st.write("O sistema detectará automaticamente nomes, emails e separará os telefones.")
                uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
                
                if st.button("ENVIAR"):
                    if uploaded_file is not None:
                        try:
                            # AQUI ESTÁ A CORREÇÃO: encoding='latin1'
                            df_new = pd.read_csv(uploaded_file, sep=';', encoding='latin1')
                            
                            # TRATAMENTO DE TELEFONES
                            if 'Telefones' in df_new.columns:
                                split_tels = df_new['Telefones'].astype(str).str.split(' / ', expand=True)
                                df_new['TELEFONE 1'] = split_tels[0]
                                if split_tels.shape[1] > 1:
                                    df_new['TELEFONE 2'] = split_tels[1]
                                else:
                                    df_new['TELEFONE 2'] = None
                            else:
                                df_new['TELEFONE 1'] = None
                                df_new['TELEFONE 2'] = None

                            # Renomeia as colunas
                            df_new = df_new.rename(columns={
                                'Aluno': 'NOME',
                                'Data de Nascimento': 'NASCIMENTO',
                                'E-mail': 'EMAIL',
                                'Turma': 'TURMA'
                            })

                            # Conversão de Data
                            df_new['NASCIMENTO'] = pd.to_datetime(df_new['NASCIMENTO'], dayfirst=True, errors='coerce').dt.date

                            # Preenche colunas que não vieram no CSV
                            df_new['SÉRIE'] = '' 
                            df_new['TURNO'] = ''
                            df_new['SALDO'] = 0.00

                            # Filtra e ordena
                            colunas_finais = ["NOME", "SÉRIE", "TURMA", "TURNO", "NASCIMENTO", "SALDO", "EMAIL", "TELEFONE 1", "TELEFONE 2"]
                            for col in colunas_finais:
                                if col not in df_new.columns:
                                    df_new[col] = None
                            
                            df_final = df_new[colunas_finais]

                            # Salva no banco de dados da sessão
                            st.session_state['db_alunos'] = pd.concat([st.session_state['db_alunos'], df_final], ignore_index=True)
                            
                            st.success(f"Importação realizada! {len(df_final)} alunos carregados.")
                            
                        except Exception as e:
                            st.error(f"Falha na importação: {e}")
                    else:
                        st.warning("Por favor, selecione um arquivo.")

            # 2. NOVO ALUNO
            elif opt_user == "NOVO ALUNO":
                with st.form("form_novo_aluno"):
                    st.write("Preencha os dados do aluno:")
                    nome = st.text_input("NOME")
                    serie = st.text_input("SÉRIE")
                    turma = st.text_input("TURMA")
                    turno = st.selectbox("TURNO", ["Matutino", "Vespertino", "Integral"])
                    nascimento = st.date_input("DATA DE NASCIMENTO")
                    email = st.text_input("EMAIL")
                    tel1 = st.text_input("TELEFONE 1 (Principal)")
                    tel2 = st.text_input("TELEFONE 2 (Recado/Telegram)")
                    saldo = st.number_input("SALDO INICIAL (R$)", value=0.00, step=0.01)

                    col_save, col_cancel = st.columns(2)
                    with col_save:
                        submitted = st.form_submit_button("SALVAR")
                    with col_cancel:
                        cancelled = st.form_submit
