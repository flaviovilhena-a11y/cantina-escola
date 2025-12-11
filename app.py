import streamlit as st
import pandas as pd
from datetime import date

# --- Configuração da Página (Nuvem/Navegador)  ---
st.set_page_config(page_title="Cantina Escola", layout="centered")

# --- Simulação de Banco de Dados (Session State) ---
if 'logado' not in st.session_state:
    st.session_state['logado'] = False
if 'db_alunos' not in st.session_state:
    # Dados iniciais vazios com as colunas pedidas 
    st.session_state['db_alunos'] = pd.DataFrame(columns=[
        "NOME", "SÉRIE", "TURMA", "TURNO", "NASCIMENTO", "SALDO"
    ])

# --- Tela de Login  ---
def login_screen():
    st.title("Bem-vindo à Cantina Escola") # 
    usuario = st.text_input("Login")
    senha = st.text_input("Senha", type="password")
    
    if st.button("Entrar"):
        # Login simples para demonstração
        if usuario == "admin" and senha == "1234":
            st.session_state['logado'] = True
            st.rerun()
        else:
            st.error("Login ou senha incorretos")

# --- Menu Principal  ---
def main_menu():
    st.sidebar.title("Menu")
    if st.sidebar.button("Sair"):
        st.session_state['logado'] = False
        st.rerun()

    st.header("Painel Principal")
    
    # Criando os 4 botões lado a lado (ou em grid para celular)
    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)

    with col1:
        btn_cadastro = st.button("CADASTRO", use_container_width=True) # 
    with col2:
        btn_comprar = st.button("COMPRAR REFEIÇÃO", use_container_width=True) # 
    with col3:
        btn_saldo = st.button("SALDO/HISTÓRICO", use_container_width=True) # 
    with col4:
        btn_recarga = st.button("RECARGA", use_container_width=True) # 

    # --- Lógica do Botão CADASTRO [cite: 8] ---
    if btn_cadastro or st.session_state.get('menu_atual') == 'cadastro':
        st.session_state['menu_atual'] = 'cadastro'
        st.markdown("---")
        st.subheader("Menu de Cadastro")
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("USUÁRIO", use_container_width=True): # [cite: 9]
                st.session_state['submenu'] = 'usuario'
        with c2:
            if st.button("ALIMENTOS", use_container_width=True): # [cite: 10]
                st.session_state['submenu'] = 'alimentos'

        # --- Lógica do Botão USUÁRIO [cite: 11] ---
        if st.session_state.get('submenu') == 'usuario':
            st.info("Gerenciamento de Usuários")
            
            # Botões de ação do Usuário
            opt_user = st.radio("Escolha uma ação:", 
                ["IMPORTAR ALUNOS VIA CSV", "NOVO ALUNO", "ATUALIZAR ALUNO"]) # [cite: 12, 13, 14]

            # 1. IMPORTAR ALUNOS VIA CSV [cite: 15]
            if opt_user == "IMPORTAR ALUNOS VIA CSV":
                st.write("Selecione o arquivo CSV:")
                uploaded_file = st.file_uploader("Upload CSV", type=['csv']) # [cite: 15]
                
                if st.button("ENVIAR"): # 
                    if uploaded_file is not None:
                        try:
                            df_new = pd.read_csv(uploaded_file)
                            # Concatena com o banco existente
                            st.session_state['db_alunos'] = pd.concat([st.session_state['db_alunos'], df_new], ignore_index=True)
                            st.success("Importação de alunos com sucesso") # 
                        except Exception as e:
                            st.error(f"Falha na importação de alunos: {e}") # 
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
                    # Saldo inicial preenchido com 0.00 
                    saldo = st.number_input("SALDO INICIAL (R$)", value=0.00, step=0.01)

                    # Botões Salvar/Cancelar [cite: 18]
                    col_save, col_cancel = st.columns(2)
                    with col_save:
                        submitted = st.form_submit_button("SALVAR")
                    with col_cancel:
                        cancelled = st.form_submit_button("CANCELAR")

                    if submitted:
                        novo_dado = pd.DataFrame([{
                            "NOME": nome, "SÉRIE": serie, "TURMA": turma, 
                            "TURNO": turno, "NASCIMENTO": nascimento, "SALDO": saldo
                        }])
                        st.session_state['db_alunos'] = pd.concat([st.session_state['db_alunos'], novo_dado], ignore_index=True)
                        st.success("Aluno salvo com sucesso!")
                    
                    if cancelled:
                        st.warning("Operação cancelada.")

            # 3. ATUALIZAR ALUNO [cite: 19]
            elif opt_user == "ATUALIZAR ALUNO":
                if st.session_state['db_alunos'].empty:
                    st.warning("Não há alunos cadastrados para atualizar.")
                else:
                    # Selecionar aluno [cite: 19]
                    lista_nomes = st.session_state['db_alunos']['NOME'].unique()
                    aluno_selecionado = st.selectbox("Selecione o aluno:", lista_nomes)
                    
                    # Pegar dados atuais
                    idx = st.session_state['db_alunos'].index[st.session_state['db_alunos']['NOME'] == aluno_selecionado][0]
                    dados_atuais = st.session_state['db_alunos'].loc[idx]

                    # Formulário de edição [cite: 20]
                    with st.form("form_atualiza_aluno"):
                        new_nome = st.text_input("NOME", value=dados_atuais['NOME'])
                        new_serie = st.text_input("SÉRIE", value=dados_atuais['SÉRIE'])
                        new_turma = st.text_input("TURMA", value=dados_atuais['TURMA'])
                        new_turno = st.selectbox("TURNO", ["Matutino", "Vespertino", "Integral"], 
                                               index=["Matutino", "Vespertino", "Integral"].index(dados_atuais['TURNO']))
                        new_saldo = st.number_input("SALDO", value=float(dados_atuais['SALDO']))

                        # Botões Salvar/Cancelar [cite: 21]
                        c_save, c_cancel = st.columns(2)
                        save_upd = st.form_submit_button("SALVAR")
                        cancel_upd = st.form_submit_button("CANCELAR")

                        if save_upd:
                            st.session_state['db_alunos'].at[idx, 'NOME'] = new_nome
                            st.session_state['db_alunos'].at[idx, 'SÉRIE'] = new_serie
                            st.session_state['db_alunos'].at[idx, 'TURMA'] = new_turma
                            st.session_state['db_alunos'].at[idx, 'TURNO'] = new_turno
                            st.session_state['db_alunos'].at[idx, 'SALDO'] = new_saldo
                            st.success("Dados atualizados!")
                        
                        if cancel_upd:
                            st.info("Edição cancelada.")

    # Exibir tabela para conferência (apenas para debug)
    if not st.session_state['db_alunos'].empty:
        st.markdown("---")
        with st.expander("Ver Base de Dados (Admin)"):
            st.dataframe(st.session_state['db_alunos'])

# --- Controle de Fluxo ---
if st.session_state['logado']:
    main_menu()
else:
    login_screen()
