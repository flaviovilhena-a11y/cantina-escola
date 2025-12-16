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
        self.set_font('Arial', 'B', 9); cols = df.columns.tolist(); largeur = 190/len(cols
