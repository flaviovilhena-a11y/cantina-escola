import streamlit as st
import pandas as pd
import sqlite3
import shutil
import os
import binascii
import time
import requests
import threading
import streamlit.components.v1 as components
from datetime import datetime, timedelta, date
from collections import Counter
from fpdf import FPDF

# --- Configuração da Página ---
st.set_page_config(page_title="Cantina Peixinho Dourado", layout="centered")

# ==========================================
#    CONFIGURAÇÃO DO BREVO (E-MAIL)
# ==========================================
BREVO_API_KEY = "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"
EMAIL_REMETENTE = "cantina@peixinhodourado.g12.br" 
NOME_REMETENTE = "Cantina Peixinho Dourado"
# ==========================================

# ==========================================
#    CONFIGURAÇÃO DO PIX
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
    c.execute('''CREATE TABLE IF NOT EXISTS alunos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, serie TEXT, turma TEXT, turno TEXT, nascimento TEXT, email TEXT, telefone1 TEXT, telefone2 TEXT, telefone3 TEXT, saldo REAL)''')
    try: c.execute("ALTER TABLE alunos ADD COLUMN telefone3 TEXT")
    except: pass
    c.execute('''CREATE TABLE IF NOT EXISTS alimentos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, valor REAL, tipo TEXT)''')
    try: c.execute("ALTER TABLE alimentos ADD COLUMN tipo TEXT"); c.execute("UPDATE alimentos SET tipo = 'ALIMENTO' WHERE tipo IS NULL")
    except: pass
    c.execute('''CREATE TABLE IF NOT EXISTS transacoes (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_id INTEGER, itens TEXT, valor_total REAL, data_hora TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS recargas (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_id INTEGER, valor REAL, data_hora TEXT, metodo_pagamento TEXT, nsu TEXT)''')
    try: c.execute("ALTER TABLE recargas ADD COLUMN metodo_pagamento TEXT"); c.execute("ALTER TABLE recargas ADD COLUMN nsu TEXT")
    except: pass
    conn.commit(); conn.close()

# --- CLASSE PARA GERAR PDF TÉRMICO (80mm) ---
class PDFTermico(FPDF):
    def __init__(self, titulo, dados, modo="simples"):
        # Se modo for 'turmas', dados é um dicionário. Se 'simples', é um DataFrame.
        linhas = 0
        if modo == "turmas":
            for df in dados.values(): linhas += len(df) + 4 
        else:
            linhas = len(dados)
            
        altura_estimada = 40 + (linhas * 6)
        super().__init__(orientation='P', unit='mm', format=(80, altura_estimada))
        self.titulo = titulo
        self.dados = dados
        self.modo = modo
        self.set_margins(2, 2, 2)
        self.add_page()

    def header(self):
        self.set_font('Courier', 'B', 10)
        self.cell(0, 5, 'CANTINA PEIXINHO DOURADO', 0, 1, 'C')
        self.set_font('Courier', '', 8)
        self.cell(0, 4, 'Relatorio Gerencial', 0, 1, 'C')
        self.cell(0, 4, f'{datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'C')
        self.ln(2)
        self.cell(0, 0, border="T", ln=1)
        self.ln(2)
        self.set_font('Courier', 'B', 9)
        self.multi_cell(0, 4, self.titulo.upper(), 0, 'C')
        self.ln(2)

    def footer(self):
        self.set_y(-10)
        self.set_font('Courier', 'I', 6)
        self.cell(0, 4, 'Sistema de Gestao Escolar', 0, 0, 'C')

    def gerar_relatorio(self):
        if self.modo == "turmas":
            self._gerar_por_turma()
        else:
            self._gerar_simples()

    def _gerar_simples(self):
        self.set_font('Courier', 'B', 7)
        cols = self.dados.columns.tolist()
        largura_util = 76
        largura_col = largura_util / len(cols)
        
        for col in cols:
            self.cell(largura_col, 4, str(col)[:15], 0, 0, 'L')
        self.ln()
        
        self.set_font('Courier', '', 7)
        for index, row in self.dados.iterrows():
            for col in cols:
                valor = str(row[col])
                if isinstance(row[col], (int, float)) and ('Valor' in col or 'Total' in col):
                    valor = f"{row[col]:.2f}"
                self.cell(largura_col, 4, valor[:20], 0, 0, 'L')
            self.ln()
        self.ln(4)
        self.cell(0, 0, border="T", ln=1)

    def _gerar_por_turma(self):
        for turma, df in self.dados.items():
            self.set_font('Courier', 'B', 9)
            self.cell(0, 5, f"TURMA: {turma}", 0, 1, 'L')
            self.cell(0, 0, border="T", ln=1)
            
            self.set_font('Courier', 'B', 7)
            self.cell(60, 4, "PRODUTO", 0, 0, 'L')
            self.cell(16, 4, "QTD", 0, 1, 'R')
            
            self.set_font('Courier', '', 7)
            total_financeiro = 0.0
            
            for index, row in df.iterrows():
                produto = str(row['Produto'])
                if produto == "TOTAL TURMA":
                    total_financeiro = row['Total']
                    continue 
                qtd = str(row['Qtd'])
                self.cell(60, 4, produto[:30], 0, 0, 'L')
                self.cell(16, 4, qtd, 0, 1, 'R')
            
            self.ln(1)
            self.set_font('Courier', 'B', 8)
            self.cell(50, 5, "TOTAL VENDIDO:", 0, 0, 'R')
            self.cell(26, 5, f"R$ {total_financeiro:.2f}", 0, 1, 'R')
            
            self.ln(4)
            self.cell(0, 0, border="B", ln=1)
            self.ln(2)

# --- FUNÇÕES HELPER PARA DOWNLOAD PDF ---
def criar_botao_pdf_termico(dados, titulo_relatorio, modo="simples"):
    # CORREÇÃO DO ERRO: Validação correta se é DataFrame ou Dict
    vazio = False
    if isinstance(dados, pd.DataFrame):
        if dados.empty: vazio = True
    elif not dados: # Para dict ou None
        vazio = True
        
    if vazio: return

    try:
        pdf = PDFTermico(titulo_relatorio, dados, modo)
        pdf.gerar_relatorio()
        pdf_bytes = pdf.output(dest='S').encode('latin-1', 'ignore') 
        
        st.download_button(
            label="🧾 BAIXAR PDF TÉRMICO (Bematech)",
            data=pdf_bytes,
            file_name=f"cupom_{modo}_{int(time.time())}.pdf",
            mime="application/pdf",
            type="primary"
        )
    except Exception as e:
        st.error(f"Erro ao gerar PDF: {e}")

# --- FUNÇÃO DE ENVIO DE E-MAIL (THREAD) ---
def enviar_email_brevo_thread(email_destino, nome_aluno, assunto, mensagem_html):
    if not email_destino or "@" not in str(email_destino): return 
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"accept": "application/json", "api-key": BREVO_API_KEY, "content-type": "application/json"}
    payload = {
        "sender": {"name": NOME_REMETENTE, "email": EMAIL_REMETENTE},
        "to": [{"email": email_destino, "name": nome_aluno}],
        "subject": assunto,
        "htmlContent": f"<html><body><h3>Olá, responsável por {nome_aluno}!</h3><p>{mensagem_html}</p><hr><p style='font-size:12px; color:gray'>Aviso automático da Cantina Peixinho Dourado.</p></body></html>"
    }
    try: requests.post(url, json=payload, headers=headers)
    except: pass

def disparar_alerta(aluno_id, tipo, valor, detalhes):
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("SELECT nome, email, saldo FROM alunos WHERE id = ?", (aluno_id,)); dados = c.fetchone(); conn.close()
        if dados:
            nome, email, saldo_atual = dados
            if email and len(str(email)) > 5:
                msg = f"Uma <b>{tipo}</b> foi realizada.<br><br><b>Detalhes:</b> {detalhes}<br><b>Valor:</b> R$ {valor:.2f}<br><br><b>Saldo Atual:</b> R$ {saldo_atual:.2f}"
                threading.Thread(target=enviar_email_brevo_thread, args=(email, nome, f"🔔 Cantina: {tipo} R$ {valor:.2f}", msg)).start()
    except: pass

# --- CLASSE PIX ---
class PixPayload:
    def __init__(self, c, n, ci, v, t="***"): self.c,self.n,self.ci,self.v,self.t=c,n,ci,f"{v:.2f}",t
    def _f(self,i,v): return f"{i}{len(v):02}{v}"
    def _crc(self,p):
        c=0xFFFF; pl=0x1021
        for b in p.encode("utf-8"):
            c^=(b<<8); 
            for _ in range(8): c=(c<<1)^pl if c&0x8000 else c<<1
            c&=0xFFFF
        return f"{c:04X}"
    def gerar_payload(self):
        p=self._f("00","01")+self._f("26",self._f("00","BR.GOV.BCB.PIX")+self._f("01",self.c))+self._f("52","0000")+self._f("53","986")+self._f("54",self.v)+self._f("58","BR")+self._f("59",self.n)+self._f("60",self.ci)+self._f("62",self._f("05",self.t))+"6304"
        return p+self._crc(p)

# --- FUNÇÕES DB ---
def get_all_alunos(): conn=sqlite3.connect(DB_FILE); df=pd.read_sql_query("SELECT * FROM alunos",conn) if sqlite3.connect(DB_FILE) else pd.DataFrame(); conn.close(); return df
def get_alunos_por_turma(t): conn=sqlite3.connect(DB_FILE); df=pd.read_sql_query("SELECT * FROM alunos WHERE turma=? ORDER BY nome ASC",conn,params=(t,)); conn.close(); return df
def get_vendas_hoje_turma(t): conn=sqlite3.connect(DB_FILE); df=pd.read_sql_query("SELECT a.nome, t.itens, t.valor_total FROM transacoes t JOIN alunos a ON t.aluno_id=a.id WHERE a.turma=? AND t.data_hora LIKE ? ORDER BY t.id DESC",conn,params=(t,datetime.now().strftime("%d/%m/%Y")+"%")); conn.close(); return df
def get_historico_preferencias(aid):
    conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute("SELECT itens FROM transacoes WHERE aluno_id=? ORDER BY id DESC LIMIT 10",(aid,)); r=c.fetchall(); conn.close(); cnt=Counter()
    for row in r: 
        if row[0]: 
            for i in row[0].split(", "): 
                try: cnt[i.split("x ")[1]]+=int(i.split("x ")[0])
                except: pass
    return cnt

def update_saldo_aluno(id,s): conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute("UPDATE alunos SET saldo=? WHERE id=?",(s,id)); conn.commit(); conn.close()
def registrar_venda(aid,i,v): conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute("INSERT INTO transacoes (aluno_id,itens,valor_total,data_hora) VALUES (?,?,?,?)",(aid,i,v,datetime.now().strftime("%d/%m/%Y %H:%M:%S"))); conn.commit(); conn.close()
def registrar_recarga(aid,v,m,n=None): 
    conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute("INSERT INTO recargas (aluno_id,valor,data_hora,metodo_pagamento,nsu) VALUES (?,?,?,?,?)",(aid,v,datetime.now().strftime("%d/%m/%Y %H:%M:%S"),m,n))
    c.execute("SELECT saldo FROM alunos WHERE id=?",(aid,)); s=c.fetchone()[0]; c.execute("UPDATE alunos SET saldo=? WHERE id=?",(s+v,aid)); conn.commit(); conn.close()
def cancelar_venda_db(tid, aid, valor):
    conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute("DELETE FROM transacoes WHERE id = ?", (tid,)); c.execute("SELECT saldo FROM alunos WHERE id = ?", (aid,)); s=c.fetchone()[0]; c.execute("UPDATE alunos SET saldo = ? WHERE id = ?", (s + valor, aid)); conn.commit(); conn.close()

# --- FILTROS E RELATÓRIO ---
def calcular_data_corte(filtro):
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if filtro == "HOJE": return hoje
    elif filtro == "7 DIAS": return hoje - timedelta(days=7)
    elif filtro == "30 DIAS": return hoje - timedelta(days=30)
    return None

def get_extrato_aluno(aid, filtro):
    conn=sqlite3.connect(DB_FILE); c=conn.cursor()
    c.execute("SELECT data_hora,itens,valor_total FROM transacoes WHERE aluno_id=?",(aid,)); v=c.fetchall()
    c.execute("SELECT data_hora,valor,metodo_pagamento FROM recargas WHERE aluno_id=?",(aid,)); r=c.fetchall()
    dfp=pd.read_sql_query("SELECT nome,valor FROM alimentos",conn); preco_map=dict(zip(dfp['nome'],dfp['valor']))
    conn.close()
    
    dc = calcular_data_corte(filtro); ext = []
    
    for i in v: 
        dt=datetime.strptime(i[0],"%d/%m/%Y %H:%M:%S")
        if not dc or dt>=dc: 
            itens_str = i[1]; itens_com_preco = []
            if itens_str:
                for item in itens_str.split(", "):
                    try:
                        qtd, nome = item.split("x "); p_unit = preco_map.get(nome, 0.0); itens_com_preco.append(f"{qtd}x {nome} (R$ {p_unit:.2f})")
                    except: itens_com_preco.append(item)
            desc_final = ", ".join(itens_com_preco)
            ext.append({"Data":dt,"Tipo":"COMPRA","Detalhes":desc_final,"Valor":-i[2]})
            
    for i in r:
        dt=datetime.strptime(i[0],"%d/%m/%Y %H:%M:%S")
        if not dc or dt>=dc: ext.append({"Data":dt,"Tipo":"RECARGA","Detalhes":f"Via {i[2]}","Valor":i[1]})
        
    if ext: 
        df=pd.DataFrame(ext).sort_values("Data",ascending=False)
        df['Data']=df['Data'].apply(lambda x:x.strftime("%d/%m %H:%M"))
        return df
    return pd.DataFrame()

def get_vendas_cancelar(aid, filtro):
    conn=sqlite3.connect(DB_FILE); dc = calcular_data_corte(filtro)
    try:
        df = pd.read_sql_query("SELECT id, data_hora, itens, valor_total FROM transacoes WHERE aluno_id = ? ORDER BY id DESC", conn, params=(aid,))
        if not df.empty and dc:
            df['dt_obj'] = pd.to_datetime(df['data_hora'], format="%d/%m/%Y %H:%M:%S"); df = df[df['dt_obj'] >= dc]
    except: df = pd.DataFrame()
    conn.close(); return df

def get_relatorio_produtos(df):
    conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute("SELECT itens FROM transacoes WHERE data_hora LIKE ?",(f"{df}%",)); rs=c.fetchall(); dfp=pd.read_sql_query("SELECT nome,valor FROM alimentos",conn); pm=dict(zip(dfp['nome'],dfp['valor'])); conn.close(); qg=Counter()
    for r in rs:
        if r[0]: 
            for i in r[0].split(", "):
                try: qg[i.split("x ")[1]]+=int(i.split("x ")[0])
                except: pass
    dd=[]; td=0.0
    for n,q in qg.items(): v=pm.get(n,0.0)*q; td+=v; dd.append({"Produto":n,"Qtd Vendida":q,"Valor Total (R$)":v})
    if dd: return pd.DataFrame(dd).sort_values("Qtd Vendida",ascending=False),td
    return pd.DataFrame(),0.0

def get_relatorio_produtos_por_turma(data_filtro):
    conn = sqlite3.connect(DB_FILE)
    query = '''SELECT a.turma, t.itens FROM transacoes t JOIN alunos a ON t.aluno_id = a.id WHERE t.data_hora LIKE ? ORDER BY a.turma ASC'''
    try:
        rows = conn.execute(query, (f"{data_filtro}%",)).fetchall()
        dfp = pd.read_sql_query("SELECT nome,valor FROM alimentos", conn); preco_map = dict(zip(dfp['nome'], dfp['valor']))
    except: return {}
    conn.close()
    dados_turmas = {}
    for turma, itens in rows:
        if not turma: turma = "SEM TURMA"
        if turma not in dados_turmas: dados_turmas[turma] = Counter()
        if itens:
            for item in itens.split(", "):
                try:
                    parts = item.split("x "); qtd = int(parts[0]); nome = parts[1]; dados_turmas[turma][nome] += qtd
                except: pass
    resultados = {}
    for turma, contador in dados_turmas.items():
        lista_itens = []; total_turma = 0.0
        for nome, qtd in contador.items():
            valor_item = preco_map.get(nome, 0.0) * qtd; total_turma += valor_item; lista_itens.append({"Produto": nome, "Qtd": qtd, "Total": valor_item})
        if lista_itens:
            df = pd.DataFrame(lista_itens).sort_values("Produto")
            df = pd.concat([df, pd.DataFrame([{"Produto":"TOTAL TURMA", "Qtd":"", "Total": total_turma}])], ignore_index=True)
            resultados[turma] = df
    return resultados

def get_relatorio_alunos_dia(df):
    conn=sqlite3.connect(DB_FILE)
    try: 
        d=pd.read_sql_query("SELECT a.nome, t.itens, t.valor_total, t.data_hora FROM transacoes t JOIN alunos a ON t.aluno_id=a.id WHERE t.data_hora LIKE ? ORDER BY t.data_hora ASC",conn,params=(f"{df}%",))
        if not d.empty:
            d['Hora']=d['data_hora'].apply(lambda x:x.split(' ')[1]); d=d[['Hora','nome','itens','valor_total']]; d.columns=['Hora','Aluno','Produtos','Valor']
            d=pd.concat([d,pd.DataFrame([{'Hora':'','Aluno':'TOTAL GERAL','Produtos':'','Valor':d['Valor'].sum()}])],ignore_index=True)
    except: d=pd.DataFrame()
    conn.close(); return d

def get_relatorio_recargas_dia(df):
    conn = sqlite3.connect(DB_FILE)
    try:
        d = pd.read_sql_query("SELECT r.data_hora, a.nome, r.metodo_pagamento, r.valor FROM recargas r JOIN alunos a ON r.aluno_id = a.id WHERE r.data_hora LIKE ? ORDER BY r.data_hora ASC", conn, params=(f"{df}%",))
        if not d.empty:
            d['Hora'] = d['data_hora'].apply(lambda x: x.split(' ')[1]); d = d[['Hora', 'nome', 'metodo_pagamento', 'valor']]; d.columns = ['Hora', 'Aluno', 'Método', 'Valor']
            d = pd.concat([d, pd.DataFrame([{'Hora':'','Aluno':'TOTAL DO DIA','Método':'','Valor':d['Valor'].sum()}])], ignore_index=True)
    except: d = pd.DataFrame()
    conn.close(); return d

# --- FUNCIONALIDADE DE IMPRESSÃO (NOVA JANELA) ---
def acionar_impressao_js():
    st.components.v1.html(
        """<script>
        var w = window.open();
        w.document.write('<html><head><title>Relatorio</title>');
        w.document.write('<style>body{font-family:sans-serif;} table{width:100%;border-collapse:collapse;} th,td{border:1px solid #ddd;padding:8px;text-align:left;} tr:nth-child(even){background-color:#f2f2f2;} th{background-color:#04AA6D;color:white;}</style>');
        w.document.write('</head><body>');
        w.document.write(window.parent.document.getElementsByClassName('stDataFrame')[0].innerHTML);
        w.document.write('</body></html>');
        w.document.close();
        w.focus();
        setTimeout(function(){w.print();}, 1000);
        </script>""",
        height=0,
    )

# --- CRUD ---
def add_alimento_db(n,v,t): conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute('INSERT INTO alimentos (nome,valor,tipo) VALUES (?,?,?)',(n,v,t)); conn.commit(); conn.close()
def update_alimento_db(id,n,v,t): conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute('UPDATE alimentos SET nome=?,valor=?,tipo=? WHERE id=?',(n,v,t,id)); conn.commit(); conn.close()
def delete_alimento_db(id): conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute('DELETE FROM alimentos WHERE id=?',(id,)); conn.commit(); conn.close()
def get_all_alimentos(): conn=sqlite3.connect(DB_FILE); df=pd.read_sql_query("SELECT * FROM alimentos",conn); conn.close(); return df
def upsert_aluno(n,s,t,tu,nas,em,t1,t2,t3,sl):
    conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute("SELECT id FROM alunos WHERE nome=?",(n,)); d=c.fetchone(); ns=str(nas) if nas else None
    if d: c.execute('UPDATE alunos SET serie=?,turma=?,turno=?,nascimento=?,email=?,telefone1=?,telefone2=?,telefone3=? WHERE nome=?',(s,t,tu,ns,em,t1,t2,t3,n))
    else: c.execute('INSERT INTO alunos (nome,serie,turma,turno,nascimento,email,telefone1,telefone2,telefone3,saldo) VALUES (?,?,?,?,?,?,?,?,?,?)',(n,s,t,tu,ns,em,t1,t2,t3,sl))
    conn.commit(); conn.close()
def update_aluno_manual(id,n,s,t,tu,ns,em,t1,t2,t3,sl): conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute('UPDATE alunos SET nome=?,serie=?,turma=?,turno=?,nascimento=?,email=?,telefone1=?,telefone2=?,telefone3=?,saldo=? WHERE id=?',(n,s,t,tu,ns,em,t1,t2,t3,sl,id)); conn.commit(); conn.close()
def delete_aluno_db(id): conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute("DELETE FROM alunos WHERE id=?",(id,)); conn.commit(); conn.close()
def delete_turma_db(t): conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute("DELETE FROM alunos WHERE turma=?",(t,)); ct=c.rowcount; conn.commit(); conn.close(); return ct

init_db()
if 'logado' not in st.session_state: st.session_state['logado']=False

def login_screen():
    st.title("Cantina Peixinho Dourado"); u=st.text_input("Login")
    if st.button("Entrar"): 
        if u=="fvilhena": st.session_state['logado']=True; st.rerun()
        else: st.error("Erro")

def main_menu():
    st.sidebar.title("Menu"); st.sidebar.subheader("💾 Backup")
    if os.path.exists(DB_FILE): 
        with open(DB_FILE,"rb") as f: st.sidebar.download_button("⬇️ BAIXAR DADOS",f,"backup.db")
    up=st.sidebar.file_uploader("RESTORE",type=["db"])
    if up and st.sidebar.button("CONFIRMAR IMPORTAÇÃO DE DADOS"):
        try: open(DB_FILE,"wb").write(up.getbuffer()); st.sidebar.success("✅ Sucesso! Reiniciando..."); time.sleep(2); st.rerun()
        except Exception as e: st.sidebar.error(f"❌ {e}")
    st.sidebar.markdown("---")
    if st.sidebar.button("Sair"): st.session_state['logado']=False; st.rerun()

    st.header("Painel Principal"); st.write("Usuário: fvilhena")
    c1,c2=st.columns(2); c3,c4=st.columns(2); c5,c6=st.columns(2)
    if c1.button("CADASTRO",use_container_width=True): st.session_state.update(menu='cadastro', sub=None)
    if c2.button("COMPRAR",use_container_width=True): st.session_state.update(menu='comprar', modo=None)
    if c3.button("SALDO/HISTÓRICO",use_container_width=True): st.session_state.update(menu='hist', hist_id=None, hist_mode='view')
    if c4.button("RECARGA",use_container_width=True): st.session_state.update(menu='recarga', rec_mode=None, pix_data=None)
    if c5.button("RELATÓRIOS",use_container_width=True): st.session_state.update(menu='relatorios', rel_mode='produtos')

    menu=st.session_state.get('menu')

    # --- CADASTRO ---
    if menu=='cadastro':
        st.markdown("---"); c1,c2=st.columns(2)
        if c1.button("USUÁRIO",use_container_width=True): st.session_state['sub']='user'
        if c2.button("ALIMENTOS",use_container_width=True): st.session_state['sub']='food'
        
        if st.session_state.get('sub')=='food':
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

        if st.session_state.get('sub')=='user':
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
            elif act=="NOVO ALUNO":
                st.write("📝 **Ficha de Cadastro Completa**")
                with st.form("nal"):
                    c1,c2=st.columns([3,1]); nm=c1.text_input("Nome Completo"); nas=c2.date_input("Data Nascimento",value=None,min_value=date(1990,1,1),format="DD/MM/YYYY")
                    c3,c4,c5=st.columns(3); ser=c3.text_input("Série"); tr=c4.text_input("Turma"); tur=c5.selectbox("Turno",["Matutino","Vespertino","Integral"])
                    em=st.text_input("E-mail Responsável")
                    c6,c7,c8=st.columns(3); t1=c6.text_input("Telefone 1"); t2=c7.text_input("Telefone 2"); t3=c8.text_input("Telefone 3")
                    sl=st.number_input("Saldo Inicial (R$)",0.0)
                    if st.form_submit_button("CONFIRMAR CADASTRO"): 
                        try:
                            upsert_aluno(nm,ser,tr,tur,nas,em,t1,t2,t3,sl)
                            st.success("✅ Aluno cadastrado com sucesso!"); time.sleep(1.5); st.rerun()
                        except Exception as e: st.error(f"❌ Erro ao cadastrar: {e}")
            elif act=="ATUALIZAR":
                df=get_all_alunos()
                if not df.empty:
                    df=df.sort_values('nome'); df['l']=df['id'].astype(str)+" - "+df['nome']; s=st.selectbox("Aluno",df['l'].unique()); id=int(s.split(' - ')[0]); d=df[df['id']==id].iloc[0]
                    try: dna=datetime.strptime(d['nascimento'],'%Y-%m-%d').date()
                    except: dna=None
                    st.write("✏️ **Editar Dados**")
                    with st.form("ual"):
                        c1,c2=st.columns([3,1]); nm=c1.text_input("Nome",d['nome']); nas=c2.date_input("Nascimento",dna,format="DD/MM/YYYY")
                        c3,c4,c5=st.columns(3); ser=c3.text_input("Série",d['serie'] or ""); tr=c4.text_input("Turma",d['turma']); 
                        ts=["Matutino","Vespertino","Integral"]; idx=ts.index(d['turno']) if d['turno'] in ts else 0; tur=c5.selectbox("Turno",ts,index=idx)
                        em=st.text_input("E-mail",d['email'] or ""); c6,c7,c8=st.columns(3); t1=c6.text_input("Tel 1",d['telefone1'] or ""); t2=c7.text_input("Tel 2",d['telefone2'] or ""); t3=c8.text_input("Tel 3",d['telefone3'] or ""); sl=st.number_input("Saldo",value=float(d['saldo']))
                        if st.form_submit_button("CONFIRMAR ALTERAÇÕES"):
                            try:
                                update_aluno_manual(id,nm,ser,tr,tur,str(nas) if nas else None,em,t1,t2,t3,sl)
                                st.success("✅ Dados atualizados com sucesso!"); time.sleep(1.5); st.rerun()
                            except Exception as e: st.error(f"❌ Erro ao atualizar: {e}")
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
        if c1.button("📝 RECEBIMENTO MANUAL",use_container_width=True): st.session_state['rec_mode']='manual'; st.session_state['pix_data']=None
        if c2.button("💠 PIX (QR CODE)",use_container_width=True): st.session_state['rec_mode']='pix'; st.session_state['pix_data']=None

        df=get_all_alunos()
        if not df.empty:
            df=df.sort_values('nome'); df['l']=df['nome']+" | "+df['turma']; s=st.selectbox("Aluno",df['l'].unique()); id_a=int(df[df['l']==s].iloc[0]['id'])
            
            if st.session_state.get('rec_mode')=='manual':
                st.info("Recarga Manual")
                with st.form("rman"):
                    v=st.number_input("Valor R$",0.0,step=5.0); m=st.selectbox("Forma",["DINHEIRO", "PIX (MANUAL)", "DÉBITO", "CRÉDITO"])
                    if st.form_submit_button("CONFIRMAR"):
                        registrar_recarga(id_a,v,m)
                        disparar_alerta(id_a, "Recarga", v, f"Forma: {m}")
                        st.success("Sucesso!"); st.rerun()
            
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
                    if st.button("✅ CONFIRMAR PIX"):
                        registrar_recarga(id_a, v, "PIX (QR)")
                        disparar_alerta(id_a, "Recarga Pix", v, "Via QR Code")
                        st.success("Creditado!"); st.rerun()
        else: st.warning("Sem alunos.")

    # --- COMPRAR ---
    if menu == 'comprar':
        st.markdown("---"); st.subheader("🛒 Venda")
        if not st.session_state.get('modo'):
            c1,c2=st.columns(2)
            if c1.button("🔍 ALUNO",use_container_width=True): st.session_state['modo']='aluno'
            if c2.button("🏫 TURMA",use_container_width=True): st.session_state.update(modo='turma', res_tur=False)
        
        if st.session_state.get('modo')=='aluno':
            df=get_all_alunos()
            if not df.empty:
                df=df.sort_values('nome'); df['l']=df['nome']+" | "+df['turma']; s=st.selectbox("Aluno",df['l'].unique()); idx=int(df[df['l']==s].iloc[0]['id'])
                realizar_venda_form(idx, origin='aluno')
            else: st.warning("Sem alunos.")
        
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
                    if c2.button("🛑 ENCERRAR TURMA", type="primary"): st.session_state['res_tur']=True; st.rerun()
                    if not st.session_state.get('aid_venda'):
                        df=get_alunos_por_turma(tur); h1,h2,h3=st.columns([3,1,1]); h1.write("Nome"); h2.write("Saldo"); h3.write("Ação")
                        for i,r in df.iterrows():
                            c1,c2,c3=st.columns([3,1,1]); c1.write(r['nome']); c2.markdown(f"<span style='color:{'green' if r['saldo']>=0 else 'red'}'>{r['saldo']:.2f}</span>",unsafe_allow_html=True)
                            if c3.button("VENDER",key=r['id']): st.session_state['aid_venda']=r['id']; st.rerun()
                            st.markdown("<hr style='margin:5px 0'>",unsafe_allow_html=True)
                        if st.button("⬅️ Voltar"): st.session_state['t_sel']=None; st.rerun()
                    else:
                        realizar_venda_form(st.session_state['aid_venda'], origin='turma')

    # --- HISTÓRICO ---
    if menu == 'hist':
        st.markdown("---"); st.subheader("📜 Extrato e Histórico")
        c1, c2 = st.columns(2)
        if c1.button("📜 VER EXTRATO", use_container_width=True): st.session_state['hist_mode'] = 'view'; st.session_state['hist_id'] = None
        if c2.button("🚫 CANCELAR VENDA", use_container_width=True): st.session_state['hist_mode'] = 'cancel'; st.session_state['hist_id'] = None

        df = get_all_alunos()
        if not df.empty:
            df = df.sort_values(by='nome'); df['lbl'] = df['nome'] + " | " + df['turma'].astype(str)
            
            if st.session_state.get('hist_mode') == 'view':
                if not st.session_state.get('hist_id'):
                    sel = st.selectbox("Selecione o Aluno:", df['lbl'].unique())
                    if st.button("ABRIR EXTRATO"): st.session_state['hist_id'] = int(df[df['lbl'] == sel].iloc[0]['id']); st.rerun()
                else:
                    if st.button("⬅️ Trocar Aluno"): st.session_state['hist_id'] = None; st.rerun()
                    conn=sqlite3.connect(DB_FILE); conn.row_factory=sqlite3.Row; c=conn.cursor(); c.execute("SELECT * FROM alunos WHERE id=?",(st.session_state['hist_id'],)); al=c.fetchone(); conn.close()
                    st.markdown(f"<div style='background:#f0f2f6;padding:20px;text-align:center'><h3>{al['nome']}</h3><h1>R$ {al['saldo']:.2f}</h1></div>",unsafe_allow_html=True)
                    filt = st.selectbox("Filtro:", ["HOJE", "7 DIAS", "30 DIAS", "TODOS"])
                    if st.button("EXIBIR"):
                        ext=get_extrato_aluno(al['id'], filt)
                        if not ext.empty: 
                            st.dataframe(ext, column_config={"Valor": st.column_config.NumberColumn(format="R$ %.2f")}, hide_index=True, use_container_width=True)
                            
                            c_p1, c_p2 = st.columns(2)
                            if c_p1.button("🖨️ LASER/JATO (A4)"): acionar_impressao_js()
                            criar_botao_pdf_termico(ext, f"EXTRATO: {al['nome']}")
                        else: st.info("Vazio.")

            elif st.session_state.get('hist_mode') == 'cancel':
                st.info("⚠️ Cancelamento de vendas")
                sel = st.selectbox("Selecione o Aluno:", df['lbl'].unique()); id_aluno = int(df[df['lbl'] == sel].iloc[0]['id'])
                filt_canc = st.selectbox("Período:", ["HOJE", "7 DIAS", "30 DIAS", "TODOS"])
                vendas_lista = get_vendas_cancelar(id_aluno, filt_canc)
                
                if not vendas_lista.empty:
                    vendas_lista['desc'] = vendas_lista.apply(lambda x: f"ID: {x['id']} | {x['data_hora']} | R$ {x['valor_total']:.2f} | {x['itens']}", axis=1)
                    venda_sel = st.selectbox("Selecione a compra:", vendas_lista['desc'])
                    if st.button("🗑️ CONFIRMAR CANCELAMENTO", type="primary"):
                        id_transacao = int(venda_sel.split(" | ")[0].replace("ID: ", ""))
                        valor_estorno = float(venda_sel.split(" | ")[2].replace("R$ ", ""))
                        cancelar_venda_db(id_transacao, id_aluno, valor_estorno)
                        disparar_alerta(id_aluno, "Estorno/Cancelamento", valor_estorno, "Venda cancelada pelo operador")
                        st.success(f"Cancelado! R$ {valor_estorno:.2f} devolvidos."); time.sleep(2); st.rerun()
                else: st.warning("Nenhuma venda encontrada.")
        else: st.warning("Sem alunos.")

    # --- RELATÓRIOS ---
    if menu == 'relatorios':
        st.markdown("---"); st.subheader("📊 Relatórios")
        data_sel = st.date_input("Data:", datetime.now(), format="DD/MM/YYYY"); d_str = data_sel.strftime("%d/%m/%Y")
        st.write(f"Filtrando por: **{d_str}**"); st.markdown("---")
        c1, c2, c3 = st.columns(3)
        if c1.button("📦 PRODUTOS", use_container_width=True): st.session_state['rel_mode'] = 'produtos'
        if c2.button("👥 ALUNOS", use_container_width=True): st.session_state['rel_mode'] = 'alunos'
        if c3.button("💰 RECARGAS", use_container_width=True): st.session_state['rel_mode'] = 'recargas'

        if st.session_state.get('rel_mode') == 'produtos':
            vis_mode = st.radio("Modo de Visualização:", ["VISÃO GERAL (TOTAL)", "DETALHADO POR TURMA"], horizontal=True)
            if vis_mode == "VISÃO GERAL (TOTAL)":
                df_p, tot = get_relatorio_produtos(d_str)
                if not df_p.empty:
                    st.metric("Total do Dia (Estimado)", f"R$ {tot:.2f}")
                    st.dataframe(df_p, column_config={"Valor Total (R$)": st.column_config.NumberColumn(format="R$ %.2f")}, hide_index=True, use_container_width=True)
                    c1, c2 = st.columns(2)
                    if c1.button("🖨️ LASER/JATO (A4)"): acionar_impressao_js()
                    criar_botao_pdf_termico(df_p, "RELATORIO VENDAS GERAL")
                else: st.info("Nada vendido.")
            else:
                res_turmas = get_relatorio_produtos_por_turma(d_str)
                if res_turmas:
                    # Para impressão térmica, concatenamos tudo em um único DF
                    df_completo = pd.DataFrame()
                    for turma, df_t in res_turmas.items():
                        st.markdown(f"### {turma}")
                        st.dataframe(df_t, column_config={"Total": st.column_config.NumberColumn(format="R$ %.2f")}, hide_index=True, use_container_width=True)
                        df_t['TURMA'] = turma # Marca a turma
                        df_completo = pd.concat([df_completo, df_t])
                    
                    c1, c2 = st.columns(2)
                    if c1.button("🖨️ LASER/JATO (A4)"): acionar_impressao_js()
                    criar_botao_pdf_termico(res_turmas, "RELATORIO POR TURMA", modo="turmas")
                else: st.info("Nada vendido.")
        
        elif st.session_state.get('rel_mode') == 'alunos':
            df_a = get_relatorio_alunos_dia(d_str)
            if not df_a.empty:
                st.dataframe(df_a, column_config={"Valor": st.column_config.NumberColumn(format="R$ %.2f")}, hide_index=True, use_container_width=True)
                c_p1, c_p2 = st.columns(2)
                if c_p1.button("🖨️ LASER/JATO (A4)"): acionar_impressao_js()
                criar_botao_pdf_termico(df_a, "RELATORIO ALUNOS")
            else: st.info("Nada vendido.")

        elif st.session_state.get('rel_mode') == 'recargas':
            df_r = get_relatorio_recargas_dia(d_str)
            if not df_r.empty:
                st.dataframe(df_r, column_config={"Valor": st.column_config.NumberColumn(format="R$ %.2f")}, hide_index=True, use_container_width=True)
                c_p1, c_p2 = st.columns(2)
                if c_p1.button("🖨️ LASER/JATO (A4)"): acionar_impressao_js()
                criar_botao_pdf_termico(df_r, "RELATORIO RECARGAS")
            else: st.info("Nenhuma recarga.")

# --- FUNÇÃO DE VENDA ---
def realizar_venda_form(aid, origin=None):
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
        
        st.markdown("---")
        c_conf, c_voltar = st.columns(2)
        with c_conf: confirm = st.form_submit_button("✅ CONFIRMAR", type="primary")
        with c_voltar: back = st.form_submit_button("⬅️ VOLTAR")
        
        if confirm:
            t=0; its=[]
            for i,q in qs.items():
                if q>0: it=df[df['id']==i].iloc[0]; t+=it['valor']*q; its.append(f"{q}x {it['nome']}")
            if t>0: 
                try:
                    update_saldo_aluno(aid,al['saldo']-t); registrar_venda(aid,", ".join(its),t)
                    disparar_alerta(aid, "Compra", t, ", ".join(its))
                    st.success("✅ Venda realizada com sucesso!"); time.sleep(1.5); st.session_state['aid_venda']=None; st.rerun()
                except Exception as e: st.error(f"❌ Erro na venda: {e}")
            else: st.warning("Selecione algo.")
        
        if back:
            if origin == 'aluno': st.session_state['modo_compra'] = None
            if origin == 'turma': st.session_state['aid_venda'] = None
            st.rerun()

if st.session_state['logado']: main_menu()
else: login_screen()
