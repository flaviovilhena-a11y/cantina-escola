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

# LISTA ATUALIZADA DE MODULOS
LISTA_PERMISSOES = ["CADASTRO", "COMPRAR", "SALDO", "RECARGA", "CANCELAR VENDA", "RELATÓRIOS DE VENDAS", "RELATÓRIO DE RECARGAS", "ENVIAR ACESSOS", "ADMINISTRADORES"]

def agora_manaus(): return datetime.now(FUSO_MANAUS)

# --- BANCO DE DADOS ---
def check_column_exists(cursor, table_name, column_name):
    try:
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [info[1] for info in cursor.fetchall()]
        return column_name in columns
    except: return False

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabela de ADMINISTRAÇÃO
    c.execute('''CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, senha TEXT, nome TEXT, ativo INTEGER DEFAULT 1, permissoes TEXT)''')
    if not check_column_exists(c, 'admins', 'permissoes'):
        try: c.execute("ALTER TABLE admins ADD COLUMN permissoes TEXT")
        except: pass
    
    # Cria usuário admin padrão
    c.execute("SELECT * FROM admins WHERE email='admin'")
    perms_str = ",".join(LISTA_PERMISSOES)
    if not c.fetchone():
        c.execute("INSERT INTO admins (email, senha, nome, ativo, permissoes) VALUES (?, ?, ?, ?, ?)", ('admin', 'admin123', 'Super Admin', 1, perms_str))
    else:
        # Atualiza permissões para garantir acesso ao novo módulo
        c.execute("UPDATE admins SET permissoes = ? WHERE email='admin'", (perms_str,))

    # 2. Tabela Alunos
    c.execute('''CREATE TABLE IF NOT EXISTS alunos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, serie TEXT, turma TEXT, turno TEXT, nascimento TEXT, email TEXT, telefone1 TEXT, telefone2 TEXT, telefone3 TEXT, saldo REAL)''')
    for col, tipo in [('telefone3', 'TEXT'), ('login', 'TEXT'), ('senha', 'TEXT')]:
        if not check_column_exists(c, 'alunos', col):
            try: c.execute(f"ALTER TABLE alunos ADD COLUMN {col} {tipo}")
            except: pass

    # 3. Tabela Alimentos
    c.execute('''CREATE TABLE IF NOT EXISTS alimentos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, valor REAL, tipo TEXT)''')
    if not check_column_exists(c, 'alimentos', 'tipo'):
        try: c.execute("ALTER TABLE alimentos ADD COLUMN tipo TEXT"); c.execute("UPDATE alimentos SET tipo = 'ALIMENTO' WHERE tipo IS NULL")
        except: pass
    
    # 4. Tabelas Transacionais
    c.execute('''CREATE TABLE IF NOT EXISTS transacoes (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_id INTEGER, itens TEXT, valor_total REAL, data_hora TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS recargas (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_id INTEGER, valor REAL, data_hora TEXT, metodo_pagamento TEXT, nsu TEXT)''')
    
    if not check_column_exists(c, 'recargas', 'metodo_pagamento'):
        try: c.execute("ALTER TABLE recargas ADD COLUMN metodo_pagamento TEXT")
        except: pass
    if not check_column_exists(c, 'recargas', 'nsu'):
        try: c.execute("ALTER TABLE recargas ADD COLUMN nsu TEXT")
        except: pass
    if not check_column_exists(c, 'recargas', 'realizado_por'):
        try: c.execute("ALTER TABLE recargas ADD COLUMN realizado_por TEXT")
        except: pass
    
    # 5. Controle Envios
    c.execute('''CREATE TABLE IF NOT EXISTS controle_envios (data_envio TEXT PRIMARY KEY, status TEXT)''')
    
    conn.commit(); conn.close()

# --- FUNÇÃO RESET ADMIN ---
def reset_admin_padrao():
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("DROP TABLE IF EXISTS admins"); conn.commit(); conn.close()
        init_db(); return True
    except Exception as e: st.error(f"Erro: {e}"); return False

# --- LOGIN E CREDENCIAIS ---
def verificar_login(usuario, senha):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    try:
        c.execute("SELECT id, nome, ativo, permissoes FROM admins WHERE email = ? AND senha = ?", (usuario, senha))
        admin = c.fetchone()
        if admin:
            conn.close()
            if admin[2] == 1: 
                perms = admin[3] if admin[3] else ""
                lista_perms = perms.split(',')
                # Compatibilidade
                if "RELATÓRIOS" in lista_perms: lista_perms.append("RELATÓRIOS DE VENDAS")
                if "SALDO" in lista_perms: lista_perms.append("CANCELAR VENDA") # Garante acesso para quem já tinha saldo
                return {'tipo': 'admin', 'id': admin[0], 'nome': admin[1], 'perms': lista_perms}
            else: return {'tipo': 'bloqueado'}
    except: pass

    try:
        c.execute("SELECT id, nome FROM alunos WHERE login = ? AND senha = ?", (usuario, senha))
        aluno = c.fetchone(); conn.close()
        if aluno: return {'tipo': 'aluno', 'id': aluno[0], 'nome': aluno[1]}
    except: conn.close()
    return None

def gerar_senha_aleatoria(tamanho=6):
    return ''.join(random.choice(string.ascii_letters + string.digits) for i in range(tamanho))

def garantir_credenciais(aluno_id, nome_aluno):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    try:
        c.execute("SELECT login, senha FROM alunos WHERE id = ?", (aluno_id,)); dados = c.fetchone()
        if not dados or not dados[0]:
            primeiro_nome = nome_aluno.split()[0].lower().replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u').replace('ã','a')
            login_novo = f"{primeiro_nome}{aluno_id}"
        else: login_novo = dados[0]
        if not dados or not dados[1]: senha_nova = gerar_senha_aleatoria()
        else: senha_nova = dados[1]
        c.execute("UPDATE alunos SET login = ?, senha = ? WHERE id = ?", (login_novo, senha_nova, aluno_id))
        conn.commit(); return login_novo, senha_nova
    except: return None, None
    finally: conn.close()

# --- PDF ---
class PDFTermico(FPDF):
    def __init__(self, titulo, dados, modo="simples"):
        linhas = 0
        if modo == "turmas":
            for df in dados.values(): linhas += len(df) + 4 
        else: linhas = len(dados)
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
                    if isinstance(r[c], (int, float)): v = f"R$ {r[c]:.2f}"; align = 'R'
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
    if not dados: return
    if isinstance(dados, pd.DataFrame) and dados.empty: return
    try:
        pdf = PDFA4(titulo)
        if modo == "turmas": pdf.tabela_agrupada(dados)
        else: pdf.tabela_simples(dados)
        st.download_button("🖨️ BAIXAR PDF LASER (A4)", pdf.output(dest='S').encode('latin-1', 'ignore'), f"rel_a4_{int(time.time())}.pdf", "application/pdf")
    except Exception as e: st.error(f"Erro A4: {e}")

def criar_botao_pdf_termico(dados, titulo, modo="simples"):
    if not dados: return
    if isinstance(dados, pd.DataFrame) and dados.empty: return
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

# --- AUTOMAÇÃO: EMAIL SALDO BAIXO ---
def verificar_saldo_baixo_e_enviar():
    agora = agora_manaus(); hoje_str = agora.strftime("%Y-%m-%d")
    if agora.weekday() > 4: return
    if not (6 <= agora.hour < 7): return
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT status FROM controle_envios WHERE data_envio = ?", (hoje_str,))
    if c.fetchone(): conn.close(); return 
    try:
        c.execute("SELECT nome, email, saldo FROM alunos WHERE saldo <= 10.00 AND email IS NOT NULL AND email != ''")
        for nome, email, saldo in c.fetchall():
            if "@" in str(email):
                msg_html = f"<html><body><h3>Olá, responsável por {nome}!</h3><p>Lembramos que o saldo do aluno <b>{nome}</b> no Sistema da Cantina Escolar é de <b style='color:red'>R$ {saldo:.2f}</b>.</p><p>Acesse o sistema e realize a recarga.</p><hr><p style='font-size:12px; color:gray'>Cantina Peixinho Dourado</p></body></html>"
                enviar_email_brevo_thread(email, nome, "⚠️ Aviso de Saldo Baixo - Cantina Peixinho Dourado", msg_html); time.sleep(0.2)
        c.execute("INSERT INTO controle_envios (data_envio, status) VALUES (?, ?)", (hoje_str, "ENVIADO")); conn.commit()
    except: pass
    finally: conn.close()

@st.cache_resource
def start_scheduler():
    def loop():
        while True:
            try: verificar_saldo_baixo_e_enviar(); time.sleep(60)
            except: time.sleep(60)
    threading.Thread(target=loop, daemon=True).start()
start_scheduler()

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
    conn=sqlite3.connect(DB_FILE); c=conn.cursor(); dm=agora_manaus().strftime("%d/%m/%Y %H:%M:%S")
    c.execute("INSERT INTO transacoes (aluno_id,itens,valor_total,data_hora) VALUES (?,?,?,?)",(aid,i,v,dm)); conn.commit(); conn.close()
def registrar_recarga(aid, v, m, usuario_logado, nsu=None): 
    conn=sqlite3.connect(DB_FILE); c=conn.cursor()
    dm = agora_manaus().strftime("%d/%m/%Y %H:%M:%S")
    c.execute("INSERT INTO recargas (aluno_id,valor,data_hora,metodo_pagamento,nsu,realizado_por) VALUES (?,?,?,?,?,?)",(aid, v, dm, m, nsu, usuario_logado))
    c.execute("SELECT saldo FROM alunos WHERE id=?",(aid,)); s=c.fetchone()[0]
    c.execute("UPDATE alunos SET saldo=? WHERE id=?",(s+v,aid)); conn.commit(); conn.close()
def cancelar_venda_db(tid, aid, valor):
    conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute("DELETE FROM transacoes WHERE id = ?", (tid,)); c.execute("SELECT saldo FROM alunos WHERE id = ?", (aid,)); s=c.fetchone()[0]; c.execute("UPDATE alunos SET saldo = ? WHERE id = ?", (s + valor, aid)); conn.commit(); conn.close()

# --- ADMIN CRUD ---
def criar_admin(email, senha, nome, permissoes):
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        perms_str = ",".join(permissoes)
        c.execute("INSERT INTO admins (email, senha, nome, ativo, permissoes) VALUES (?, ?, ?, 1, ?)", (email, senha, nome, perms_str))
        conn.commit(); conn.close(); return True
    except: return False
def get_all_admins(): conn=sqlite3.connect(DB_FILE); df=pd.read_sql_query("SELECT id, nome, email, ativo, permissoes FROM admins", conn); conn.close(); return df
def toggle_admin_status(id_admin, novo_status):
    conn=sqlite3.connect(DB_FILE); c=conn.cursor(); c.execute("UPDATE admins SET ativo = ? WHERE id = ?", (novo_status, id_admin)); conn.commit(); conn.close()

# --- HELPER FILTROS ---
def calcular_data_corte(filtro):
    hoje = agora_manaus().replace(hour=0, minute=0, second=0, microsecond=0)
    if filtro == "HOJE": return hoje
    elif filtro == "ÚLTIMOS 7 DIAS": return hoje - timedelta(days=7)
    elif filtro == "ÚLTIMOS 15 DIAS": return hoje - timedelta(days=15)
    elif filtro == "ÚLTIMOS 30 DIAS": return hoje - timedelta(days=30)
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
def get_relatorio_alunos_dia(data_filtro):
    conn = sqlite3.connect(DB_FILE)
    try:
        query = "SELECT a.nome, t.itens, t.valor_total, t.data_hora FROM transacoes t JOIN alunos a ON t.aluno_id=a.id WHERE t.data_hora LIKE ? ORDER BY t.data_hora ASC"
        df = pd.read_sql_query(query, conn, params=(f"{data_filtro}%",))
        if not df.empty:
            df['Hora'] = df['data_hora'].apply(lambda x: x.split(' ')[1])
            df = df[['Hora', 'nome', 'itens', 'valor_total']]
            df.columns = ['Hora', 'Aluno', 'Produtos', 'Valor']
            total_row = pd.DataFrame([{'Hora': '', 'Aluno': 'TOTAL GERAL', 'Produtos': '', 'Valor': df['Valor'].sum()}])
            df = pd.concat([df, total_row], ignore_index=True)
            return df
    except: pass
    finally: conn.close()
    return pd.DataFrame()

def get_relatorio_recargas_dia(data_filtro):
    conn = sqlite3.connect(DB_FILE)
    try:
        query = "SELECT r.data_hora, a.nome, r.metodo_pagamento, r.valor FROM recargas r JOIN alunos a ON r.aluno_id = a.id WHERE r.data_hora LIKE ? ORDER BY r.data_hora ASC"
        df = pd.read_sql_query(query, conn, params=(f"{data_filtro}%",))
        if not df.empty:
            df['Hora'] = df['data_hora'].apply(lambda x: x.split(' ')[1])
            df = df[['Hora', 'nome', 'metodo_pagamento', 'valor']]
            df.columns = ['Hora', 'Aluno', 'Método', 'Valor']
            total_row = pd.DataFrame([{'Hora': '', 'Aluno': 'TOTAL DO DIA', 'Método': '', 'Valor': df['Valor'].sum()}])
            df = pd.concat([df, total_row], ignore_index=True)
            return df
    except: pass
    finally: conn.close()
    return pd.DataFrame()

def get_extrato_aluno(aid, filtro):
    conn=sqlite3.connect(DB_FILE); c=conn.cursor()
    c.execute("SELECT data_hora,itens,valor_total FROM transacoes WHERE aluno_id=?",(aid,)); v=c.fetchall()
    c.execute("SELECT data_hora,valor,metodo_pagamento FROM recargas WHERE aluno_id=?",(aid,)); r=c.fetchall()
    dfp=pd.read_sql_query("SELECT nome,valor FROM alimentos",conn); preco_map=dict(zip(dfp['nome'],dfp['valor'])); conn.close(); dc = calcular_data_corte(filtro); ext = []
    for i in v: 
        dt=datetime.strptime(i[0],"%d/%m/%Y %H:%M:%S"); dt_corte_naive = dc.replace(tzinfo=None) if dc else None
        if not dt_corte_naive or dt>=dt_corte_naive: 
            itens_str = i[1]; itens_formatados = []
            if itens_str:
                for item in itens_str.split(", "):
                    try: qtd, nome = item.split("x "); p_unit = preco_map.get(nome, 0.0); itens_formatados.append(f"{qtd}x {nome} (R$ {p_unit:.2f})")
                    except: itens_formatados.append(item)
            ext.append({"Data":dt,"Tipo":"COMPRA","Produtos/Histórico":", ".join(itens_formatados),"Valor":-i[2]})
    for i in r:
        dt=datetime.strptime(i[0],"%d/%m/%Y %H:%M:%S"); dt_corte_naive = dc.replace(tzinfo=None) if dc else None
        if not dt_corte_naive or dt>=dt_corte_naive: ext.append({"Data":dt,"Tipo":"RECARGA","Produtos/Histórico":f"Via {i[2]}","Valor":i[1]})
    if ext: df=pd.DataFrame(ext).sort_values("Data",ascending=False); df['Data']=df['Data'].apply(lambda x:x.strftime("%d/%m %H:%M")); return df
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
    c.execute("SELECT itens, data_hora FROM transacoes WHERE data_hora LIKE ?",(f"{df_data}%",)); rs=c.fetchall()
    dfp=pd.read_sql_query("SELECT nome,valor FROM alimentos",conn); pm=dict(zip(dfp['nome'],dfp['valor'])); conn.close(); qg=Counter()
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
    try: rows = conn.execute(query, (f"{data_filtro}%",)).fetchall(); dfp = pd.read_sql_query("SELECT nome,valor FROM alimentos", conn); preco_map = dict(zip(dfp['nome'], dfp['valor']))
    except: return {}
    conn.close(); dados_turmas = {}
    for turma, itens, dh in rows:
        if not validar_horario_turno(dh, turno): continue
        if not turma: turma = "SEM TURMA"
        if turma not in dados_turmas: dados_turmas[turma] = Counter()
        if itens:
            for item in itens.split(", "):
                try: parts = item.split("x "); qtd = int(parts[0]); nome = parts[1]; dados_turmas[turma][nome] += qtd
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

def get_relatorio_recargas_detalhado(filtro_tempo):
    conn = sqlite3.connect(DB_FILE)
    try:
        dc = calcular_data_corte(filtro_tempo)
        query = """
            SELECT r.data_hora, a.nome, r.valor, r.metodo_pagamento, r.realizado_por
            FROM recargas r 
            JOIN alunos a ON r.aluno_id = a.id 
            ORDER BY r.id DESC
        """
        rows = conn.execute(query).fetchall()
        lista_final = []
        for dh, nome_aluno, valor, metodo, realizado_por in rows:
            dt_obj = datetime.strptime(dh, "%d/%m/%Y %H:%M:%S")
            if dc:
                dc_naive = dc.replace(tzinfo=None)
                if dt_obj < dc_naive: continue
            
            if metodo == "PIX (QR)":
                origem = "BANCO (Pix Automático)"
            else:
                quem = realizado_por if realizado_por else "Sistema"
                origem = f"MANUAL ({nome_aluno}) | Por: {quem}"
            
            lista_final.append({
                "Data": dt_obj.strftime("%d/%m %H:%M"),
                "Origem": origem,
                "Método": metodo,
                "Valor": valor
            })
        if lista_final: return pd.DataFrame(lista_final)
        return pd.DataFrame()
    except: return pd.DataFrame()
    finally: conn.close()

# --- CRUD ALIMENTOS ---
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

# --- FUNÇÃO DE VENDA (COM BLOQUEIO SALDO NEGATIVO) ---
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
                if al['saldo'] < t:
                    st.error(f"❌ Saldo insuficiente! Falta R$ {t - al['saldo']:.2f}")
                else:
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

# --- MENUS DE INTERFACE ---
if 'logado' not in st.session_state: st.session_state['logado'] = False
if 'user_type' not in st.session_state: st.session_state['user_type'] = None
if 'user_id' not in st.session_state: st.session_state['user_id'] = None
if 'user_name' not in st.session_state: st.session_state['user_name'] = ""
if 'user_perms' not in st.session_state: st.session_state['user_perms'] = []

def login_screen():
    st.title("Cantina Peixinho Dourado")
    st.info("💡 Primeiro acesso Admin: user: `admin` | senha: `admin123`")
    with st.form("login_form"):
        u = st.text_input("Usuário / E-mail"); p = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            res = verificar_login(u, p)
            if res:
                if res['tipo'] == 'bloqueado': st.error("🚫 Acesso bloqueado. Contate o administrador.")
                else:
                    st.session_state['logado'] = True; st.session_state['user_type'] = res['tipo']
                    st.session_state['user_id'] = res['id']; st.session_state['user_name'] = res['nome']
                    if res['tipo'] == 'admin': st.session_state['user_perms'] = res.get('perms', [])
                    st.rerun()
            else: st.error("❌ Usuário ou senha inválidos")
    with st.expander("🆘 Problemas no acesso?"):
        st.write("Se não conseguir acessar com a senha padrão, clique abaixo para resetar a tabela de administradores.")
        if st.button("RESTAURAR ADMIN PADRÃO"):
            if reset_admin_padrao(): st.success("Tabela resetada! Tente: admin / admin123"); time.sleep(2); st.rerun()

def menu_aluno():
    st.sidebar.title(f"Olá, {st.session_state['user_name'].split()[0]}")
    if st.sidebar.button("Sair"): st.session_state.clear(); st.rerun()
    st.header("Painel do Aluno")
    conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; c = conn.cursor(); c.execute("SELECT * FROM alunos WHERE id = ?", (st.session_state['user_id'],)); aluno = c.fetchone(); conn.close()
    if aluno:
        st.markdown(f"""<div style="background-color:#04AA6D;padding:20px;border-radius:10px;color:white;text-align:center;margin-bottom:20px"><h3 style="margin:0">Saldo Disponível</h3><h1 style="font-size:50px;margin:0">R$ {aluno['saldo']:.2f}</h1></div>""", unsafe_allow_html=True)
        tab1, tab2, tab3 = st.tabs(["📜 Extrato", "💳 Recarga Pix", "👤 Meus Dados"])
        with tab1:
            filt = st.selectbox("Período", ["HOJE", "7 DIAS", "30 DIAS", "TODOS"])
            df_ext = get_extrato_aluno(aluno['id'], filt)
            if not df_ext.empty: st.dataframe(df_ext, hide_index=True, use_container_width=True)
            else: st.info("Nenhuma movimentação no período.")
        with tab2: st.write("Para recarregar, mostre este QR Code no caixa ou faça um Pix e envie o comprovante."); st.info(f"Chave Pix: {CHAVE_PIX_ESCOLA}")
        with tab3: st.text_input("Nome", aluno['nome'], disabled=True); st.text_input("Turma", f"{aluno['serie']} - {aluno['turma']}", disabled=True); st.text_input("Matrícula (Login)", aluno['login'], disabled=True)

def menu_admin():
    st.sidebar.title("Menu Admin")
    st.sidebar.write(f"Logado como: **{st.session_state['user_name']}**")
    st.sidebar.subheader("💾 Backup")
    if os.path.exists(DB_FILE): 
        with open(DB_FILE,"rb") as f: st.sidebar.download_button("⬇️ BAIXAR DADOS",f,"backup.db")
    up=st.sidebar.file_uploader("RESTORE",type=["db"])
    if up and st.sidebar.button("CONFIRMAR IMPORTAÇÃO"):
        try: open(DB_FILE,"wb").write(up.getbuffer()); st.sidebar.success("Reiniciando..."); time.sleep(2); st.rerun()
        except Exception as e: st.sidebar.error(f"Erro: {e}")
    st.sidebar.markdown("---")
    if st.sidebar.button("Sair"): st.session_state.clear(); st.rerun()

    perms = st.session_state.get('user_perms', [])
    c1, c2, c3 = st.columns(3)
    c4, c5, c6 = st.columns(3)
    c7, c8, c9 = st.columns(3)
    
    # Linha 1
    if "CADASTRO" in perms:
        if c1.button("CADASTROS", use_container_width=True): st.session_state.update(menu='cadastro', sub=None)
    if "COMPRAR" in perms:
        if c2.button("INICIAR VENDAS", use_container_width=True): st.session_state.update(menu='comprar', modo=None)
    if "RECARGA" in perms:
        if c3.button("RECARGA", use_container_width=True): st.session_state.update(menu='recarga', rec_mode=None, pix_data=None)
    
    # Linha 2
    if "SALDO" in perms:
        if c4.button("SALDO", use_container_width=True): st.session_state.update(menu='hist', hist_id=None, hist_mode='view')
    if "CANCELAR VENDA" in perms:
        if c5.button("🚫 CANCELAR VENDA", use_container_width=True): st.session_state.update(menu='cancelar', canc_mode=None)
    if "RELATÓRIOS DE VENDAS" in perms:
        if c6.button("RELATÓRIOS DE VENDAS", use_container_width=True): st.session_state.update(menu='relatorios', rel_mode='produtos')
        
    # Linha 3
    if "RELATÓRIO DE RECARGAS" in perms:
        if c7.button("RELATÓRIO DE RECARGAS", use_container_width=True): st.session_state.update(menu='rel_recargas')
    if "ENVIAR ACESSOS" in perms:
        if c8.button("ENVIAR ACESSOS", use_container_width=True): st.session_state.update(menu='enviar_acessos', acc_mode=None)
    if "ADMINISTRADORES" in perms:
        if c9.button("👥 ADMINISTRADORES", use_container_width=True): st.session_state.update(menu='acesso', acc_mode=None)

    menu=st.session_state.get('menu')

    if menu=='cadastro' and "CADASTRO" in perms:
        st.markdown("---"); c1,c2,c3=st.columns(3)
        if c1.button("📝 DADOS ALUNOS",use_container_width=True): st.session_state['sub']='user'
        if c2.button("📧 ENVIAR ACESSOS",use_container_width=True): st.session_state['sub']='acesso_alunos'
        if c3.button("🍎 ALIMENTOS",use_container_width=True): st.session_state['sub']='food'
        
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

        if st.session_state.get('sub')=='acesso_alunos':
            st.subheader("🔑 Enviar Senhas para Alunos")
            c1, c2, c3 = st.columns(3)
            if c1.button("👤 POR ALUNO", use_container_width=True): st.session_state['acc_mode'] = 'aluno'
            if c2.button("🏫 POR TURMA", use_container_width=True): st.session_state['acc_mode'] = 'turma'
            if c3.button("📢 PARA TODOS", use_container_width=True): st.session_state['acc_mode'] = 'todos'
            df_alunos = get_all_alunos()
            if st.session_state.get('acc_mode') == 'aluno':
                if not df_alunos.empty:
                    df_alunos['lbl'] = df_alunos['nome'] + " | " + df_alunos['turma'].astype(str)
                    sel = st.selectbox("Selecione o Aluno:", df_alunos['lbl'].unique())
                    id_sel = int(df_alunos[df_alunos['lbl'] == sel].iloc[0]['id'])
                    nome_sel = df_alunos[df_alunos['lbl'] == sel].iloc[0]['nome']
                    email_sel = df_alunos[df_alunos['lbl'] == sel].iloc[0]['email']
                    if st.button("GERAR E ENVIAR"):
                        l, s = garantir_credenciais(id_sel, nome_sel)
                        if email_sel:
                            enviar_credenciais_thread(email_sel, nome_sel, l, s); st.success(f"Enviado para {email_sel}!"); st.info(f"Login: {l} | Senha: {s}")
                        else: st.warning("Sem e-mail cadastrado."); st.info(f"Login: {l} | Senha: {s}")
                else: st.warning("Sem alunos.")
            elif st.session_state.get('acc_mode') == 'turma':
                if not df_alunos.empty:
                    turmas = sorted(df_alunos['turma'].dropna().unique()); t_sel = st.selectbox("Selecione a Turma:", turmas)
                    if st.button(f"DISPARAR PARA {t_sel}"):
                        alunos_turma = df_alunos[df_alunos['turma'] == t_sel]; count = 0; bar = st.progress(0)
                        for i, row in alunos_turma.iterrows():
                            l, s = garantir_credenciais(row['id'], row['nome'])
                            if row['email']: enviar_credenciais_thread(row['email'], row['nome'], l, s); count += 1
                            bar.progress((i + 1) / len(alunos_turma))
                        st.success(f"Processo finalizado! {count} e-mails enviados.")
                else: st.warning("Sem alunos.")
            elif st.session_state.get('acc_mode') == 'todos':
                st.warning("⚠️ Atenção: Isso enviará e-mails para TODOS os alunos.")
                if st.button("CONFIRMAR ENVIO EM MASSA"):
                    if not df_alunos.empty:
                        count = 0; bar = st.progress(0)
                        for i, row in df_alunos.iterrows():
                            l, s = garantir_credenciais(row['id'], row['nome'])
                            if row['email']: enviar_credenciais_thread(row['email'], row['nome'], l, s); count += 1
                            bar.progress((i + 1) / len(df_alunos))
                        st.success(f"Envio concluído! {count} mensagens enviadas.")

    if menu == 'recarga' and "RECARGA" in perms:
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
                        registrar_recarga(id_a,v,m, usuario_logado=st.session_state['user_name'])
                        disparar_alerta(id_a, "Recarga", v, f"Forma: {m}"); st.success("Sucesso!"); st.rerun()
            elif st.session_state.get('rec_mode')=='pix':
                st.info("Gerar QR Code Estático")
                v=st.number_input("Valor Pix",0.0,step=5.0)
                if v>0:
                    pix = PixPayload(CHAVE_PIX_ESCOLA, NOME_BENEFICIARIO, CIDADE_BENEFICIARIO, v); payload = pix.gerar_payload()
                    st.markdown("---"); c_qr, c_txt = st.columns([1, 2])
                    with c_qr: st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={payload}", caption="Ler no App do Banco")
                    with c_txt: st.code(payload); st.warning("Confira o comprovante.")
                    if st.button("✅ CONFIRMAR PIX"):
                        registrar_recarga(id_a, v, "PIX (QR)", usuario_logado=st.session_state['user_name'])
                        disparar_alerta(id_a, "Recarga Pix", v, "Via QR Code"); st.success("Creditado!"); st.rerun()
        else: st.warning("Sem alunos.")

    if menu == 'comprar' and "COMPRAR" in perms:
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
                    t=st.selectbox("Turma",sorted(df['turma'].dropna().unique())); 
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
                    else: realizar_venda_form(st.session_state['aid_venda'], origin='turma')

    if menu == 'hist' and "SALDO" in perms:
        st.markdown("---"); st.subheader("📜 Extrato e Histórico")
        df = get_all_alunos()
        if not df.empty:
            df = df.sort_values(by='nome'); df['lbl'] = df['nome'] + " | " + df['turma'].astype(str)
            sel = st.selectbox("Selecione o Aluno:", df['lbl'].unique())
            if st.button("ABRIR EXTRATO"): 
                st.session_state['hist_id'] = int(df[df['lbl'] == sel].iloc[0]['id'])
                st.session_state['hist_mode'] = 'view'
            
            if st.session_state.get('hist_mode') == 'view' and st.session_state.get('hist_id'):
                conn=sqlite3.connect(DB_FILE); conn.row_factory=sqlite3.Row; c=conn.cursor(); c.execute("SELECT * FROM alunos WHERE id=?",(st.session_state['hist_id'],)); al=c.fetchone(); conn.close()
                st.markdown(f"<div style='background:#f0f2f6;padding:20px;text-align:center'><h3>{al['nome']}</h3><h1>R$ {al['saldo']:.2f}</h1></div>",unsafe_allow_html=True)
                filt = st.selectbox("Filtro:", ["HOJE", "7 DIAS", "30 DIAS", "TODOS"])
                ext=get_extrato_aluno(al['id'], filt)
                if not ext.empty: 
                    st.dataframe(ext, column_config={"Valor": st.column_config.NumberColumn(format="R$ %.2f")}, hide_index=True, use_container_width=True)
                    c_p1, c_p2 = st.columns(2)
                    criar_botao_pdf_a4(ext, f"EXTRATO: {al['nome']}")
                    criar_botao_pdf_termico(ext, f"EXTRATO: {al['nome']}")
                else: st.info("Vazio.")
        else: st.warning("Sem alunos.")

    if menu == 'cancelar' and "CANCELAR VENDA" in perms:
        st.markdown("---"); st.subheader("🚫 Cancelar Venda")
        df = get_all_alunos()
        if not df.empty:
            df = df.sort_values(by='nome'); df['lbl'] = df['nome'] + " | " + df['turma'].astype(str)
            sel = st.selectbox("Selecione o Aluno para Estorno:", df['lbl'].unique())
            id_aluno = int(df[df['lbl'] == sel].iloc[0]['id'])
            
            filt_canc = st.selectbox("Período da Venda:", ["HOJE", "7 DIAS", "30 DIAS", "TODOS"])
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
            else: st.warning("Nenhuma venda encontrada para este aluno no período.")
        else: st.warning("Sem alunos.")

    if menu == 'relatorios' and "RELATÓRIOS DE VENDAS" in perms:
        st.markdown("---"); st.subheader("📊 Relatórios de Vendas")
        data_sel = st.date_input("Data:", datetime.now(), format="DD/MM/YYYY"); d_str = data_sel.strftime("%d/%m/%Y")
        st.write(f"Filtrando por: **{d_str}**"); st.markdown("---")
        turno_sel = st.radio("Turno:", ["DIA INTEIRO", "MATUTINO", "VESPERTINO"], horizontal=True); st.markdown("---")
        c1, c2, c3 = st.columns(3)
        if c1.button("📦 PRODUTOS", use_container_width=True): st.session_state['rel_mode'] = 'produtos'
        if c2.button("👥 ALUNOS", use_container_width=True): st.session_state['rel_mode'] = 'alunos'
        
        if st.session_state.get('rel_mode') == 'produtos':
            vis_mode = st.radio("Modo de Visualização:", ["VISÃO GERAL (TOTAL)", "DETALHADO POR TURMA"], horizontal=True)
            if vis_mode == "VISÃO GERAL (TOTAL)":
                df_p, tot = get_relatorio_produtos(d_str, turno_sel)
                if not df_p.empty:
                    st.metric(f"Total {turno_sel} (Estimado)", f"R$ {tot:.2f}")
                    st.dataframe(df_p, column_config={"Valor Total (R$)": st.column_config.NumberColumn(format="R$ %.2f")}, hide_index=True, use_container_width=True)
                    c1, c2 = st.columns(2)
                    criar_botao_pdf_a4(df_p, f"VENDAS GERAL ({turno_sel})")
                    criar_botao_pdf_termico(df_p, f"VENDAS GERAL ({turno_sel})")
                else: st.info("Nada vendido neste turno.")
            else:
                res_turmas = get_relatorio_produtos_por_turma(d_str, turno_sel)
                if res_turmas:
                    df_completo = pd.DataFrame()
                    for turma, df_t in res_turmas.items():
                        st.markdown(f"### {turma}"); st.dataframe(df_t, column_config={"Total": st.column_config.NumberColumn(format="R$ %.2f")}, hide_index=True, use_container_width=True); df_t['TURMA'] = turma; df_completo = pd.concat([df_completo, df_t])
                    c1, c2 = st.columns(2)
                    criar_botao_pdf_a4(res_turmas, f"POR TURMA ({turno_sel})", modo="turmas")
                    criar_botao_pdf_termico(res_turmas, f"POR TURMA ({turno_sel})", modo="turmas")
                else: st.info("Nada vendido neste turno.")
        elif st.session_state.get('rel_mode') == 'alunos':
            df_a = get_relatorio_alunos_dia(d_str)
            if not df_a.empty:
                st.dataframe(df_a, column_config={"Valor": st.column_config.NumberColumn(format="R$ %.2f")}, hide_index=True, use_container_width=True)
                c1, c2 = st.columns(2)
                criar_botao_pdf_a4(df_a, "RELATORIO ALUNOS")
                criar_botao_pdf_termico(df_a, "RELATORIO ALUNOS")
            else: st.info("Nada vendido.")
            
    if menu == 'rel_recargas' and "RELATÓRIO DE RECARGAS" in perms:
        st.markdown("---"); st.subheader("💳 Relatório Detalhado de Recargas")
        filtro_tempo = st.radio("Período:", ["HOJE", "ÚLTIMOS 7 DIAS", "ÚLTIMOS 15 DIAS", "ÚLTIMOS 30 DIAS"], horizontal=True)
        st.write(f"Exibindo recargas: **{filtro_tempo}**")
        df_recargas = get_relatorio_recargas_detalhado(filtro_tempo)
        if not df_recargas.empty:
            total_recargas = df_recargas['Valor'].sum()
            st.metric("Total Recarregado", f"R$ {total_recargas:.2f}")
            st.dataframe(df_recargas, column_config={"Valor": st.column_config.NumberColumn(format="R$ %.2f")}, hide_index=True, use_container_width=True)
            c1, c2 = st.columns(2)
            criar_botao_pdf_a4(df_recargas, f"RECARGAS ({filtro_tempo})")
            criar_botao_pdf_termico(df_recargas, f"RECARGAS ({filtro_tempo})")
        else: st.info("Nenhuma recarga encontrada neste período.")

    if menu == 'acesso' and "ADMINISTRADORES" in perms:
        st.markdown("---"); st.subheader("🔑 Gestão de Administradores")
        st.subheader("Cadastrar Novo Admin")
        with st.form("novo_admin"):
            nome_adm = st.text_input("Nome"); email_adm = st.text_input("E-mail (Login)"); senha_adm = st.text_input("Senha", type="password")
            st.write("**Permissões de Acesso:**")
            perms_selecionadas = st.multiselect("Selecione os módulos:", LISTA_PERMISSOES, default=LISTA_PERMISSOES)
            if st.form_submit_button("CRIAR ADMIN"):
                if criar_admin(email_adm, senha_adm, nome_adm, perms_selecionadas): st.success("Criado com sucesso!")
                else: st.error("Erro: E-mail já existe.")
        st.subheader("Gerenciar Admins")
        df_admins = get_all_admins()
        for index, row in df_admins.iterrows():
            c1, c2, c3 = st.columns([2, 2, 1])
            c1.write(f"**{row['nome']}** ({row['email']})")
            status = "Ativo" if row['ativo'] == 1 else "Bloqueado"
            c2.write(status)
            if row['email'] != 'admin': 
                btn_label = "Bloquear" if row['ativo'] == 1 else "Ativar"
                if c3.button(btn_label, key=f"adm_{row['id']}"):
                    novo_status = 0 if row['ativo'] == 1 else 1; toggle_admin_status(row['id'], novo_status); st.rerun()
            with st.expander(f"Ver permissões de {row['nome']}"):
                st.write(row['permissoes'].replace(",", " | ") if row['permissoes'] else "Nenhuma")

if st.session_state['logado']:
    if st.session_state['user_type'] == 'admin': menu_admin()
    else: menu_aluno()
else: login_screen()
