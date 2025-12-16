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
import random
import string
import pytz
from datetime import datetime, timedelta, date
from collections import Counter
from fpdf import FPDF

# --- Configuração da Página ---
st.set_page_config(page_title="Cantina Peixinho Dourado", layout="centered")

# ==========================================
#    CONFIGURAÇÕES GERAIS
# ==========================================
FUSO_MANAUS = pytz.timezone('America/Manaus')
BREVO_API_KEY = "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"
EMAIL_REMETENTE = "cantina@peixinhodourado.g12.br" 
NOME_REMETENTE = "Cantina Peixinho Dourado"
CHAVE_PIX_ESCOLA = "flaviovilhena@gmail.com" 
NOME_BENEFICIARIO = "FLAVIO SILVA"
CIDADE_BENEFICIARIO = "MANAUS" 
DB_FILE = 'cantina.db'

def agora_manaus(): return datetime.now(FUSO_MANAUS)

# --- BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabela de ADMINISTRAÇÃO
    c.execute('''CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        email TEXT UNIQUE, 
        senha TEXT, 
        nome TEXT, 
        ativo INTEGER DEFAULT 1
    )''')
    
    # Cria usuário admin padrão se não existir
    c.execute("SELECT * FROM admins WHERE email='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO admins (email, senha, nome, ativo) VALUES (?, ?, ?, ?)", 
                  ('admin', 'admin123', 'Super Admin', 1))

    # 2. Tabela Alunos
    c.execute('''CREATE TABLE IF NOT EXISTS alunos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, serie TEXT, turma TEXT, turno TEXT, nascimento TEXT, email TEXT, telefone1 TEXT, telefone2 TEXT, telefone3 TEXT, saldo REAL, login TEXT, senha TEXT)''')
    # Migrações
    cols = [('telefone3','TEXT'), ('login','TEXT'), ('senha','TEXT')]
    for col, tip in cols:
        try: c.execute(f"ALTER TABLE alunos ADD COLUMN {col} {tip}")
        except: pass
    
    # 3. Tabela Alimentos
    c.execute('''CREATE TABLE IF NOT EXISTS alimentos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, valor REAL, tipo TEXT)''')
    try: c.execute("ALTER TABLE alimentos ADD COLUMN tipo TEXT"); c.execute("UPDATE alimentos SET tipo = 'ALIMENTO' WHERE tipo IS NULL")
    except: pass
    
    # 4. Tabelas Transacionais
    c.execute('''CREATE TABLE IF NOT EXISTS transacoes (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_id INTEGER, itens TEXT, valor_total REAL, data_hora TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS recargas (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_id INTEGER, valor REAL, data_hora TEXT, metodo_pagamento TEXT, nsu TEXT)''')
    try: c.execute("ALTER TABLE recargas ADD COLUMN metodo_pagamento TEXT"); c.execute("ALTER TABLE recargas ADD COLUMN nsu TEXT")
    except: pass
    
    conn.commit(); conn.close()

# --- FUNÇÕES DE LOGIN ---
def verificar_login(usuario, senha):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tenta como ADMIN
    c.execute("SELECT id, nome, ativo FROM admins WHERE email = ? AND senha = ?", (usuario, senha))
    admin = c.fetchone()
    if admin:
        conn.close()
        if admin[2] == 1: # Se ativo
            return {'tipo': 'admin', 'id': admin[0], 'nome': admin[1]}
        else:
            return {'tipo': 'bloqueado'}
            
    # 2. Tenta como ALUNO
    c.execute("SELECT id, nome FROM alunos WHERE login = ? AND senha = ?", (usuario, senha))
    aluno = c.fetchone()
    conn.close()
    if aluno:
        return {'tipo': 'aluno', 'id': aluno[0], 'nome': aluno[1]}
        
    return None

# --- FUNÇÕES DE SUPORTE (PDF, Email, DB) ---
def gerar_senha_aleatoria(tamanho=6):
    return ''.join(random.choice(string.ascii_letters + string.digits) for i in range(tamanho))

def garantir_credenciais(aluno_id, nome_aluno):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT login, senha FROM alunos WHERE id = ?", (aluno_id,)); dados = c.fetchone()
    if not dados or not dados[0]:
        primeiro_nome = nome_aluno.split()[0].lower().replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u').replace('ã','a')
        login_novo = f"{primeiro_nome}{aluno_id}"
    else: login_novo = dados[0]
    if not dados or not dados[1]: senha_nova = gerar_senha_aleatoria()
    else: senha_nova = dados[1]
    c.execute("UPDATE alunos SET login = ?, senha = ? WHERE id = ?", (login_novo, senha_nova, aluno_id))
    conn.commit(); conn.close()
    return login_novo, senha_nova

# --- CLASSES PDF ---
class PDFTermico(FPDF):
    def __init__(self, titulo, dados, modo="simples"):
        linhas = 0
        if modo == "turmas":
            for df in dados.values(): linhas += len(df) + 4 
        else:
            linhas = len(dados)
        altura_estimada = 40 + (linhas * 6)
        super().__init__(orientation='P', unit='mm', format=(80, altura_estimada))
        self.titulo = titulo; self.dados = dados; self.modo = modo; self.set_margins(2, 2, 2); self.add_page()
    def header(self):
        self.set_font('Courier', 'B', 10); self.cell(0, 5, 'CANTINA PEIXINHO DOURADO', 0, 1, 'C')
        self.set_font('Courier', '', 8); self.cell(0, 4, 'Relatorio Gerencial', 0, 1, 'C')
        self.cell(0, 4, f'{agora_manaus().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'C')
        self.ln(2); self.cell(0, 0, border="T", ln=1); self.ln(2)
        self.set_font('Courier', 'B', 9); self.multi_cell(0, 4, self.titulo.upper(), 0, 'C'); self.ln(2)
    def gerar_relatorio(self):
        if self.modo == "turmas": self._gerar_por_turma()
        else: self._gerar_simples()
    def _gerar_simples(self):
        self.set_font('Courier', 'B', 7); cols = self.dados.columns.tolist(); largeur = 76/len(cols)
        for c in cols:
            align = 'R' if 'Qtd' in str(c) or 'Valor' in str(c) else 'L'
            self.cell(largeur, 4, str(c)[:15], 0, 0, align)
        self.ln(); self.set_font('Courier', '', 7)
        for i, r in self.dados.iterrows():
            for c in cols:
                v = str(r[c]); align = 'L'
                if 'Valor' in c or 'Total' in c: 
                    if isinstance(r[c], (int, float)): v = f"{r[c]:.2f}"; align = 'R'
                elif 'Qtd' in c: align = 'R'
                self.cell(largeur, 4, v[:20], 0, 0, align)
            self.ln()
        self.ln(4); self.cell(0, 0, border="T", ln=1)
    def _gerar_por_turma(self):
        for t, df in self.dados.items():
            self.set_font('Courier', 'B', 9); self.cell(0, 5, f"TURMA: {t}", 0, 1, 'L'); self.cell(0, 0, border="T", ln=1)
            self.set_font('Courier', 'B', 7); self.cell(60, 4, "PRODUTO", 0, 0, 'L'); self.cell(16, 4, "QTD", 0, 1, 'R')
            self.set_font('Courier', '', 7)
            for i, r in df.iterrows():
                if str(r['Produto']) == "TOTAL TURMA": continue
                self.cell(60, 4, str(r['Produto'])[:30], 0, 0, 'L'); self.cell(16, 4, str(r['Qtd']), 0, 1, 'R')
            self.ln(2); self.cell(0, 0, border="B", ln=1); self.ln(2)

class PDFA4(FPDF):
    def __init__(self, titulo):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.titulo = titulo; self.set_margins(10, 10, 10); self.add_page()
    def header(self):
        self.set_font('Arial', 'B', 14); self.cell(0, 10, 'CANTINA PEIXINHO DOURADO', 0, 1, 'C')
        self.set_font('Arial', '', 10); self.cell(0, 6, f'Relatório: {self.titulo}', 0, 1, 'C')
        self.cell(0, 6, f'Gerado em: {agora_manaus().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'C')
        self.ln(5); self.line(10, 35, 200, 35); self.ln(5)
    def footer(self):
        self.set_y(-15); self.set_font('Arial', 'I', 8); self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')
    def tabela_simples(self, df):
        self.set_font('Arial', 'B', 9); cols = df.columns.tolist(); largeur = 190/len(cols)
        for c in cols: 
            align = 'R' if 'Valor' in c or 'Qtd' in c or 'Total' in c else 'L'
            self.cell(largeur, 8, str(c), 1, 0, 'C')
        self.ln(); self.set_font('Arial', '', 9)
        for i, r in df.iterrows():
            for c in cols:
                v = str(r[c]); align = 'L'
                if 'Valor' in c or 'Total' in c: 
                    if isinstance(r[c], (int, float)): v = f"R$ {r[c]:.2f}"
                    align = 'R'
                elif 'Qtd' in c: align = 'R'
                self.cell(largeur, 7, v[:40], 1, 0, align)
            self.ln()
    def tabela_agrupada(self, dados):
        for t, df in dados.items():
            self.set_font('Arial', 'B', 11); self.cell(0, 10, f"TURMA: {t}", 0, 1, 'L')
            self.set_font('Arial', 'B', 9); self.cell(100, 7, "PRODUTO", 1, 0, 'L'); self.cell(30, 7, "QTD", 1, 0, 'C'); self.cell(60, 7, "TOTAL (R$)", 1, 1, 'C')
            self.set_font('Arial', '', 9)
            for i, r in df.iterrows():
                p=str(r['Produto']); q=str(r['Qtd']); tot=f"R$ {r['Total']:.2f}"
                if p=="TOTAL TURMA":
                    self.set_font('Arial','B',9); self.cell(130,7,"TOTAL DA TURMA",1,0,'R'); self.cell(60,7,tot,1,1,'R')
                else:
                    self.set_font('Arial','',9); self.cell(100,7,p,1,0,'L'); self.cell(30,7,q,1,0,'C'); self.cell(60,7,tot,1,1,'R')
            self.ln(5)

# --- HELPERS DOWNLOAD ---
def criar_botao_pdf_a4(dados, titulo, modo="simples"):
    vazio = False
    if isinstance(dados, pd.DataFrame): 
        if dados.empty: vazio=True
    elif not dados: vazio=True
    if vazio: return
    try:
        pdf = PDFA4(titulo)
        if modo == "turmas": pdf.tabela_agrupada(dados)
        else: pdf.tabela_simples(dados)
        st.download_button("🖨️ BAIXAR PDF LASER (A4)", pdf.output(dest='S').encode('latin-1', 'ignore'), f"rel_a4_{int(time.time())}.pdf", "application/pdf")
    except Exception as e: st.error(f"Erro A4: {e}")

def criar_botao_pdf_termico(dados, titulo, modo="simples"):
    vazio = False
    if isinstance(dados, pd.DataFrame): 
        if dados.empty: vazio=True
    elif not dados: vazio=True
    if vazio: return
    try:
        pdf = PDFTermico(titulo, dados, modo); pdf.gerar_relatorio()
        st.download_button("🧾 BAIXAR PDF TÉRMICO (Bematech)", pdf.output(dest='S').encode('latin-1', 'ignore'), f"cupom_{int(time.time())}.pdf", "application/pdf", type="primary")
    except Exception as e: st.error(f"Erro Termico: {e}")

# --- EMAIL E ALERTAS ---
def enviar_email_brevo_thread(email_destino, nome_aluno, assunto, mensagem_html):
    if not email_destino or "@" not in str(email_destino): return 
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"accept": "application/json", "api-key": BREVO_API_KEY, "content-type": "application/json"}
    payload = {"sender": {"name": NOME_REMETENTE, "email": EMAIL_REMETENTE}, "to": [{"email": email_destino, "name": nome_aluno}], "subject": assunto, "htmlContent": mensagem_html}
    try: requests.post(url, json=payload, headers=headers)
    except: pass

def enviar_credenciais_thread(email, nome, login, senha):
    if not email or "@" not in str(email): return
    msg_html = f"<html><body><h3>Olá, responsável por {nome}!</h3><p>Para acompanhar o saldo, seu acesso é:</p><div style='background:#f0f2f6;padding:15px;border:1px solid #ccc;'><p><b>Login:</b> {login}</p><p><b>Senha:</b> {senha}</p></div><p>Acesse o app da cantina.</p></body></html>"
    enviar_email_brevo_thread(email, nome, "🔑 Seu Acesso - Cantina Peixinho Dourado", msg_html)

def disparar_alerta(aluno_id, tipo, valor, detalhes):
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor(); c.execute("SELECT nome, email, saldo FROM alunos WHERE id = ?", (aluno_id,)); dados = c.fetchone(); conn.close()
        if dados:
            nome, email, saldo_atual = dados
            if email and len(str(email)) > 5:
                msg = f"<html><body><h3>Olá, responsável por {nome}!</h3><p>Uma <b>{tipo}</b> foi realizada.<br><br><b>Detalhes:</b> {detalhes}<br><b>Valor:</b> R$ {valor:.2f}<br><br><b>Saldo Atual:</b> R$ {saldo_atual:.2f}</p></body></html>"
                threading.Thread(target=enviar_email_brevo_thread, args=(email, nome, f"🔔 Cantina: {tipo} R$ {valor:.2f}", msg)).start()
    except: pass

# --- PIX ---
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
        p=self._f("00","01")+self._f("26",self._f("00","BR.GOV.BCB.PIX")+self._f("01",self.c))+self._f("52","0000")+self._f("53","986")+self._f("54",self.v)+self._f("58","BR")+self._f("59",self.n)+self._f("60",self.ci)+self._f("62",self._f("05",self.t))+"6304"; return p+self._crc(p)

# --- DB LEITURA ---
def get_all_alunos(): conn=sqlite3.connect(DB_FILE); df=pd.read_sql_query("SELECT * FROM alunos",conn) if sqlite3.connect(DB_FILE) else pd.DataFrame(); conn.close(); return df
def get_alunos_por_turma(t): conn=sqlite3.connect(DB_FILE); df=pd.read_sql_query("SELECT * FROM alunos WHERE turma=? ORDER BY nome ASC",conn,params=(t,)); conn.close(); return df
def get_vendas_hoje_turma(t): 
    data_hoje_str = agora_manaus().strftime("%d/%m/%Y")
    conn=sqlite3.connect(DB_FILE)
    df=pd.read_sql_query("SELECT a.nome, t.itens, t.valor_total FROM transacoes t JOIN alunos a ON t.aluno_id=a.id WHERE a.turma=? AND t.data_hora LIKE ? ORDER BY t.id DESC",conn,params=(t,data_hoje_str+"%"))
    conn.close(); return df
def get_historico_preferencias(aid):
    conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute("SELECT itens FROM transacoes WHERE aluno_id=? ORDER BY id DESC LIMIT 10",(aid,)); r=c.fetchall(); conn.close(); cnt=Counter()
    for row in r: 
        if row[0]: 
            for i in row[0].split(", "): 
                try: cnt[i.split("x ")[1]]+=int(i.split("x ")[0])
                except: pass
    return cnt

# --- DB ESCRITA ---
def update_saldo_aluno(id,s): conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute("UPDATE alunos SET saldo=? WHERE id=?",(s,id)); conn.commit(); conn.close()
def registrar_venda(aid,i,v): 
    conn=sqlite3.connect(DB_FILE); c=conn.cursor()
    data_manaus = agora_manaus().strftime("%d/%m/%Y %H:%M:%S")
    c.execute("INSERT INTO transacoes (aluno_id,itens,valor_total,data_hora) VALUES (?,?,?,?)",(aid,i,v,data_manaus))
    conn.commit(); conn.close()
def registrar_recarga(aid,v,m,n=None): 
    conn=sqlite3.connect(DB_FILE); c=conn.cursor()
    data_manaus = agora_manaus().strftime("%d/%m/%Y %H:%M:%S")
    c.execute("INSERT INTO recargas (aluno_id,valor,data_hora,metodo_pagamento,nsu) VALUES (?,?,?,?,?)",(aid,v,data_manaus,m,n))
    c.execute("SELECT saldo FROM alunos WHERE id=?",(aid,)); s=c.fetchone()[0]; c.execute("UPDATE alunos SET saldo=? WHERE id=?",(s+v,aid)); conn.commit(); conn.close()
def cancelar_venda_db(tid, aid, valor):
    conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute("DELETE FROM transacoes WHERE id = ?", (tid,)); c.execute("SELECT saldo FROM alunos WHERE id = ?", (aid,)); s=c.fetchone()[0]; c.execute("UPDATE alunos SET saldo = ? WHERE id = ?", (s + valor, aid)); conn.commit(); conn.close()

# --- ADMIN CRUD ---
def criar_admin(email, senha, nome):
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("INSERT INTO admins (email, senha, nome, ativo) VALUES (?, ?, ?, 1)", (email, senha, nome))
        conn.commit(); conn.close()
        return True
    except: return False

def get_all_admins():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT id, nome, email, ativo FROM admins", conn)
    conn.close(); return df

def toggle_admin_status(id_admin, novo_status):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("UPDATE admins SET ativo = ? WHERE id = ?", (novo_status, id_admin))
    conn.commit(); conn.close()

# --- HELPER FILTROS ---
def calcular_data_corte(filtro):
    hoje = agora_manaus().replace(hour=0, minute=0, second=0, microsecond=0)
    if filtro == "HOJE": return hoje
    elif filtro == "7 DIAS": return hoje - timedelta(days=7)
    elif filtro == "30 DIAS": return hoje - timedelta(days=30)
    return None

def validar_horario_turno(data_hora_str, turno):
    if turno == "DIA INTEIRO": return True
    try:
        dt = datetime.strptime(data_hora_str, "%d/%m/%Y %H:%M:%S")
        h = dt.hour; m = dt.minute
        if turno == "MATUTINO": return (h>=6 and (h<11 or (h==11 and m<=45)))
        elif turno == "VESPERTINO": return (h>=13 and h<=18)
    except: pass
    return False

# --- RELATORIOS ---
def get_extrato_aluno(aid, filtro):
    conn=sqlite3.connect(DB_FILE); c=conn.cursor()
    c.execute("SELECT data_hora,itens,valor_total FROM transacoes WHERE aluno_id=?",(aid,)); v=c.fetchall()
    c.execute("SELECT data_hora,valor,metodo_pagamento FROM recargas WHERE aluno_id=?",(aid,)); r=c.fetchall()
    dfp=pd.read_sql_query("SELECT nome,valor FROM alimentos",conn); preco_map=dict(zip(dfp['nome'],dfp['valor']))
    conn.close(); dc = calcular_data_corte(filtro); ext = []
    
    for i in v: 
        dt=datetime.strptime(i[0],"%d/%m/%Y %H:%M:%S")
        dt_corte_naive = dc.replace(tzinfo=None) if dc else None
        if not dt_corte_naive or dt>=dt_corte_naive: 
            itens_str = i[1]; itens_formatados = []
            if itens_str:
                for item in itens_str.split(", "):
                    try:
                        qtd, nome = item.split("x ")
                        p_unit = preco_map.get(nome, 0.0)
                        itens_formatados.append(f"{qtd}x {nome} (R$ {p_unit:.2f})")
                    except: itens_formatados.append(item)
            ext.append({"Data":dt,"Tipo":"COMPRA","Produtos/Histórico":", ".join(itens_formatados),"Valor":-i[2]})
    for i in r:
        dt=datetime.strptime(i[0],"%d/%m/%Y %H:%M:%S")
        dt_corte_naive = dc.replace(tzinfo=None) if dc else None
        if not dt_corte_naive or dt>=dt_corte_naive: ext.append({"Data":dt,"Tipo":"RECARGA","Produtos/Histórico":f"Via {i[2]}","Valor":i[1]})
        
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
            df['dt_obj'] = pd.to_datetime(df['data_hora'], format="%d/%m/%Y %H:%M:%S"); dc_naive = dc.replace(tzinfo=None); df = df[df['dt_obj'] >= dc_naive]
    except: df = pd.DataFrame()
    conn.close(); return df

def get_relatorio_produtos(df_data, turno="DIA INTEIRO"):
    conn=sqlite3.connect(DB_FILE); c=conn.cursor()
    c.execute("SELECT itens, data_hora FROM transacoes WHERE data_hora LIKE ?",(f"{df_data}%",))
    rs=c.fetchall(); dfp=pd.read_sql_query("SELECT nome,valor FROM alimentos",conn); pm=dict(zip(dfp['nome'],dfp['valor']))
    conn.close(); qg=Counter()
    for itens, dh in rs:
        if not validar_horario_turno(dh, turno): continue
        if itens: 
            for i in itens.split(", "):
                try: qg[i.split("x ")[1]]+=int(i.split("x ")[0])
                except: pass
    dd=[]; td=0.0
    for n,q in qg.items(): v=pm.get(n,0.0)*q; td+=v; dd.append({"Produto":n,"Qtd Vendida":q,"Valor Total (R$)":v})
    if dd: return pd.DataFrame(dd).sort_values("Qtd Vendida",ascending=False),td
    return pd.DataFrame(),0.0

def get_relatorio_produtos_por_turma(data_filtro, turno="DIA INTEIRO"):
    conn = sqlite3.connect(DB_FILE)
    query = '''SELECT a.turma, t.itens, t.data_hora FROM transacoes t JOIN alunos a ON t.aluno_id = a.id WHERE t.data_hora LIKE ? ORDER BY a.turma ASC'''
    try:
        rows = conn.execute(query, (f"{data_filtro}%",)).fetchall()
        dfp = pd.read_sql_query("SELECT nome,valor FROM alimentos", conn); preco_map = dict(zip(dfp['nome'], dfp['valor']))
    except: return {}
    conn.close(); dados_turmas = {}
    for turma, itens, dh in rows:
        if not validar_horario_turno(dh, turno): continue
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

# --- INICIALIZAÇÃO ---
init_db()
if 'logado' not in st.session_state: st.session_state['logado'] = False
if 'user_type' not in st.session_state: st.session_state['user_type'] = None
if 'user_id' not in st.session_state: st.session_state['user_id'] = None
if 'user_name' not in st.session_state: st.session_state['user_name'] = ""

def login_screen():
    st.title("Cantina Peixinho Dourado")
    st.info("💡 Primeiro acesso Admin: user: `admin` | senha: `admin123`")
    
    with st.form("login_form"):
        u = st.text_input("Usuário / E-mail")
        p = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")
        
        if submitted:
            res = verificar_login(u, p)
            if res:
                if res['tipo'] == 'bloqueado':
                    st.error("🚫 Acesso bloqueado. Contate o administrador.")
                else:
                    st.session_state['logado'] = True
                    st.session_state['user_type'] = res['tipo']
                    st.session_state['user_id'] = res['id']
                    st.session_state['user_name'] = res['nome']
                    st.rerun()
            else:
                st.error("❌ Usuário ou senha inválidos")

def menu_aluno():
    st.sidebar.title(f"Olá, {st.session_state['user_name'].split()[0]}")
    if st.sidebar.button("Sair"):
        st.session_state.clear()
        st.rerun()
        
    st.header("Painel do Aluno")
    
    # Busca dados atualizados do aluno
    conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; c = conn.cursor()
    c.execute("SELECT * FROM alunos WHERE id = ?", (st.session_state['user_id'],))
    aluno = c.fetchone()
    conn.close()
    
    if aluno:
        # Cartão de Saldo
        st.markdown(f"""
        <div style="background-color:#04AA6D;padding:20px;border-radius:10px;color:white;text-align:center;margin-bottom:20px">
            <h3 style="margin:0">Saldo Disponível</h3>
            <h1 style="font-size:50px;margin:0">R$ {aluno['saldo']:.2f}</h1>
        </div>
        """, unsafe_allow_html=True)
        
        tab1, tab2, tab3 = st.tabs(["📜 Extrato", "💳 Recarga Pix", "👤 Meus Dados"])
        
        with tab1:
            filt = st.selectbox("Período", ["HOJE", "7 DIAS", "30 DIAS", "TODOS"])
            df_ext = get_extrato_aluno(aluno['id'], filt)
            if not df_ext.empty:
                st.dataframe(df_ext, hide_index=True, use_container_width=True)
            else: st.info("Nenhuma movimentação no período.")
            
        with tab2:
            st.write("Para recarregar, mostre este QR Code no caixa ou faça um Pix e envie o comprovante.")
            st.info(f"Chave Pix: {CHAVE_PIX_ESCOLA}")
            
        with tab3:
            st.text_input("Nome", aluno['nome'], disabled=True)
            st.text_input("Turma", f"{aluno['serie']} - {aluno['turma']}", disabled=True)
            st.text_input("Matrícula (Login)", aluno['login'], disabled=True)

def menu_admin():
    st.sidebar.title("Menu Admin")
    st.sidebar.write(f"Logado como: **{st.session_state['user_name']}**")
    st.sidebar.subheader("💾 Backup")
    if os.path.exists(DB_FILE): 
        with open(DB_FILE,"rb") as f: st.sidebar.download_button("⬇️ BAIXAR DADOS",f,"backup.db")
    up=st.sidebar.file_uploader("RESTORE",type=["db"])
    if up and st.sidebar.button("CONFIRMAR IMPORTAÇÃO"):
        try: open(DB_FILE,"wb").write(up.getbuffer()); st.sidebar.success("Reiniciando..."); time.sleep(2); st.rerun()
        except Exception as e: st.sidebar.
