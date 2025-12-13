import streamlit as st
import pandas as pd
import sqlite3
import shutil
import os
import binascii
from datetime import datetime, timedelta
from collections import Counter

# --- Configuração da Página ---
st.set_page_config(page_title="Cantina Peixinho Dourado", layout="centered")

# ==========================================
#    CONFIGURAÇÃO DO PIX (ATUALIZADO)
# ==========================================
CHAVE_PIX_ESCOLA = "flaviovilhena@gmail.com" 
NOME_BENEFICIARIO = "FLAVIO SILVA"  # <--- Atualizado conforme solicitado
CIDADE_BENEFICIARIO = "MANAUS" 
# ==========================================

# --- Configuração do Banco de Dados (SQLite) ---
DB_FILE = 'cantina.db'

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Tabelas (Alunos, Alimentos, Transacoes, Recargas)
    c.execute('''CREATE TABLE IF NOT EXISTS alunos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, serie TEXT, turma TEXT, turno TEXT, nascimento TEXT, email TEXT, telefone1 TEXT, telefone2 TEXT, telefone3 TEXT, saldo REAL)''')
    try: c.execute("ALTER TABLE alunos ADD COLUMN telefone3 TEXT")
    except: pass

    c.execute('''CREATE TABLE IF NOT EXISTS alimentos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, valor REAL, tipo TEXT)''')
    try: 
        c.execute("ALTER TABLE alimentos ADD COLUMN tipo TEXT")
        c.execute("UPDATE alimentos SET tipo = 'ALIMENTO' WHERE tipo IS NULL")
    except: pass

    c.execute('''CREATE TABLE IF NOT EXISTS transacoes (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_id INTEGER, itens TEXT, valor_total REAL, data_hora TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS recargas (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_id INTEGER, valor REAL, data_hora TEXT, metodo_pagamento TEXT)''')
    try: c.execute("ALTER TABLE recargas ADD COLUMN metodo_pagamento TEXT")
    except: pass

    conn.commit()
    conn.close()

# --- CLASSE PARA GERAR O PAYLOAD PIX (PADRÃO BANCO CENTRAL) ---
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
            self._fmt("26", 
                self._fmt("00", "BR.GOV.BCB.PIX") + 
                self._fmt("01", self.chave)
            ) +
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
    c.execute("INSERT INTO transacoes (aluno_id, itens, valor_total, data_hora) VALUES (?, ?, ?, ?)", (aluno_id, itens_str, valor_total, data_hora))
    conn.commit()
    conn.close()

def registrar_recarga(aluno_id, valor, metodo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    data_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    c.execute("INSERT INTO recargas (aluno_id, valor, data_hora, metodo_pagamento) VALUES (?, ?, ?, ?)", (aluno_id, valor, data_hora, metodo))
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

# --- FUNÇÕES DE ALIMENTOS ---
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

# --- FUNÇÕES ALUNOS ---
def upsert_aluno(nome, serie, turma, turno, nasck, email, tel1, tel2, tel3, saldo_inicial):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor(); c.execute("SELECT id FROM alunos WHERE nome = ?", (nome,))
    data = c.fetchone(); action = ""
    if data:
        c.execute('UPDATE alunos SET turma=?, email=?, telefone1=?, telefone2=?, telefone3=? WHERE nome=?', (turma, email, tel1, tel2, tel3, nome)); action = "atualizado"
    else:
        c.execute('INSERT INTO alunos (nome, serie, turma, turno, nascimento, email, telefone1, telefone2, telefone3, saldo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (nome, serie, turma, turno, str(nasck), email, tel1, tel2, tel3, saldo_inicial)); action = "novo"
    conn.commit(); conn.close(); return action
def update_aluno_manual(id, nome, serie, turma, turno, email, t1, t2, t3, saldo):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor(); c.execute('UPDATE alunos SET nome=?, serie=?, turma=?, turno=?, email=?, telefone1=?, telefone2=?, telefone3=?, saldo=? WHERE id=?', (nome, serie, turma, turno, email, t1, t2, t3, saldo, id)); conn.commit(); conn.close()
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
    st.sidebar.title("Menu")
    st.sidebar.subheader("💾 Backup")
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "rb") as fp: st.sidebar.download_button("⬇️ BAIXAR DADOS", fp, "backup_cantina.db", "application/x-sqlite3")
    up_db = st.sidebar.file_uploader("⬆️ RESTAURAR", type=["db", "sqlite3"])
    if up_db and st.sidebar.button("CONFIRMAR RESTAURAÇÃO"):
        with open(DB_FILE, "wb") as f: f.write(up_db.getbuffer())
        st.sidebar.success("Restaurado!"); st.rerun()
    st.sidebar.markdown("---")
    if st.sidebar.button("Sair"): st.session_state['logado'] = False; st.session_state['menu_atual'] = None; st.rerun()

    st.header("Painel Principal")
    st.write("Usuário logado: fvilhena")
    
    col1, col2 = st.columns(2); col3, col4 = st.columns(2)
    with col1: 
        if st.button("CADASTRO", use_container_width=True): st.session_state.update(menu_atual='cadastro', submenu=None)
    with col2: 
        if st.button("COMPRAR REFEIÇÃO", use_container_width=True): st.session_state.update(menu_atual='comprar', modo_compra=None, turma_selecionada=None, aluno_compra_id=None, resumo_turma=False)
    with col3: 
        if st.button("SALDO/HISTÓRICO", use_container_width=True): st.session_state.update(menu_atual='historico', hist_aluno_id=None)
    with col4: 
        if st.button("RECARGA", use_container_width=True): st.session_state.update(menu_atual='recarga', modo_recarga=None)

    # --- MENU CADASTRO ---
    if st.session_state.get('menu_atual') == 'cadastro':
        st.markdown("---"); st.subheader("Menu de Cadastro")
        c1, c2 = st.columns(2)
        if c1.button("USUÁRIO", use_container_width=True): st.session_state['submenu'] = 'usuario'
        if c2.button("ALIMENTOS", use_container_width=True): st.session_state['submenu'] = 'alimentos'

        if st.session_state.get('submenu') == 'alimentos':
            act = st.radio("Ação:", ["NOVO ALIMENTO", "ALTERAR ALIMENTO", "EXCLUIR ALIMENTO"], horizontal=True); st.markdown("---"); df = get_all_alimentos()
            if act == "NOVO ALIMENTO":
                with st.form("new_ali"):
                    n = st.text_input("Nome"); v = st.number_input("Valor", 0.0, step=0.5); t = st.selectbox("Tipo", ["ALIMENTO", "BEBIDA"])
                    if st.form_submit_button("CADASTRAR"): add_alimento_db(n, v, t); st.success("Sucesso!"); st.rerun()
                if not df.empty: st.dataframe(df[['nome', 'valor', 'tipo']], hide_index=True)
            elif act == "ALTERAR ALIMENTO" and not df.empty:
                df['lbl'] = df['id'].astype(str) + " - " + df['nome']; sel = st.selectbox("Item:", df['lbl'].unique()); id_sel = int(sel.split(' - ')[0]); d = df[df['id']==id_sel].iloc[0]
                with st.form("edit_ali"):
                    nn = st.text_input("Nome", d['nome']); nv = st.number_input("Valor", value=float(d['valor'])); nt = st.selectbox("Tipo", ["ALIMENTO", "BEBIDA"], index=["ALIMENTO", "BEBIDA"].index(d['tipo'] if d['tipo'] in ["ALIMENTO", "BEBIDA"] else "ALIMENTO"))
                    if st.form_submit_button("SALVAR"): update_alimento_db(id_sel, nn, nv, nt); st.success("Salvo!"); st.rerun()
            elif act == "EXCLUIR ALIMENTO" and not df.empty:
                df['lbl'] = df['id'].astype(str) + " - " + df['nome']; sel = st.selectbox("Excluir:", df['lbl'].unique()); id_sel = int(sel.split(' - ')[0])
                if st.button("❌ CONFIRMAR"): delete_alimento_db(id_sel); st.success("Apagado!"); st.rerun()

        if st.session_state.get('submenu') == 'usuario':
            opt = st.radio("Ação:", ["IMPORTAR CSV", "NOVO ALUNO", "ATUALIZAR ALUNO", "EXCLUIR ALUNO", "EXCLUIR TURMA"]); st.markdown("---")
            if opt == "IMPORTAR CSV":
                up = st.file_uploader("CSV", type=['csv'])
                if up and st.button("ENVIAR"):
                    try:
                        df = pd.read_csv(up, sep=None, engine='python', encoding='latin1')
                        for c in df.select_dtypes(include=['object']): df[c] = df[c].astype(str).str.replace('1Â','1o',regex=False).str.replace('Ã¢','â',regex=False).str.replace('Ãº','ú',regex=False).str.replace('Ã£','ã',regex=False).str.replace('Ã©','é',regex=False).str.replace('Ã¡','á',regex=False).str.replace('Ã³','ó',regex=False).str.replace('Ã','í',regex=False).str.replace('°','',regex=False)
                        n, a, bar = 0, 0, st.progress(0)
                        for i, r in df.iterrows():
                            t1, t2, t3 = None, None, None
                            if 'Telefones' in r and pd.notna(r['Telefones']): 
                                p = str(r['Telefones']).split(' / '); t1=p[0] if len(p)>0 else None; t2=p[1] if len(p)>1 else None; t3=p[2] if len(p)>2 else None
                            nas = pd.to_datetime(r['Data de Nascimento'], dayfirst=True).date() if 'Data de Nascimento' in r and pd.notna(r['Data de Nascimento']) else None
                            if upsert_aluno(r.get('Aluno',''), '', r.get('Turma',''), '', nas, r.get('E-mail',''), t1, t2, t3, 0.0) == "novo": n+=1
                            else: a+=1
                            bar.progress((i+1)/len(df))
                        st.success(f"{n} novos, {a} atualizados.")
                    except Exception as e: st.error(f"Erro: {e}")
            elif opt == "NOVO ALUNO":
                with st.form("nal"):
                    nm = st.text_input("Nome"); tr = st.text_input("Turma"); sl = st.number_input("Saldo", 0.0)
                    if st.form_submit_button("SALVAR"): upsert_aluno(nm, '', tr, '', None, '', None, None, None, sl); st.success("Salvo!")
            elif opt == "ATUALIZAR ALUNO":
                df = get_all_alunos()
                if not df.empty:
                    df = df.sort_values(by='nome'); df['lbl'] = df['id'].astype(str) + " - " + df['nome']; sel = st.selectbox("Aluno:", df['lbl'].unique()); id_a = int(sel.split(' - ')[0]); d = df[df['id']==id_a].iloc[0]
                    with st.form("ual"):
                        nm = st.text_input("Nome", d['nome']); tr = st.text_input("Turma", d['turma']); sl = st.number_input("Saldo", value=float(d['saldo']))
                        if st.form_submit_button("ATUALIZAR"): update_aluno_manual(id_a, nm, d['serie'], tr, d['turno'], d['email'], d['telefone1'], d['telefone2'], d['telefone3'], sl); st.success("Feito!"); st.rerun()
            elif opt == "EXCLUIR ALUNO":
                df = get_all_alunos()
                if not df.empty:
                    df = df.sort_values(by='nome'); df['lbl'] = df['nome'] + " | " + df['turma'].astype(str); sel = st.selectbox("Excluir:", df['lbl'].unique()); id_d = int(df[df['lbl']==sel].iloc[0]['id'])
                    if st.button("❌ CONFIRMAR EXCLUSÃO"): delete_aluno_db(id_d); st.success("Excluído!"); st.rerun()
            elif opt == "EXCLUIR TURMA":
                df = get_all_alunos()
                if not df.empty:
                    t_del = st.selectbox("Turma:", sorted(df['turma'].dropna().astype(str).unique()))
                    if st.button("🧨 APAGAR TURMA"): cnt = delete_turma_db(t_del); st.success(f"{cnt} excluídos."); st.rerun()

    # --- MENU RECARGA ---
    if st.session_state.get('menu_atual') == 'recarga':
        st.markdown("---"); st.subheader("💰 Recarga de Créditos")
        c1, c2 = st.columns(2)
        if c1.button("📝 MANUAL", use_container_width=True): st.session_state['modo_recarga'] = 'manual'
        if c2.button("💠 PIX (QR CODE)", use_container_width=True): st.session_state['modo_recarga'] = 'pix'

        df = get_all_alunos()
        if df.empty: st.warning("Sem alunos."); st.stop()
        df = df.sort_values(by='nome'); df['lbl'] = df['nome'] + " | " + df['turma'].astype(str)
        
        if st.session_state.get('modo_recarga') == 'manual':
            st.info("Recarga Manual")
            sel = st.selectbox("Aluno:", df['lbl'].unique()); id_a = int(df[df['lbl']==sel].iloc[0]['id'])
            with st.form("frm_man"):
                v = st.number_input("Valor R$", 0.0, step=5.0); m = st.selectbox("Forma", ["DINHEIRO", "PIX", "DÉBITO", "CRÉDITO"])
                if st.form_submit_button("✅ CONFIRMAR"): 
                    if v>0: registrar_recarga(id_a, v, m); st.success("Recarga efetuada!"); st.rerun()
        
        elif st.session_state.get('modo_recarga') == 'pix':
            st.info("Gerar QR Code Pix (Copia e Cola)")
            sel = st.selectbox("Aluno:", df['lbl'].unique()); id_a = int(df[df['lbl']==sel].iloc[0]['id'])
            v = st.number_input("Valor R$", 0.0, step=5.0)
            if v > 0:
                pix = PixPayload(CHAVE_PIX_ESCOLA, NOME_BENEFICIARIO, CIDADE_BENEFICIARIO, v)
                payload = pix.gerar_payload()
                st.markdown("---")
                c_qr, c_txt = st.columns([1, 2])
                with c_qr: st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={payload}", caption="Escaneie no App do Banco")
                with c_txt: st.write("**Pix Copia e Cola:**"); st.code(payload, language="text"); st.warning("Confira o comprovante antes de liberar.")
                if st.button("✅ CONFIRMAR RECEBIMENTO (PIX)"): registrar_recarga(id_a, v, "PIX (QR)"); st.success(f"Crédito de R$ {v:.2f} liberado!"); st.rerun()

    # --- MENU COMPRAR ---
    if st.session_state.get('menu_atual') == 'comprar':
        st.markdown("---"); st.subheader("🛒 Venda de Refeição")
        if not st.session_state.get('modo_compra'):
            c1, c2 = st.columns(2)
            if c1.button("🔍 POR ALUNO", use_container_width=True): st.session_state['modo_compra'] = 'aluno'
            if c2.button("🏫 POR TURMA", use_container_width=True): st.session_state.update(modo_compra='turma', resumo_turma=False)

        if st.session_state.get('modo_compra') == 'aluno':
            if st.button("⬅️ Voltar"): st.session_state['modo_compra'] = None; st.rerun()
            df = get_all_alunos()
            if not df.empty:
                df = df.sort_values(by='nome'); df['lbl'] = df['nome'] + " | " + df['turma'].astype(str)
                sel = st.selectbox("Aluno:", df['lbl'].unique()); idx = int(df[df['lbl']==sel].iloc[0]['id'])
                realizar_venda_form(idx)
            else: st.warning("Sem alunos.")

        elif st.session_state.get('modo_compra') == 'turma':
            if not st.session_state.get('turma_selecionada'):
                if st.button("⬅️ Voltar"): st.session_state['modo_compra'] = None; st.rerun()
                df = get_all_alunos()
                if not df.empty:
                    t = st.selectbox("Turma:", sorted(df['turma'].dropna().astype(str).unique()))
                    if st.button("ABRIR"): st.session_state.update(turma_selecionada=t, resumo_turma=False); st.rerun()
            else:
                turma = st.session_state['turma_selecionada']
                if st.session_state.get('resumo_turma'):
                    st.markdown(f"### Conferência: {turma}")
                    res = get_vendas_hoje_turma(turma)
                    if not res.empty:
                        st.dataframe(res, hide_index=True, use_container_width=True)
                        st.markdown(f"**Total Hoje: R$ {res['valor_total'].sum():.2f}**")
                    else: st.warning("Sem vendas hoje.")
                    c1, c2 = st.columns(2)
                    if c1.button("✅ FECHAR TURMA"): st.session_state.update(turma_selecionada=None, aluno_compra_id=None, resumo_turma=False, modo_compra=None); st.rerun()
                    if c2.button("⬅️ Voltar"): st.session_state['resumo_turma'] = False; st.rerun()
                else:
                    c1, c2 = st.columns([3, 1]); c1.markdown(f"### {turma}"); 
                    if c2.button("🏁 ENCERRAR"): st.session_state['resumo_turma'] = True; st.rerun()
                    
                    if not st.session_state.get('aluno_compra_id'):
                        df = get_alunos_por_turma(turma)
                        h1, h2, h3 = st.columns([3,1,1]); h1.write("**Nome**"); h2.write("**Saldo**"); h3.write("**Ação**")
                        for i, r in df.iterrows():
                            c1, c2, c3 = st.columns([3,1,1]); c1.write(r['nome']); c2.markdown(f"<span style='color:{'green' if r['saldo']>=0 else 'red'}'>R$ {r['saldo']:.2f}</span>", unsafe_allow_html=True)
                            if c3.button("VENDER", key=r['id']): st.session_state['aluno_compra_id'] = r['id']; st.rerun()
                            st.markdown("<hr style='margin:5px 0'>", unsafe_allow_html=True)
                    else:
                        if st.button("⬅️ Cancelar"): st.session_state['aluno_compra_id'] = None; st.rerun()
                        realizar_venda_form(st.session_state['aluno_compra_id'], True)

    # --- MENU HISTÓRICO ---
    if st.session_state.get('menu_atual') == 'historico':
        st.markdown("---"); st.subheader("📜 Extrato")
        if not st.session_state.get('hist_aluno_id'):
            df = get_all_alunos()
            if not df.empty:
                df = df.sort_values(by='nome'); df['lbl'] = df['nome'] + " | " + df['turma'].astype(str)
                sel = st.selectbox("Aluno:", df['lbl'].unique())
                if st.button("VER EXTRATO"): st.session_state['hist_aluno_id'] = int(df[df['lbl']==sel].iloc[0]['id']); st.rerun()
        else:
            if st.button("⬅️ Voltar"): st.session_state['hist_aluno_id'] = None; st.rerun()
            conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; c = conn.cursor(); c.execute("SELECT * FROM alunos WHERE id=?",(st.session_state['hist_aluno_id'],)); al=c.fetchone(); conn.close()
            st.markdown(f"<div style='background:#f0f2f6;padding:20px;text-align:center;border-radius:10px'><h3>{al['nome']}</h3><p>Saldo Atual</p><h1 style='color:{'green' if al['saldo']>=0 else 'red'}'>R$ {al['saldo']:.2f}</h1></div>", unsafe_allow_html=True)
            filt = st.selectbox("Filtro:", ["7 DIAS", "30 DIAS", "60 DIAS", "TODOS"])
            mapa = {"7 DIAS":7, "30 DIAS":30, "60 DIAS":60, "TODOS":"TODOS"}
            if st.button("EXIBIR"):
                ext = get_extrato_aluno(al['id'], mapa[filt])
                if not ext.empty: 
                    st.dataframe(ext.style.map(lambda v: f"color:{'red' if v<0 else 'green'};font-weight:bold", subset=['Valor']).format({"Valor":"R$ {:.2f}"}), hide_index=True, use_container_width=True)
                else: st.info("Sem dados.")

def realizar_venda_form(aid, mode=False):
    conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; c = conn.cursor(); c.execute("SELECT * FROM alunos WHERE id=?",(aid,)); al=c.fetchone(); conn.close()
    if not al: st.error("Erro"); return
    st.markdown(f"<div style='padding:10px;background:#f0f2f6;border-radius:5px'><h4>👤 {al['nome']}</h4><h2 style='color:{'green' if al['saldo']>=0 else 'red'}'>Saldo: R$ {al['saldo']:.2f}</h2></div>", unsafe_allow_html=True)
    
    dfa = get_all_alimentos()
    if dfa.empty: st.warning("Sem produtos."); return
    
    # Inteligência + Ordenação
    freq = get_historico_preferencias(aid)
    dfa['freq'] = dfa['nome'].map(freq).fillna(0)
    dfa = dfa.sort_values(by=['freq', 'nome'], ascending=[False, True])
    if 'tipo' not in dfa.columns: dfa['tipo'] = 'ALIMENTO'
    
    with st.form("venda"):
        qtds = {}
        for tp, icon in [("BEBIDA", "🥤"), ("ALIMENTO", "🥪")]:
            sub = dfa[dfa['tipo'] == tp] if tp=="BEBIDA" else dfa[dfa['tipo'] != "BEBIDA"]
            if not sub.empty:
                st.markdown(f"### {icon} {tp}s")
                for i, r in sub.iterrows():
                    c1, c2, c3 = st.columns([3,1,1])
                    c1.write(f"⭐ {r['nome']}" if r['freq']>0 else r['nome'])
                    c2.write(f"R$ {r['valor']:.2f}")
                    qtds[r['id']] = c3.number_input("Qtd", 0, step=1, key=f"q_{r['id']}", label_visibility="collapsed")
                    st.markdown("<hr style='margin:0 0 5px 0'>", unsafe_allow_html=True)
        
        if st.form_submit_button("✅ CONFIRMAR"):
            total, itens = 0.0, []
            for i, q in qtds.items():
                if q > 0:
                    it = dfa[dfa['id']==i].iloc[0]; total += it['valor'] * q
                    itens.append(f"{q}x {it['nome']}")
            if total > 0:
                update_saldo_aluno(aid, al['saldo'] - total)
                registrar_venda(aid, ", ".join(itens), total)
                st.success(f"Venda R$ {total:.2f} OK!"); 
                if mode: st.session_state['aluno_compra_id'] = None
                st.rerun()
            else: st.warning("Selecione algo.")

if st.session_state['logado']: main_menu()
else: login_screen()
