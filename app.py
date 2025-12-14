import streamlit as st
import pandas as pd
import sqlite3
import shutil
import os
import binascii
import time
from datetime import datetime, timedelta, date
from collections import Counter

# --- Configuração da Página ---
st.set_page_config(page_title="Cantina Peixinho Dourado", layout="centered")

# ==========================================
#    CONFIGURAÇÃO DO PIX (QR CODE ESTÁTICO)
# ==========================================
CHAVE_PIX_ESCOLA = "flaviovilhena@gmail.com" 
NOME_BENEFICIARIO = "FLAVIO SILVA"
CIDADE_BENEFICIARIO = "MANAUS" 
# ==========================================

# --- Configuração do Banco de Dados (SQLite) ---
DB_FILE = 'cantina.db'

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Tabelas
    c.execute('''CREATE TABLE IF NOT EXISTS alunos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, serie TEXT, turma TEXT, turno TEXT, nascimento TEXT, email TEXT, telefone1 TEXT, telefone2 TEXT, telefone3 TEXT, saldo REAL)''')
    try: c.execute("ALTER TABLE alunos ADD COLUMN telefone3 TEXT")
    except: pass

    c.execute('''CREATE TABLE IF NOT EXISTS alimentos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, valor REAL, tipo TEXT)''')
    try: 
        c.execute("ALTER TABLE alimentos ADD COLUMN tipo TEXT")
        c.execute("UPDATE alimentos SET tipo = 'ALIMENTO' WHERE tipo IS NULL")
    except: pass

    c.execute('''CREATE TABLE IF NOT EXISTS transacoes (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_id INTEGER, itens TEXT, valor_total REAL, data_hora TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS recargas (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_id INTEGER, valor REAL, data_hora TEXT, metodo_pagamento TEXT, nsu TEXT)''')
    try: c.execute("ALTER TABLE recargas ADD COLUMN metodo_pagamento TEXT")
    except: pass
    try: c.execute("ALTER TABLE recargas ADD COLUMN nsu TEXT")
    except: pass

    conn.commit()
    conn.close()

# --- CLASSE PARA GERAR O PAYLOAD PIX (BR CODE) ---
class PixPayload:
    def __init__(self, chave, nome, cidade, valor, txid="***"):
        self.chave = chave
        self.nome = nome
        self.cidade = cidade
        self.valor = f"{valor:.2f}"
        self.txid = txid

    def _fmt(self, id, value):
        size = f"{len(value):02}"
        return f"{id}{size}{value}"

    def _crc16(self, payload):
        crc = 0xFFFF
        poly = 0x1021
        for byte in payload.encode("utf-8"):
            crc ^= (byte << 8)
            for _ in range(8):
                if (crc & 0x8000): crc = (crc << 1) ^ poly
                else: crc <<= 1
            crc &= 0xFFFF
        return f"{crc:04X}"

    def gerar_payload(self):
        payload = (
            self._fmt("00", "01") +
            self._fmt("26", self._fmt("00", "BR.GOV.BCB.PIX") + self._fmt("01", self.chave)) +
            self._fmt("52", "0000") +
            self._fmt("53", "986") +
            self._fmt("54", self.valor) +
            self._fmt("58", "BR") +
            self._fmt("59", self.nome) +
            self._fmt("60", self.cidade) +
            self._fmt("62", self._fmt("05", self.txid)) +
            "6304"
        )
        payload += self._crc16(payload)
        return payload

# --- FUNÇÕES DE BANCO DE DADOS ---
def get_all_alunos():
    conn = sqlite3.connect(DB_FILE)
    try: df = pd.read_sql_query("SELECT * FROM alunos", conn)
    except: df = pd.DataFrame()
    conn.close()
    return df

def get_alunos_por_turma(turma):
    conn = sqlite3.connect(DB_FILE)
    try: df = pd.read_sql_query("SELECT * FROM alunos WHERE turma = ? ORDER BY nome ASC", conn, params=(turma,))
    except: df = pd.DataFrame()
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

def registrar_recarga(aluno_id, valor, metodo, nsu=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    data_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    c.execute("INSERT INTO recargas (aluno_id, valor, data_hora, metodo_pagamento, nsu) VALUES (?, ?, ?, ?, ?)", 
              (aluno_id, valor, data_hora, metodo, nsu))
    
    c.execute("SELECT saldo FROM alunos WHERE id = ?", (aluno_id,))
    saldo_atual = c.fetchone()[0]
    c.execute("UPDATE alunos SET saldo = ? WHERE id = ?", (saldo_atual + valor, aluno_id))
    conn.commit()
    conn.close()

def get_vendas_hoje_turma(turma):
    conn = sqlite3.connect(DB_FILE)
    hoje = datetime.now().strftime("%d/%m/%Y")
    query = '''SELECT a.nome, t.itens, t.valor_total FROM transacoes t JOIN alunos a ON t.aluno_id = a.id WHERE a.turma = ? AND t.data_hora LIKE ? ORDER BY t.id DESC'''
    try: df = pd.read_sql_query(query, conn, params=(turma, f"{hoje}%"))
    except: df = pd.DataFrame()
    conn.close()
    return df

def get_historico_preferencias(aluno_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT itens FROM transacoes WHERE aluno_id = ? ORDER BY id DESC LIMIT 10", (aluno_id,))
    rows = cursor.fetchall()
    conn.close()
    contador = Counter()
    for row in rows:
        if row[0]:
            for item in row[0].split(", "):
                try: contador[item.split("x ")[1]] += int(item.split("x ")[0])
                except: continue
    return contador

def get_extrato_aluno(aluno_id, dias_filtro):
    conn = sqlite3.connect(DB_FILE)
    data_corte = None
    if dias_filtro != 'TODOS': data_corte = datetime.now() - timedelta(days=int(dias_filtro))
    
    c = conn.cursor()
    c.execute("SELECT data_hora, itens, valor_total FROM transacoes WHERE aluno_id = ?", (aluno_id,))
    vendas = c.fetchall()
    c.execute("SELECT data_hora, valor, metodo_pagamento FROM recargas WHERE aluno_id = ?", (aluno_id,))
    recargas = c.fetchall()
    conn.close()

    extrato = []
    for v in vendas:
        dt = datetime.strptime(v[0], "%d/%m/%Y %H:%M:%S")
        if not data_corte or dt >= data_corte: extrato.append({"Data": dt, "Tipo": "COMPRA", "Descrição": v[1], "Valor": -v[2]})
    for r in recargas:
        dt = datetime.strptime(r[0], "%d/%m/%Y %H:%M:%S")
        if not data_corte or dt >= data_corte: extrato.append({"Data": dt, "Tipo": "RECARGA", "Descrição": f"Via {r[2] or 'Crédito'}", "Valor": r[1]})
    
    if extrato:
        df = pd.DataFrame(extrato).sort_values(by="Data", ascending=False)
        df['Data'] = df['Data'].apply(lambda x: x.strftime("%d/%m/%Y %H:%M"))
        return df
    return pd.DataFrame()

# --- FUNÇÕES DE RELATÓRIO ---
def get_relatorio_produtos(data_filtro):
    conn = sqlite3.connect(DB_FILE)
    query = "SELECT itens FROM transacoes WHERE data_hora LIKE ?"
    c = conn.cursor()
    c.execute(query, (f"{data_filtro}%",))
    rows = c.fetchall()
    
    df_precos = pd.read_sql_query("SELECT nome, valor FROM alimentos", conn)
    preco_map = dict(zip(df_precos['nome'], df_precos['valor']))
    conn.close()

    qtd_geral = Counter()
    for r in rows:
        if r[0]:
            itens_lista = r[0].split(", ")
            for item in itens_lista:
                try:
                    parts = item.split("x ")
                    if len(parts) == 2:
                        qtd = int(parts[0])
                        nome = parts[1]
                        qtd_geral[nome] += qtd
                except: continue
    
    dados = []
    total_dia = 0.0
    for nome, qtd in qtd_geral.items():
        valor_unit = preco_map.get(nome, 0.0) 
        valor_total = valor_unit * qtd
        total_dia += valor_total
        dados.append({"Produto": nome, "Qtd Vendida": qtd, "Valor Total (R$)": valor_total})
    
    if dados:
        df = pd.DataFrame(dados)
        df = df.sort_values(by="Qtd Vendida", ascending=False)
        return df, total_dia
    return pd.DataFrame(), 0.0

def get_relatorio_alunos_dia(data_filtro):
    conn = sqlite3.connect(DB_FILE)
    query = '''
        SELECT a.nome, t.itens, t.valor_total, t.data_hora 
        FROM transacoes t 
        JOIN alunos a ON t.aluno_id = a.id 
        WHERE t.data_hora LIKE ? 
        ORDER BY t.data_hora ASC
    '''
    try:
        df = pd.read_sql_query(query, conn, params=(f"{data_filtro}%",))
        if not df.empty:
            df['Hora'] = df['data_hora'].apply(lambda x: x.split(' ')[1])
            df = df[['Hora', 'nome', 'itens', 'valor_total']]
            df.columns = ['Hora', 'Aluno', 'Produtos', 'Valor']
            
            total_geral = df['Valor'].sum()
            linha_total = pd.DataFrame([{
                'Hora': '', 
                'Aluno': 'TOTAL GERAL', 
                'Produtos': '', 
                'Valor': total_geral
            }])
            df = pd.concat([df, linha_total], ignore_index=True)
    except:
        df = pd.DataFrame()
    conn.close()
    return df

# --- FUNÇÕES DE ALIMENTOS E ALUNOS (CRUD) ---
def add_alimento_db(nome, valor, tipo):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor(); c.execute('INSERT INTO alimentos (nome, valor, tipo) VALUES (?, ?, ?)', (nome, valor, tipo)); conn.commit(); conn.close()
def update_alimento_db(id, nome, valor, tipo):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor(); c.execute('UPDATE alimentos SET nome=?, valor=?, tipo=? WHERE id=?', (nome, valor, tipo, id)); conn.commit(); conn.close()
def delete_alimento_db(id):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor(); c.execute('DELETE FROM alimentos WHERE id=?', (id,)); conn.commit(); conn.close()
def get_all_alimentos():
    conn = sqlite3.connect(DB_FILE); 
    try: df = pd.read_sql_query("SELECT * FROM alimentos", conn)
    except: df = pd.DataFrame()
    conn.close(); return df

def upsert_aluno(nome, serie, turma, turno, nasck, email, tel1, tel2, tel3, saldo_inicial):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor(); c.execute("SELECT id FROM alunos WHERE nome = ?", (nome,))
    data = c.fetchone(); action = ""
    # Converte Date para String se não for nulo
    nasc_str = str(nasck) if nasck else None
    
    if data:
        # Atualiza dados se nome já existe
        c.execute('''UPDATE alunos SET serie=?, turma=?, turno=?, nascimento=?, email=?, telefone1=?, telefone2=?, telefone3=? WHERE nome=?''', 
                  (serie, turma, turno, nasc_str, email, tel1, tel2, tel3, nome))
        action = "atualizado"
    else:
        # Insere novo
        c.execute('''INSERT INTO alunos (nome, serie, turma, turno, nascimento, email, telefone1, telefone2, telefone3, saldo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                  (nome, serie, turma, turno, nasc_str, email, tel1, tel2, tel3, saldo_inicial))
        action = "novo"
    conn.commit(); conn.close(); return action

# --- FUNÇÃO DE ATUALIZAÇÃO ---
def update_aluno_manual(id, nome, serie, turma, turno, nasc_str, email, t1, t2, t3, saldo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''UPDATE alunos SET nome=?, serie=?, turma=?, turno=?, nascimento=?, email=?, telefone1=?, telefone2=?, telefone3=?, saldo=? WHERE id=?''', 
              (nome, serie, turma, turno, nasc_str, email, t1, t2, t3, saldo, id))
    conn.commit()
    conn.close()

def delete_aluno_db(id):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor(); c.execute("DELETE FROM alunos WHERE id=?", (id,)); conn.commit(); conn.close()
def delete_turma_db(turma):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor(); c.execute("DELETE FROM alunos WHERE turma=?", (turma,)); count = c.rowcount; conn.commit(); conn.close(); return count

init_db()

if 'logado' not in st.session_state: st.session_state['logado'] = False

def login_screen():
    st.title("Cantina Peixinho Dourado"); st.write("Acesso ao Sistema"); usuario = st.text_input("Login")
    if st.button("Entrar"):
        if usuario == "fvilhena": st.session_state['logado'] = True; st.rerun()
        else: st.error("Acesso negado.")

def main_menu():
    st.sidebar.title("Menu"); st.sidebar.subheader("💾 Backup")
    
    if os.path.exists(DB_FILE): 
        with open(DB_FILE,"rb") as f: st.sidebar.download_button("⬇️ BAIXAR DADOS",f,"backup.db")
    
    up = st.sidebar.file_uploader("RESTORE", type=["db"])
    if up and st.sidebar.button("CONFIRMAR IMPORTAÇÃO DE DADOS"):
        try:
            with open(DB_FILE, "wb") as f:
                f.write(up.getbuffer())
            st.sidebar.success("✅ Dados importados com sucesso! Reiniciando...")
            time.sleep(2)
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"❌ Erro ao importar: {e}")

    st.sidebar.markdown("---")
    if st.sidebar.button("Sair"): st.session_state['logado']=False; st.rerun()

    st.header("Painel Principal"); st.write("Usuário: fvilhena")
    
    c1,c2=st.columns(2); c3,c4=st.columns(2); c5,c6=st.columns(2)
    with c1: 
        if st.button("CADASTRO",use_container_width=True): st.session_state.update(menu='cadastro', sub=None)
    with c2: 
        if st.button("COMPRAR",use_container_width=True): st.session_state.update(menu='comprar', modo=None)
    with c3: 
        if st.button("SALDO/HISTÓRICO",use_container_width=True): st.session_state.update(menu='hist', hist_id=None)
    with c4: 
        if st.button("RECARGA",use_container_width=True): st.session_state.update(menu='recarga', rec_mode=None, pix_data=None)
    with c5:
        if st.button("RELATÓRIOS",use_container_width=True): st.session_state.update(menu='relatorios', rel_mode='produtos')

    menu = st.session_state.get('menu')

    # --- CADASTRO ---
    if menu == 'cadastro':
        st.markdown("---"); c1,c2=st.columns(2)
        if c1.button("USUÁRIO",use_container_width=True): st.session_state['sub']='user'
        if c2.button("ALIMENTOS",use_container_width=True): st.session_state['sub']='food'
        
        if st.session_state.get('sub') == 'food':
            act=st.radio("Ação",["NOVO","ALTERAR","EXCLUIR"],horizontal=True); df=get_all_alimentos()
            if act=="NOVO":
                with st.form("nf"): 
                    n=st.text_input("Nome"); v=st.number_input("Valor",0.0,step=0.5); t=st.selectbox("Tipo",["ALIMENTO","BEBIDA"])
                    if st.form_submit_button("CADASTRAR"): add_alimento_db(n,v,t); st.success("Ok!"); st.rerun()
                if not df.empty: st.dataframe(df[['nome','valor','tipo']],hide_index=True)
            elif act=="ALTERAR" and not df.empty:
                df['l']=df['id'].astype(str)+" - "+df['nome']; s=st.selectbox("Item",df['l'].unique()); id=int(s.split(' - ')[0]); d=df[df['id']==id].iloc[0]
                with st.form("ef"):
                    n=st.text_input("Nome",d['nome']); v=st.number_input("Valor",value=float(d['valor'])); t=st.selectbox("Tipo",["ALIMENTO","BEBIDA"],index=["ALIMENTO","BEBIDA"].index(d['tipo'] if d['tipo'] in ["ALIMENTO","BEBIDA"] else "ALIMENTO"))
                    if st.form_submit_button("SALVAR"): update_alimento_db(id,n,v,t); st.success("Ok!"); st.rerun()
            elif act=="EXCLUIR" and not df.empty:
                df['l']=df['id'].astype(str)+" - "+df['nome']; s=st.selectbox("Excluir",df['l'].unique()); id=int(s.split(' - ')[0])
                if st.button("CONFIRMAR"): delete_alimento_db(id); st.success("Apagado!"); st.rerun()

        if st.session_state.get('sub') == 'user':
            act=st.radio("Ação",["IMPORTAR CSV","NOVO ALUNO","ATUALIZAR","EXCLUIR ALUNO","EXCLUIR TURMA"])
            
            if act=="IMPORTAR CSV":
                u=st.file_uploader("CSV",type=['csv'])
                if u and st.button("ENVIAR"):
                    try:
                        df=pd.read_csv(u,sep=None,engine='python',encoding='latin1')
                        for c in df.select_dtypes(include=['object']): df[c]=df[c].astype(str).str.replace('1Â','1o',regex=False).str.replace('°','',regex=False)
                        n,a,b=0,0,st.progress(0)
                        for i,r in df.iterrows():
                            upsert_aluno(r.get('Aluno',''),'',r.get('Turma',''),'',None,r.get('E-mail',''),None,None,None,0.0); b.progress((i+1)/len(df))
                        st.success(f"{n} novos, {a} atualizados.")
                    except Exception as e: st.error(f"Erro: {e}")
            
            # --- NOVO ALUNO (COM DATA BR) ---
            elif act=="NOVO ALUNO":
                st.write("📝 **Ficha de Cadastro Completa**")
                with st.form("nal"):
                    c1, c2 = st.columns([3, 1])
                    nm = c1.text_input("Nome Completo")
                    # Adicionado format="DD/MM/YYYY"
                    nas = c2.date_input("Data Nascimento", value=None, min_value=date(1990,1,1), format="DD/MM/YYYY")
                    
                    c3, c4, c5 = st.columns(3)
                    ser = c3.text_input("Série")
                    tr = c4.text_input("Turma")
                    tur = c5.selectbox("Turno", ["Matutino", "Vespertino", "Integral"])
                    
                    em = st.text_input("E-mail Responsável")
                    
                    c6, c7, c8 = st.columns(3)
                    tel1 = c6.text_input("Telefone 1")
                    tel2 = c7.text_input("Telefone 2")
                    tel3 = c8.text_input("Telefone 3")
                    
                    sl = st.number_input("Saldo Inicial (R$)", value=0.0)
                    
                    if st.form_submit_button("CONFIRMAR CADASTRO"): 
                        upsert_aluno(nm, ser, tr, tur, nas, em, tel1, tel2, tel3, sl)
                        st.success("Aluno salvo com sucesso!")
                        st.rerun()
            
            # --- ATUALIZAR (COM DATA BR) ---
            elif act=="ATUALIZAR":
                df=get_all_alunos()
                if not df.empty:
                    df=df.sort_values('nome')
                    df['l']=df['id'].astype(str)+" - "+df['nome']
                    sel = st.selectbox("Buscar Aluno:", df['l'].unique())
                    id_a = int(sel.split(' - ')[0])
                    d = df[df['id']==id_a].iloc[0]
                    
                    try:
                        data_nasc_atual = datetime.strptime(d['nascimento'], '%Y-%m-%d').date()
                    except:
                        data_nasc_atual = None

                    st.write("✏️ **Editar Dados**")
                    with st.form("ual"):
                        c1, c2 = st.columns([3, 1])
                        nm = c1.text_input("Nome", value=d['nome'])
                        # Adicionado format="DD/MM/YYYY"
                        nas = c2.date_input("Nascimento", value=data_nasc_atual, format="DD/MM/YYYY")
                        
                        c3, c4, c5 = st.columns(3)
                        ser = c3.text_input("Série", value=d['serie'] if d['serie'] else "")
                        tr = c4.text_input("Turma", value=d['turma'])
                        
                        turnos = ["Matutino", "Vespertino", "Integral"]
                        idx_t = turnos.index(d['turno']) if d['turno'] in turnos else 0
                        tur = c5.selectbox("Turno", turnos, index=idx_t)
                        
                        em = st.text_input("E-mail", value=d['email'] if d['email'] else "")
                        
                        c6, c7, c8 = st.columns(3)
                        t1 = c6.text_input("Tel 1", value=d['telefone1'] if d['telefone1'] else "")
                        t2 = c7.text_input("Tel 2", value=d['telefone2'] if d['telefone2'] else "")
                        t3 = c8.text_input("Tel 3", value=d['telefone3'] if d['telefone3'] else "")
                        
                        sl = st.number_input("Saldo (R$)", value=float(d['saldo']))
                        
                        if st.form_submit_button("CONFIRMAR ALTERAÇÕES"):
                            nas_str = str(nas) if nas else None
                            update_aluno_manual(id_a, nm, ser, tr, tur, nas_str, em, t1, t2, t3, sl)
                            st.success("Dados atualizados!")
                            st.rerun()
                else:
                    st.warning("Sem alunos cadastrados.")

            elif act=="EXCLUIR ALUNO":
                df=get_all_alunos()
                if not df.empty:
                    df=df.sort_values('nome'); df['l']=df['nome']+" | "+df['turma']; s=st.selectbox("Excluir:",df['l'].unique()); id=int(df[df['l']==s].iloc[0]['id'])
                    if st.button("❌ CONFIRMAR EXCLUSÃO"): delete_aluno_db(id); st.success("Excluído!"); st.rerun()
            elif act=="EXCLUIR TURMA":
                df=get_all_alunos()
                if not df.empty:
                    t=st.selectbox("Turma",sorted(df['turma'].dropna().unique()))
                    if st.button("🧨 APAGAR TURMA"): cnt=delete_turma_db(t); st.success(f"{cnt} excluídos."); st.rerun()

    # --- RECARGA ---
    if menu == 'recarga':
        st.markdown("---"); st.subheader("💰 Recarga")
        c1,c2=st.columns(2)
        if c1.button("📝 MANUAL (Todas Opções)",use_container_width=True): st.session_state['rec_mode']='manual'; st.session_state['pix_data']=None
        if c2.button("💠 PIX (QR CODE)",use_container_width=True): st.session_state['rec_mode']='pix'; st.session_state['pix_data']=None

        df=get_all_alunos()
        if not df.empty:
            df=df.sort_values('nome'); df['l']=df['nome']+" | "+df['turma']; s=st.selectbox("Aluno",df['l'].unique()); id_a=int(df[df['l']==s].iloc[0]['id'])
            
            if st.session_state.get('rec_mode')=='manual':
                st.info("Recarga Manual (Dinheiro, Cartão, Transferência)")
                with st.form("rman"):
                    v=st.number_input("Valor R$",0.0,step=5.0); m=st.selectbox("Forma",["DINHEIRO", "PIX (MANUAL)", "DÉBITO", "CRÉDITO"])
                    if st.form_submit_button("CONFIRMAR") and v>0: registrar_recarga(id_a,v,m); st.success("Sucesso!"); st.rerun()
            
            elif st.session_state.get('rec_mode')=='pix':
                st.info("Gerar QR Code Estático")
                v=st.number_input("Valor Pix",0.0,step=5.0)
                if v>0:
                    pix = PixPayload(CHAVE_PIX_ESCOLA, NOME_BENEFICIARIO, CIDADE_BENEFICIARIO, v)
                    payload = pix.gerar_payload()
                    st.markdown("---")
                    c_qr, c_txt = st.columns([1, 2])
                    with c_qr: st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={payload}", caption="Ler no App do Banco")
                    with c_txt: st.code(payload); st.warning("Confira o comprovante.")
                    if st.button("✅ CONFIRMAR PIX"): registrar_recarga(id_a, v, "PIX (QR)"); st.success("Creditado!"); st.rerun()
        else: st.warning("Sem alunos.")

    # --- COMPRAR ---
    if menu == 'comprar':
        st.markdown("---"); st.subheader("🛒 Venda")
        if not st.session_state.get('modo'):
            c1,c2=st.columns(2)
            if c1.button("🔍 ALUNO",use_container_width=True): st.session_state['modo']='aluno'
            if c2.button("🏫 TURMA",use_container_width=True): st.session_state.update(modo='turma', res_tur=False)
        
        if st.session_state.get('modo')=='aluno':
            if st.button("⬅️ Voltar"): st.session_state['modo']=None; st.rerun()
            df=get_all_alunos()
            if not df.empty:
                df=df.sort_values('nome'); df['l']=df['nome']+" | "+df['turma']; s=st.selectbox("Aluno",df['l'].unique()); idx=int(df[df['l']==s].iloc[0]['id'])
                realizar_venda_form(idx)
        
        elif st.session_state.get('modo')=='turma':
            if not st.session_state.get('t_sel'):
                if st.button("⬅️ Voltar"): st.session_state['modo']=None; st.rerun()
                df=get_all_alunos()
                if not df.empty:
                    t=st.selectbox("Turma",sorted(df['turma'].dropna().unique()))
                    if st.button("ABRIR"): st.session_state.update(t_sel=t, res_tur=False); st.rerun()
            else:
                tur=st.session_state['t_sel']
                if st.session_state.get('res_tur'):
                    st.markdown(f"### Resumo: {tur}"); res=get_vendas_hoje_turma(tur)
                    if not res.empty: st.dataframe(res,hide_index=True,use_container_width=True); st.markdown(f"**Total: R$ {res['valor_total'].sum():.2f}**")
                    c1,c2=st.columns(2)
                    if c1.button("✅ FECHAR"): st.session_state.update(t_sel=None, aid_venda=None, res_tur=False, modo=None); st.rerun()
                    if c2.button("⬅️ Voltar"): st.session_state['res_tur']=False; st.rerun()
                else:
                    c1,c2=st.columns([3,1]); c1.markdown(f"### {tur}"); 
                    if c2.button("🏁 ENCERRAR"): st.session_state['res_tur']=True; st.rerun()
                    if not st.session_state.get('aid_venda'):
                        df=get_alunos_por_turma(tur); h1,h2,h3=st.columns([3,1,1]); h1.write("Nome"); h2.write("Saldo"); h3.write("Ação")
                        for i,r in df.iterrows():
                            c1,c2,c3=st.columns([3,1,1]); c1.write(r['nome']); c2.markdown(f"<span style='color:{'green' if r['saldo']>=0 else 'red'}'>{r['saldo']:.2f}</span>",unsafe_allow_html=True)
                            if c3.button("VENDER",key=r['id']): st.session_state['aid_venda']=r['id']; st.rerun()
                            st.markdown("<hr style='margin:5px 0'>",unsafe_allow_html=True)
                    else:
                        if st.button("⬅️ Cancelar"): st.session_state['aid_venda']=None; st.rerun()
                        realizar_venda_form(st.session_state['aid_venda'],True)

    # --- HISTÓRICO ---
    if menu == 'hist':
        st.markdown("---"); st.subheader("📜 Extrato")
        if not st.session_state.get('hist_id'):
            df=get_all_alunos()
            if not df.empty:
                df=df.sort_values('nome'); df['l']=df['nome']+" | "+df['turma']; s=st.selectbox("Aluno",df['l'].unique())
                if st.button("VER"): st.session_state['hist_id']=int(df[df['l']==s].iloc[0]['id']); st.rerun()
        else:
            if st.button("⬅️ Voltar"): st.session_state['hist_id']=None; st.rerun()
            conn=sqlite3.connect(DB_FILE); conn.row_factory=sqlite3.Row; c=conn.cursor(); c.execute("SELECT * FROM alunos WHERE id=?",(st.session_state['hist_id'],)); al=c.fetchone(); conn.close()
            st.markdown(f"<div style='background:#f0f2f6;padding:20px;text-align:center'><h3>{al['nome']}</h3><h1>R$ {al['saldo']:.2f}</h1></div>",unsafe_allow_html=True)
            f=st.selectbox("Filtro",["7 DIAS","30 DIAS","TODOS"]); m={"7 DIAS":7,"30 DIAS":30,"TODOS":"TODOS"}
            if st.button("EXIBIR"):
                ext=get_extrato_aluno(al['id'],m[f])
                if not ext.empty: st.dataframe(ext.style.map(lambda v:f"color:{'red' if v<0 else 'green'}",subset=['Valor']),hide_index=True,use_container_width=True)
                else: st.info("Vazio.")

    # --- RELATÓRIOS ---
    if menu == 'relatorios':
        st.markdown("---"); st.subheader("📊 Relatórios")
        
        data_sel = st.date_input("Data:", datetime.now(), format="DD/MM/YYYY")
        d_str = data_sel.strftime("%d/%m/%Y")
        st.write(f"Filtrando por: **{d_str}**"); st.markdown("---")
        
        c1, c2 = st.columns(2)
        if c1.button("📦 PRODUTOS", use_container_width=True): st.session_state['rel_mode'] = 'produtos'
        if c2.button("👥 ALUNOS", use_container_width=True): st.session_state['rel_mode'] = 'alunos'

        if st.session_state.get('rel_mode') == 'produtos':
            df_p, tot = get_relatorio_produtos(d_str)
            if not df_p.empty:
                st.metric("Total do Dia (Estimado)", f"R$ {tot:.2f}")
                st.dataframe(df_p, column_config={"Valor Total (R$)": st.column_config.NumberColumn(format="R$ %.2f")}, hide_index=True, use_container_width=True)
            else: st.info("Nada vendido.")
        
        elif st.session_state.get('rel_mode') == 'alunos':
            df_a = get_relatorio_alunos_dia(d_str)
            if not df_a.empty:
                st.dataframe(df_a, column_config={"Valor": st.column_config.NumberColumn(format="R$ %.2f")}, hide_index=True, use_container_width=True)
            else: st.info("Nada vendido.")

def realizar_venda_form(aid,mode=False):
    conn=sqlite3.connect(DB_FILE); conn.row_factory=sqlite3.Row; c=conn.cursor(); c.execute("SELECT * FROM alunos WHERE id=?",(aid,)); al=c.fetchone(); conn.close()
    st.markdown(f"**{al['nome']}** | Saldo: R$ {al['saldo']:.2f}"); df=get_all_alimentos()
    if df.empty: st.warning("Sem produtos"); return
    fr=get_historico_preferencias(aid); df['f']=df['nome'].map(fr).fillna(0); df=df.sort_values(['f','nome'],ascending=[False,True]); 
    if 'tipo' not in df: df['tipo']='ALIMENTO'
    with st.form("v"):
        qs={}
        for tp in ["BEBIDA","ALIMENTO"]:
            sub=df[df['tipo']==tp] if tp=="BEBIDA" else df[df['tipo']!="BEBIDA"]
            if not sub.empty:
                st.write(f"**{tp}S**")
                for i,r in sub.iterrows():
                    c1,c2,c3=st.columns([3,1,1]); c1.write(f"⭐ {r['nome']}" if r['f']>0 else r['nome']); c2.write(f"{r['valor']:.2f}"); qs[r['id']]=c3.number_input("Q",0,step=1,key=f"q{r['id']}",label_visibility="collapsed")
        if st.form_submit_button("✅"):
            t=0; its=[]
            for i,q in qs.items():
                if q>0: it=df[df['id']==i].iloc[0]; t+=it['valor']*q; its.append(f"{q}x {it['nome']}")
            if t>0: update_saldo_aluno(aid,al['saldo']-t); registrar_venda(aid,", ".join(its),t); st.success("OK!"); st.session_state['aid_venda']=None if mode else None; st.rerun()
            else: st.warning("Selecione algo.")

if st.session_state['logado']: main_menu()
else: login_screen()
