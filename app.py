import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import database as db
import plotly.express as px
import os
import requests
import math
import time
from PIL import Image
try:
    from pillow_heif import register_heif_opener
    register_heif_opener() # Habilita suporte a HEIC/HEIF
except Exception:
    pass # pillow_heif e opcional
from streamlit_calendar import calendar
import socket
import qrcode
from io import BytesIO
from fpdf import FPDF
import hashlib

# Cache para coordenadas CEP
@st.cache_data(ttl=3600, show_spinner=False)
def get_coordinates_from_cep_cached(cep):
    """Versão com cache para buscar coordenadas de CEP"""
    return get_coordinates_from_cep(cep)

# Configuração da Página
st.set_page_config(page_title="MalaExpress - Sistema de Controle", page_icon="🧳", layout="wide")

# Inicializar banco e autenticacao
try:
    db.init_db()
except Exception as e:
    st.error(f"Erro ao inicializar banco de dados: {e}")
    st.stop()

if "usuario_logado" not in st.session_state:
    st.session_state.usuario_logado = None
if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False

# Tela de login (para acesso online e local)
if not st.session_state.auth_ok:
    st.title("🧳 MalaExpress")
    st.subheader("Acesso ao Sistema")
    st.info("Entre com seu email e senha para acessar o sistema.")
    with st.form("form_login"):
        email_login = st.text_input("Email", placeholder="ex: socio@malaexpress.local")
        senha_login = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar", use_container_width=True)
        if entrar:
            usuario = db.authenticate_user(email_login, senha_login)
            if usuario:
                st.session_state.usuario_logado = usuario
                st.session_state.auth_ok = True
                st.success(f"Bem-vindo, {usuario['nome']}!")
                st.rerun()
            else:
                st.error("Email ou senha inválidos.")

    with st.expander("ℹ️ Acessos iniciais", expanded=True):
        st.write("**Administrador:** `admin@malaexpress.local` / `MalaExpress2026!`")
        st.write("**Sócio:** `socio@malaexpress.local` / `Socio2026!`")
        st.caption("Depois você pode trocar as senhas e criar novos usuários.")
    st.stop()

# --- FUNÇÕES DE DISTÂNCIA E CEP ---
def get_coordinates_nominatim(query):
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1"
        headers = {'User-Agent': 'MalaExpressApp/1.0'}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200 and len(response.json()) > 0:
            data = response.json()[0]
            return float(data['lat']), float(data['lon'])
    except:
        return None, None
    return None, None

def get_coordinates_from_cep(cep):
    cep = cep.replace("-", "").replace(".", "").strip()
    if len(cep) != 8:
        return None, None
    
    try:
        url = f"https://brasilapi.com.br/api/cep/v2/{cep}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if 'location' in data and 'coordinates' in data['location']:
                coords = data['location']['coordinates']
                if 'latitude' in coords and 'longitude' in coords:
                    return float(coords['latitude']), float(coords['longitude'])
            
            # Se não tiver coords na BrasilAPI, tentar Nominatim com o endereço
            street = data.get('street', '')
            city = data.get('city', '')
            state = data.get('state', '')
            if city:
                query = f"{street}, {city}, {state}, Brazil"
                return get_coordinates_nominatim(query)
            
    except Exception as e:
        # st.error(f"Erro ao buscar CEP: {e}")
        pass
    
    return None, None

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Raio da Terra em km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) * math.sin(dlat / 2) + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) * math.sin(dlon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Inicializar Banco de Dados
if 'db_initialized' not in st.session_state:
    db.init_db()
    
    # Backup automático na inicialização
    try:
        ok, msg = db.backup_db()
    except:
        ok = False
    
    # Garantir que o "Caixa da Empresa" e "Cartão de Crédito" existam como opção de gestor
    try:
        gestores_init = db.get_gestores()
        nomes_gestores = gestores_init['nome'].values if not gestores_init.empty else []
        
        if 'Caixa da Empresa' not in nomes_gestores:
            db.add_gestor('Caixa da Empresa')
            
        if 'Cartão de Crédito' not in nomes_gestores:
            db.add_gestor('Cartão de Crédito')
    except:
        pass
        
    st.session_state['db_initialized'] = True

import calendar as py_calendar

# Função para gerar PDF do calendário
def create_pdf_schedule(df_reservas, mes_ano_str, mode='list'):
    class PDF(FPDF):
        def __init__(self, mode, orientation='P', unit='mm', format='A4'):
            super().__init__(orientation, unit, format)
            self.mode = mode

        def header(self):
            # Se for visual, o título muda a cada mês/página, então não setamos aqui fixo
            # Mas se for lista, setamos
            if self.mode == 'list':
                self.set_font("Arial", 'B', 16)
                self.cell(0, 10, txt=f"MalaExpress - Cronograma {mes_ano_str}", ln=True, align='C')
                self.ln(5)
            
                # Cabeçalho da Tabela (Repetir em cada página)
                self.set_font("Arial", 'B', 10)
                self.set_fill_color(200, 220, 255)
                # Mala (20), Tam (15), Cor (25), Cliente (55), Saida (25), Retorno (25), Status (25) = 190
                self.cell(20, 10, "Mala", 1, 0, 'C', 1)
                self.cell(15, 10, "Tam", 1, 0, 'C', 1)
                self.cell(25, 10, "Cor", 1, 0, 'C', 1)
                self.cell(55, 10, "Cliente", 1, 0, 'C', 1)
                self.cell(25, 10, "Saida", 1, 0, 'C', 1)
                self.cell(25, 10, "Retorno", 1, 0, 'C', 1)
                self.cell(25, 10, "Status", 1, 1, 'C', 1)
    
    # Orientação
    orientacao = 'L' if mode == 'visual' else 'P'
    pdf = PDF(mode=mode, orientation=orientacao)
    pdf.set_auto_page_break(auto=True, margin=15)
    
    if mode == 'list':
        pdf.add_page()
        # Dados em Lista
        pdf.set_font("Arial", size=9)
        for index, row in df_reservas.iterrows():
            # Tratar caracteres especiais (básico)
            try:
                cliente = str(row['cliente_nome'])[:28].encode('latin-1', 'replace').decode('latin-1')
                mala = str(row['mala_codigo']).encode('latin-1', 'replace').decode('latin-1')
                status = str(row['status']).encode('latin-1', 'replace').decode('latin-1')
                tamanho = str(row['mala_tamanho']).encode('latin-1', 'replace').decode('latin-1')
                cor = str(row['mala_cor']).encode('latin-1', 'replace').decode('latin-1')
            except:
                cliente = str(row['cliente_nome'])[:28]
                mala = str(row['mala_codigo'])
                status = str(row['status'])
                tamanho = str(row.get('mala_tamanho', ''))
                cor = str(row.get('mala_cor', ''))
            
            # Formatando datas (usar pd.to_datetime para garantir)
            try:
                d_saida = pd.to_datetime(row['data_saida']).strftime('%d/%m/%Y')
                d_volta = pd.to_datetime(row['data_prevista_retorno']).strftime('%d/%m/%Y')
            except:
                d_saida = str(row['data_saida'])
                d_volta = str(row['data_prevista_retorno'])

            pdf.cell(20, 10, mala, 1, 0, 'C')
            pdf.cell(15, 10, tamanho, 1, 0, 'C')
            pdf.cell(25, 10, cor, 1, 0, 'C')
            pdf.cell(55, 10, cliente, 1, 0, 'L')
            pdf.cell(25, 10, d_saida, 1, 0, 'C')
            pdf.cell(25, 10, d_volta, 1, 0, 'C')
            pdf.cell(25, 10, status, 1, 1, 'C')
            
    elif mode == 'visual':
        # Modo Grade Mensal
        pdf.set_font("Arial", size=8)
        
        # Identificar meses envolvidos
        # Se mes_ano_str for "Geral", "Todos" ou um range, precisamos determinar quais meses desenhar
        # Vamos usar a data mínima e máxima do DataFrame para saber quais meses cobrir
        if df_reservas.empty:
            start_dt = date.today()
            end_dt = date.today()
        else:
            start_dt = pd.to_datetime(df_reservas['data_saida'].min()).date()
            end_dt = pd.to_datetime(df_reservas['data_prevista_retorno'].max()).date()
            
            # Se start_dt for nulo (pode acontecer), fallback
            if pd.isna(start_dt): start_dt = date.today()
            if pd.isna(end_dt): end_dt = date.today()
        
        # Iterar pelos meses entre start_dt e end_dt
        current_date = start_dt.replace(day=1)
        end_date_limit = end_dt.replace(day=1)
        
        while current_date <= end_date_limit:
            ano = current_date.year
            mes = current_date.month
            
            pdf.add_page()
            
            # Cabeçalho do Mês
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 10, txt=f"MalaExpress - {current_date.strftime('%B/%Y')}", ln=True, align='C')
            pdf.ln(5)
            
            # Cabeçalho Dias da Semana
            dias_semana = ["SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"]
            largura_col = 38 # A4 Landscape width ~280 / 7 ~ 40
            altura_cel = 30 # Altura do dia
            
            pdf.set_fill_color(220, 220, 220)
            pdf.set_font("Arial", 'B', 10)
            for dia in dias_semana:
                pdf.cell(largura_col, 8, dia, 1, 0, 'C', 1)
            pdf.ln()
            
            # Obter matriz do calendário
            cal = py_calendar.monthcalendar(ano, mes)
            
            pdf.set_font("Arial", size=7)
            
            for semana in cal:
                y_start = pdf.get_y()
                x_start = pdf.get_x()
                
                if y_start + altura_cel > 190:
                    pdf.add_page()
                    # Redesenhar header (simplificado)
                    pdf.set_font("Arial", 'B', 16)
                    pdf.cell(0, 10, txt=f"{current_date.strftime('%B/%Y')} (Cont.)", ln=True, align='C')
                    pdf.ln(5)
                    pdf.set_font("Arial", 'B', 10)
                    for dia in dias_semana:
                        pdf.cell(largura_col, 8, dia, 1, 0, 'C', 1)
                    pdf.ln()
                    y_start = pdf.get_y()
                    pdf.set_font("Arial", size=7)
                
                for i, dia in enumerate(semana):
                    x_cell = x_start + (i * largura_col)
                    
                    pdf.set_xy(x_cell, y_start)
                    pdf.cell(largura_col, altura_cel, "", 1, 0)
                    
                    if dia != 0:
                        pdf.set_xy(x_cell + 1, y_start + 1)
                        pdf.set_font("Arial", 'B', 8)
                        pdf.cell(5, 5, str(dia), 0, 0)
                        
                        data_dia = date(ano, mes, dia)
                        eventos_dia = []
                        
                        for _, row in df_reservas.iterrows():
                            try:
                                val_sai = row['data_saida']
                                if isinstance(val_sai, str): dt_sai = datetime.strptime(val_sai, '%Y-%m-%d').date()
                                elif isinstance(val_sai, pd.Timestamp): dt_sai = val_sai.date()
                                else: dt_sai = val_sai
                                    
                                val_ret = row['data_prevista_retorno']
                                if isinstance(val_ret, str): dt_ret = datetime.strptime(val_ret, '%Y-%m-%d').date()
                                elif isinstance(val_ret, pd.Timestamp): dt_ret = val_ret.date()
                                else: dt_ret = val_ret
                            except:
                                continue
                            
                            mala_cod = str(row['mala_codigo'])
                            cli_nome = str(row['cliente_nome']).split()[0]
                            
                            if dt_sai == data_dia:
                                eventos_dia.append(f"> SAI: {mala_cod}")
                            elif dt_ret == data_dia:
                                eventos_dia.append(f"< VOLTA: {mala_cod}")
                            elif dt_sai < data_dia < dt_ret:
                                eventos_dia.append(f"| {mala_cod} ({cli_nome})")
                        
                        pdf.set_font("Arial", size=6)
                        y_evt = y_start + 6
                        for evt in eventos_dia[:6]:
                            pdf.set_xy(x_cell + 1, y_evt)
                            try: evt_safe = evt.encode('latin-1', 'replace').decode('latin-1')
                            except: evt_safe = evt
                            pdf.cell(largura_col - 2, 3, evt_safe, 0, 0)
                            y_evt += 3
                
                pdf.ln(altura_cel)
            
            # Avançar para o próximo mês
            if mes == 12:
                current_date = date(ano + 1, 1, 1)
            else:
                current_date = date(ano, mes + 1, 1)

    return pdf.output(dest='S').encode('latin-1')

def create_pdf_contrato(texto_contrato):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=11)
    
    # Tratamento básico de encoding
    try:
        texto_safe = texto_contrato.encode('latin-1', 'replace').decode('latin-1')
    except:
        texto_safe = texto_contrato
        
    # Título (removido daqui pois já está no texto)
    # pdf.set_font("Arial", 'B', 14)
    # pdf.cell(0, 10, txt="CONTRATO DE LOCAÇÃO", ln=True, align='C')
    # pdf.ln(10)
    
    # Corpo do texto
    pdf.set_font("Arial", size=10) # Tamanho um pouco menor para caber melhor
    
    # Usar multi_cell com alinhamento justificado ('J')
    pdf.multi_cell(0, 5, txt=texto_safe, align='J')
    
    # Espaço para assinaturas (já incluído no texto final, mas podemos reforçar se necessário)
    # Como o texto final já tem os campos de assinatura, não precisamos adicionar extra aqui.
    
    return pdf.output(dest='S').encode('latin-1')

def create_pdf_analise_financeira(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Título
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, txt="MalaExpress - Relatório Financeiro (ROI)", ln=True, align='C')
    pdf.cell(190, 10, txt=f"Gerado em: {date.today().strftime('%d/%m/%Y')}", ln=True, align='C')
    pdf.ln(10)
    
    # Totais
    total_investido = df['custo_aquisicao'].sum()
    total_faturado = df['total_faturado'].sum()
    saldo_geral = total_faturado - total_investido
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, txt=f"Total Investido: R$ {total_investido:,.2f}", ln=True)
    pdf.cell(0, 10, txt=f"Total Faturado: R$ {total_faturado:,.2f}", ln=True)
    pdf.cell(0, 10, txt=f"Saldo Geral: R$ {saldo_geral:,.2f}", ln=True)
    pdf.ln(10)
    
    # Tabela
    pdf.set_font("Arial", 'B', 9)
    pdf.set_fill_color(200, 220, 255)
    
    # Headers: Cód (20), Marca (45), Tam (15), Custo (28), Fat (28), Saldo (28), Status (25) = 189 (aprox A4 width)
    headers = [("Cod", 20), ("Marca", 45), ("Tam", 15), ("Custo", 28), ("Fat.", 28), ("Saldo", 28), ("Status", 25)]
    
    for header, width in headers:
        pdf.cell(width, 10, header, 1, 0, 'C', 1)
    pdf.ln()
    
    # Dados
    pdf.set_font("Arial", size=9)
    for index, row in df.iterrows():
        try:
            codigo = str(row['codigo']).encode('latin-1', 'replace').decode('latin-1')
            marca = str(row['marca'])[:22].encode('latin-1', 'replace').decode('latin-1') # Limitar tamanho
            tamanho = str(row['tamanho']).encode('latin-1', 'replace').decode('latin-1')
            status = str(row['status_roi']).encode('latin-1', 'replace').decode('latin-1')
        except:
            codigo = str(row['codigo'])
            marca = str(row['marca'])[:22]
            tamanho = str(row['tamanho'])
            status = str(row['status_roi'])
            
        pdf.cell(20, 10, codigo, 1, 0, 'C')
        pdf.cell(45, 10, marca, 1, 0, 'L')
        pdf.cell(15, 10, tamanho, 1, 0, 'C')
        pdf.cell(28, 10, f"{row['custo_aquisicao']:,.2f}", 1, 0, 'R')
        pdf.cell(28, 10, f"{row['total_faturado']:,.2f}", 1, 0, 'R')
        pdf.cell(28, 10, f"{row['saldo']:,.2f}", 1, 0, 'R')
        pdf.cell(25, 10, status, 1, 1, 'C')
        
    return pdf.output(dest='S').encode('latin-1')

def create_pdf_balanco_geral(df_extrato, totais):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Título
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, txt="MalaExpress - Balanço Geral", ln=True, align='C')
    pdf.cell(190, 10, txt=f"Gerado em: {date.today().strftime('%d/%m/%Y')}", ln=True, align='C')
    pdf.ln(5)
    
    # Resumo Executivo
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Resumo Executivo", ln=True)
    pdf.set_font("Arial", size=11)
    
    pdf.cell(0, 8, f"Faturamento Bruto (Entradas): R$ {totais['faturamento']:,.2f}", ln=True)
    pdf.cell(0, 8, f"Total Reinvestido/Gasto (Saídas): R$ {totais['saidas']:,.2f}", ln=True)
    
    # Cor do Saldo
    saldo = totais['saldo']
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"Saldo Disponível em Caixa: R$ {saldo:,.2f}", ln=True)
    pdf.ln(5)
    
    # Extrato Detalhado
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "Extrato Detalhado de Movimentações", ln=True)
    
    pdf.set_font("Arial", 'B', 9)
    pdf.set_fill_color(220, 220, 220)
    
    # Headers: Data (25), Tipo (35), Descrição (90), Valor (30)
    headers = [("Data", 25), ("Tipo", 35), ("Descrição", 90), ("Valor", 30)]
    for header, width in headers:
        pdf.cell(width, 8, header, 1, 0, 'C', 1)
    pdf.ln()
    
    pdf.set_font("Arial", size=9)
    for index, row in df_extrato.iterrows():
        try:
            data = pd.to_datetime(row['data']).strftime('%d/%m/%Y')
            tipo = str(row['tipo']).encode('latin-1', 'replace').decode('latin-1')
            desc = str(row['descricao'])[:55].encode('latin-1', 'replace').decode('latin-1')
        except:
            data = str(row['data'])
            tipo = str(row['tipo'])
            desc = str(row['descricao'])[:55]
            
        valor = row['valor']
        
        pdf.cell(25, 8, data, 1, 0, 'C')
        pdf.cell(35, 8, tipo, 1, 0, 'L')
        pdf.cell(90, 8, desc, 1, 0, 'L')
        pdf.cell(30, 8, f"{valor:,.2f}", 1, 1, 'R')
        
    return pdf.output(dest='S').encode('latin-1')

def create_pdf_ranking(df_ranking):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Título
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, txt="MalaExpress - Ranking de Popularidade", ln=True, align='C')
    pdf.cell(190, 10, txt=f"Gerado em: {date.today().strftime('%d/%m/%Y')}", ln=True, align='C')
    pdf.ln(10)
    
    # Cabeçalho da Tabela
    pdf.set_font("Arial", 'B', 10)
    pdf.set_fill_color(200, 220, 255)
    
    # Columns: Pos (15), Mala (85), Qtd (20), Faturado (35), Custo (35)
    headers = [("Pos", 15), ("Mala (Cod - Tam - Cor)", 85), ("Qtd", 20), ("Faturado", 35), ("Custo", 35)]
    
    for header, width in headers:
        pdf.cell(width, 10, header, 1, 0, 'C', 1)
    pdf.ln()
    
    # Dados
    pdf.set_font("Arial", size=10)
    for index, row in df_ranking.iterrows():
        pos = str(index + 1)
        mala_desc = f"{row['codigo']} - {row['tamanho']} ({row['cor']})"
        qtd = str(row['qtd_alugueis'])
        faturado = f"R$ {row['total_faturado']:,.2f}"
        custo = f"R$ {row['custo_aquisicao']:,.2f}"
        
        # Encoding básico
        try:
            mala_desc = mala_desc.encode('latin-1', 'replace').decode('latin-1')
        except:
            pass
            
        pdf.cell(15, 10, pos, 1, 0, 'C')
        pdf.cell(85, 10, mala_desc, 1, 0, 'L')
        pdf.cell(20, 10, qtd, 1, 0, 'C')
        pdf.cell(35, 10, faturado, 1, 0, 'R')
        pdf.cell(35, 10, custo, 1, 1, 'R')
        
    return pdf.output(dest='S').encode('latin-1')

def create_pdf_galeria(df_malas):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Título
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, txt="MalaExpress - Catálogo de Estoque", ln=True, align='C')
    pdf.cell(190, 10, txt=f"Gerado em: {date.today().strftime('%d/%m/%Y')}", ln=True, align='C')
    pdf.ln(10)
    
    # Cabeçalho da Tabela
    pdf.set_font("Arial", 'B', 10)
    pdf.set_fill_color(200, 220, 255)
    
    # Headers: Foto(30), Cod(20), Marca(40), Tam(20), Cor(30), Status(30), Valor(20)
    headers = [("Foto", 30), ("Cod", 20), ("Marca", 40), ("Tam", 20), ("Cor", 30), ("Status", 30), ("Custo", 20)]
    
    for header, width in headers:
        pdf.cell(width, 10, header, 1, 0, 'C', 1)
    pdf.ln()
    
    # Dados
    pdf.set_font("Arial", size=9)
    line_height = 25 # Altura para caber foto
    
    for index, row in df_malas.iterrows():
        # Verificar quebra de página
        if pdf.get_y() + line_height > 270: # Margem inferior aprox
            pdf.add_page()
            pdf.set_font("Arial", 'B', 10)
            pdf.set_fill_color(200, 220, 255)
            for header, width in headers:
                pdf.cell(width, 10, header, 1, 0, 'C', 1)
            pdf.ln()
            pdf.set_font("Arial", size=9)
            
        y_start = pdf.get_y()
        x_start = pdf.get_x()
        
        # 1. Foto (desenhar célula vazia com borda primeiro)
        pdf.cell(30, line_height, "", 1, 0)
        
        # Inserir imagem sobreposta
        if row['imagem_path'] and os.path.exists(row['imagem_path']):
            try:
                # Ajustar imagem para caber no box 30x25 (margem 2mm -> 26x21)
                # FPDF image(name, x, y, w, h)
                # Vamos fixar altura em 21mm e deixar largura proporcional
                pdf.image(row['imagem_path'], x=x_start+2, y=y_start+2, h=21)
            except:
                pass # Se falhar, fica em branco
        
        # 2. Dados Texto
        # Preparar strings
        try:
            cod = str(row['codigo'])
            marca = str(row['marca'])[:20].encode('latin-1', 'replace').decode('latin-1')
            tam = str(row['tamanho']).encode('latin-1', 'replace').decode('latin-1')
            cor = str(row['cor'])[:15].encode('latin-1', 'replace').decode('latin-1')
            status = str(row['status']).encode('latin-1', 'replace').decode('latin-1')
        except:
            cod = str(row['codigo'])
            marca = str(row['marca'])[:20]
            tam = str(row['tamanho'])
            cor = str(row['cor'])[:15]
            status = str(row['status'])
            
        custo = f"{row.get('valor_pago', 0) or 0:,.2f}"
        
        # Usar cells normais alinhadas
        # O problema é que cell normal alinha texto no topo ou base dependendo da lib, mas FPDF padrão é base/middle baseline.
        # Para alinhar verticalmente no meio de 25mm, é chato. Vamos deixar padrão (topo/meio).
        
        # Resetar X para continuar a linha (já desenhamos a cell da foto, o cursor avançou 30)
        # Mas como desenhamos a cell da foto com ln=0, o cursor está em x_start + 30. Correto.
        
        # Truque para centralizar verticalmente: usar MultiCell ou setar Y
        # Vamos simplificar: Cell com altura line_height centraliza verticalmente? Não, fica no topo.
        # Vamos usar uma margem Y se quiser, mas para simplicidade, vai direto.
        
        pdf.cell(20, line_height, cod, 1, 0, 'C')
        pdf.cell(40, line_height, marca, 1, 0, 'L')
        pdf.cell(20, line_height, tam, 1, 0, 'C')
        pdf.cell(30, line_height, cor, 1, 0, 'L')
        pdf.cell(30, line_height, status, 1, 0, 'C')
        pdf.cell(20, line_height, custo, 1, 1, 'R') # ln=1 para pular linha
        
    return pdf.output(dest='S').encode('latin-1')

# Inicializar estado de navegação e pré-seleção
if 'page' not in st.session_state:
    st.session_state.page = "Dashboard"
if 'preselected_mala_id' not in st.session_state:
    st.session_state.preselected_mala_id = None
# IDs para resetar formulários
if 'form_mala_key' not in st.session_state:
    st.session_state.form_mala_key = 0
if 'form_cliente_key' not in st.session_state:
    st.session_state.form_cliente_key = 0

# Função de navegação
def navigate_to(page, mala_id=None):
    st.session_state.page = page
    if mala_id:
        st.session_state.preselected_mala_id = mala_id

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

@st.cache_resource
def start_ngrok():
    try:
        # Tenta conectar
        public_url = ngrok.connect(8501, "http")
        return public_url.public_url
    except Exception as e:
        return None

# --- Funções de Cache para Queries Frequentes ---
@st.cache_data(ttl=300, show_spinner=False)
def get_status_estoque_cached():
    """Versão com cache para status do estoque"""
    return db.get_status_estoque()

@st.cache_data(ttl=300, show_spinner=False)
def get_malas_disponiveis_cached(data_inicio, data_fim):
    """Versão com cache para malas disponíveis"""
    return db.get_malas_disponiveis_por_data(data_inicio, data_fim)

@st.cache_data(ttl=300, show_spinner=False)
def get_alugueis_ativos_cached():
    """Versão com cache para aluguéis ativos"""
    return db.get_alugueis_ativos()

@st.cache_data(ttl=300, show_spinner=False)
def get_malas_cached(status=None):
    """Versão com cache para malas"""
    return db.get_malas(status=status)

# Cache para outras funções frequentes
@st.cache_data(ttl=300, show_spinner=False)
def get_clientes_cached():
    """Versão com cache para clientes"""
    return db.get_clientes()

@st.cache_data(ttl=300, show_spinner=False)
def get_gestores_cached():
    """Versão com cache para gestores"""
    return db.get_gestores()

def invalidate_cache():
    """Função para invalidar todos os caches quando houver alteração"""
    get_status_estoque_cached.clear()
    get_malas_disponiveis_cached.clear()
    get_alugueis_ativos_cached.clear()
    get_malas_cached.clear()
    get_clientes_cached.clear()
    get_gestores_cached.clear()

# Criar pasta de imagens se não existir
if not os.path.exists("imagens_malas"):
    os.makedirs("imagens_malas")

# Título Principal
st.title("🧳 MalaExpress - Controle de Aluguéis")

# --- Detecção Mobile e Acesso Externo ---
try:
    user_agent = st.context.headers.get("User-Agent", "").lower()
    is_mobile = any(m in user_agent for m in ["mobile", "android", "iphone", "ipad", "tablet"])
except Exception:
    is_mobile = False

# Verificar acesso externo (não vem da rede local)
is_external = True
try:
    client_host = st.context.headers.get("Host", "")
    # Se o host é localhost/127 ou rede local, não é externo
    if "localhost" in client_host or "127.0.0.1" in client_host or ".local" in client_host:
        is_external = False
except Exception:
    is_external = False

# Se acesso externo E mobile E NÃO é a rede local, restringir a Novo Aluguel
if is_external and is_mobile and st.session_state.page == "Dashboard":
    st.warning("📱 Acesso mobile externo restrito. Redirecionando para Novo Aluguel...")
    st.session_state.page = "Novo Aluguel"
    st.rerun()

# Navegação Lateral
menu_restrito = ["Novo Aluguel"]
menu_completo = ["Dashboard", "Cadastrar Mala", "Cadastrar Cliente", "Novo Aluguel", "Devoluções", "Calendário de Reservas", "Análise Financeira", "Contrato de Aluguel", "🛒 Vender Mala", "🚚 Calculadora de Frete", "📱 Acesso Mobile"]
# Menu do socio: visualizacao + cadastro de alugueis, sem acesso a financeiro/cadastros criticos
menu_socio = ["Dashboard", "Cadastrar Mala", "Cadastrar Cliente", "Novo Aluguel", "Devoluções", "Calendário de Reservas", "Contrato de Aluguel"]

# Definir menu baseado no role do usuario logado
user_role_atual = st.session_state.get("usuario_logado", {}).get("role", "admin")
if user_role_atual == "socio":
    menu = menu_socio
elif is_external and is_mobile:
    menu = menu_restrito
else:
    menu = menu_completo

# Mostrar info de conexão
if is_external and is_mobile:
    st.info("📱 **Modo Mobile Externo** — Apenas 'Novo Aluguel' disponível.")

# Sincronizar sidebar com session_state
choice = st.sidebar.radio("Menu", menu, index=menu.index(st.session_state.page) if st.session_state.page in menu else 0)
# Atualizar page se o usuário mudar manualmente no sidebar
if choice != st.session_state.page:
    # Se acesso externo + mobile, não permite mudar para outras páginas
    if is_external and is_mobile and choice != "Novo Aluguel":
        st.warning("📱 Acesso restrito. Apenas 'Novo Aluguel' está disponível.")
        choice = st.session_state.page  # Não muda
    else:
        st.session_state.page = choice
    st.rerun()

# Se tentar acessar página restrita via URL (não sidebar), redirecionar
if is_external and is_mobile and st.session_state.page != "Novo Aluguel":
    st.warning("📱 Acesso mobile externo restrito. Apenas 'Novo Aluguel' está disponível.")
    st.session_state.page = "Novo Aluguel"
    st.rerun()

# Se socio tentar acessar pagina restrita (Análise Financeira, Vender Mala, Calculadora, Acesso Mobile), redirecionar
if user_role_atual == "socio" and st.session_state.page in ["Análise Financeira", "🛒 Vender Mala", "🚚 Calculadora de Frete", "📱 Acesso Mobile"]:
    st.warning("Acesso restrito. Essa aba é só para administradores.")
    st.session_state.page = "Dashboard"
    st.rerun()

# Info do usuario logado e logout (sidebar)
with st.sidebar:
    st.divider()
    user_atual = st.session_state.get("usuario_logado") or {}
    role_emoji = "👑" if user_atual.get("role") == "admin" else "👤"
    st.caption(f"{role_emoji} **{user_atual.get('nome', 'Convidado')}** ({user_atual.get('role', '?')})")
    if st.button("🚪 Sair", use_container_width=True, key="btn_logout"):
        st.session_state.auth_ok = False
        st.session_state.usuario_logado = None
        st.rerun()

# --- DASHBOARD ---
if st.session_state.page == "Dashboard":
    st.subheader("Visão Geral do Estoque e Aluguéis")
    
    col1, col2, col3 = st.columns(3)
    
    # Métricas (com cache)
    total_malas, total_disponiveis = get_status_estoque_cached()
    # Malas disponíveis HOJE (considerando aluguéis ativos)
    malas_disponiveis_hoje = len(get_malas_disponiveis_cached(date.today(), date.today()))
    alugueis_ativos = len(get_alugueis_ativos_cached())
    
    col1.metric("Total de Malas no Estoque", total_malas)
    col2.metric("Disponíveis para Hoje", malas_disponiveis_hoje)
    col3.metric("Aluguéis Ativos", alugueis_ativos)
    
    # --- Info de Frete Acumulado ---
    total_fretes = db.get_total_fretes_acumulados()
    if total_fretes > 0:
        st.info(f"🚚 **Frete Estimado Acumulado (referência):** R$ {total_fretes:,.2f} | *Este valor não entra no faturamento, é apenas para referência.*")
    # --------------------------------
    
    st.divider()
    
    # --- NOVO: Lembrete de Devoluções Próximas ---
    # Buscar aluguéis que vencem hoje ou amanhã (com cache)
    todos_alugueis = get_alugueis_ativos_cached()
    if not todos_alugueis.empty:
        # Converter para datetime
        todos_alugueis['data_prevista_retorno'] = pd.to_datetime(todos_alugueis['data_prevista_retorno'])
        hoje = pd.Timestamp(date.today())
        amanha = hoje + pd.Timedelta(days=1)
        
        # Filtrar
        devolucoes_amanha = todos_alugueis[todos_alugueis['data_prevista_retorno'].dt.date == amanha.date()]
        
        if not devolucoes_amanha.empty:
            st.warning(f"⚠️ **ATENÇÃO:** Existem {len(devolucoes_amanha)} devoluções agendadas para **AMANHÃ** ({amanha.strftime('%d/%m')})!")
            for _, row in devolucoes_amanha.iterrows():
                st.write(f"- 🧳 **{row['mala_codigo']}** | Cliente: **{row['cliente_nome']}** (Devolução)")
                
        # Filtrar Saídas (Retiradas) para Amanhã
        # O banco retorna todas, precisamos filtrar as que a data_saida é amanhã
        # Como get_alugueis_ativos pega status='Ativo', ele pega reservas futuras também.
        # Vamos converter data_saida também
        todos_alugueis['data_saida'] = pd.to_datetime(todos_alugueis['data_saida'])
        saidas_amanha = todos_alugueis[todos_alugueis['data_saida'].dt.date == amanha.date()]
        
        if not saidas_amanha.empty:
            st.info(f"🚀 **PRÓXIMAS SAÍDAS:** Existem {len(saidas_amanha)} retiradas agendadas para **AMANHÃ** ({amanha.strftime('%d/%m')})!")
            for _, row in saidas_amanha.iterrows():
                st.write(f"- 🧳 **{row['mala_codigo']}** | Cliente: **{row['cliente_nome']}** (Retirada)")
                
    # -----------------------------------------------
    
    st.divider()

    # Barra de Progresso de Ocupação
    if total_malas > 0:
        ocupacao = (total_malas - malas_disponiveis_hoje) / total_malas
        st.write(f"**Taxa de Ocupação Atual:** {ocupacao:.0%}")
        st.progress(ocupacao)

    with st.expander("💾 Backup do Banco de Dados", expanded=False):
        st.write("Faça backup do banco agora. Os arquivos ficam salvos na pasta `backups/` (mantém os 10 mais recentes).")
        col_bk1, col_bk2 = st.columns([1, 2])
        with col_bk1:
            if st.button("💾 Fazer Backup Agora", type="primary", use_container_width=True):
                ok_bk, msg_bk = db.backup_db()
                if ok_bk:
                    st.success(f"✅ {msg_bk}")
                else:
                    st.error(f"❌ {msg_bk}")
        with col_bk2:
            try:
                pasta_backup = db.BACKUP_DIR
                if os.path.exists(pasta_backup):
                    arquivos = sorted([f for f in os.listdir(pasta_backup) if f.startswith("mala_express_") and f.endswith(".db")], reverse=True)
                    if arquivos:
                        st.caption(f"📁 Últimos backups em `{pasta_backup}`:")
                        for arq in arquivos[:5]:
                            tamanho = os.path.getsize(os.path.join(pasta_backup, arq))
                            st.caption(f"• {arq} ({tamanho/1024:.1f} KB)")
                        if len(arquivos) > 5:
                            st.caption(f"... e mais {len(arquivos) - 5} backups antigos.")
                    else:
                        st.caption("Nenhum backup ainda. Use o botão ao lado para criar o primeiro.")
                else:
                    st.caption("Pasta de backup ainda não existe.")
            except Exception as e:
                st.caption(f"Não foi possível listar backups: {e}")

    with st.expander("🛑 Malas Quebradas (fora do estoque)", expanded=False):
        if 'ultima_mala_quebrada' in st.session_state and st.session_state['ultima_mala_quebrada']:
            st.warning(f"Última mala marcada como quebrada: {st.session_state['ultima_mala_quebrada']}")
        df_quebradas = get_malas_cached(status='Quebrada')
        if df_quebradas.empty:
            st.info("Nenhuma mala quebrada registrada.")
        else:
            st.write(f"Total de malas quebradas: {len(df_quebradas)}")
            cols_show = ['codigo', 'tamanho', 'dimensoes', 'cor', 'marca', 'data_compra', 'valor_pago']
            cols_show = [c for c in cols_show if c in df_quebradas.columns]
            st.dataframe(df_quebradas[cols_show], use_container_width=True)

    with st.expander("🛒 Malas Vendidas (Histórico)", expanded=False):
        df_vendidas = get_malas_cached(status='Vendida')
        if df_vendidas.empty:
            st.info("Nenhuma mala vendida registrada. As vendas aparecem aqui após serem registradas na aba '🛒 Vender Mala'.")
        else:
            st.write(f"Total de malas vendidas: {len(df_vendidas)}")
            cols_show_v = ['codigo', 'tamanho', 'cor', 'marca', 'data_compra', 'valor_pago']
            cols_show_v = [c for c in cols_show_v if c in df_vendidas.columns]
            st.dataframe(df_vendidas[cols_show_v], use_container_width=True)
            st.caption("💡 Para detalhes da venda (cliente, valor, data, lucro), veja 'Análise Financeira → 🛒 Vendas de Malas'.")
    
    st.subheader("Galeria de Malas Disponíveis")
    
    # Buscar todas as malas (com cache)
    df_malas = get_malas_cached()
    
    if not df_malas.empty:
        # --- Botão Download PDF Galeria ---
        col_gal1, col_gal2 = st.columns([0.7, 0.3])
        col_gal1.write("Visualize abaixo o estoque completo.")
        with col_gal2:
            pdf_galeria = create_pdf_galeria(df_malas)
            st.download_button(
                label="📄 Baixar Catálogo (PDF)",
                data=pdf_galeria,
                file_name=f"catalogo_malas_{date.today()}.pdf",
                mime="application/pdf"
            )
        # ----------------------------------

        # Filtrar apenas malas disponíveis (status 'Disponível') - Opcional, ou mostrar todas com status
        # Vamos mostrar todas, mas destacar status
        
        # Grid layout (usando container e colunas dinâmicas)
        # Streamlit não tem grid nativo perfeito, então vamos iterar em chunks de 4
        
        num_columns = 4
        chunks = [df_malas.iloc[i:i + num_columns] for i in range(0, len(df_malas), num_columns)]
        
        for chunk in chunks:
            cols = st.columns(num_columns)
            for i, (_, row) in enumerate(chunk.iterrows()):
                with cols[i]:
                    with st.container(border=True):
                        # Imagem
                        if row['imagem_path'] and os.path.exists(row['imagem_path']):
                            st.image(row['imagem_path'], use_container_width=True)
                        else:
                            st.image("https://via.placeholder.com/300x200?text=Sem+Foto", use_container_width=True)
                        
                        st.markdown(f"**{row['codigo']}** - {row['marca']}")
                        st.text(f"Tam: {row['tamanho']} | Cor: {row['cor']}")
                        dim_txt = row.get('dimensoes', '') if 'dimensoes' in row else ''
                        if pd.notna(dim_txt) and str(dim_txt).strip():
                            st.text(f"Medidas: {dim_txt}")
                        
                        status_color = "green" if row['status'] == 'Disponível' else "red"
                        st.markdown(f"Status: :{status_color}[{row['status']}]")
                        
                        if row['status'] == 'Disponível':
                            col_btn1, col_btn2 = st.columns(2)
                            with col_btn1:
                                if st.button(f"Alugar {row['codigo']}", key=f"btn_rent_{row['id']}"):
                                    navigate_to("Novo Aluguel", mala_id=row['id'])
                                    st.rerun()
                            with col_btn2:
                                if st.button(f"✏️ Editar", key=f"btn_edit_gal_{row['id']}"):
                                    st.session_state['edit_mala_id'] = row['id']
                                    st.session_state.page = "Cadastrar Mala"
                                    st.rerun()
                        else:
                            col_btn1, col_btn2 = st.columns(2)
                            with col_btn1:
                                if st.button(f"📅 Agendar", key=f"btn_rent_fut_{row['id']}"):
                                    navigate_to("Novo Aluguel", mala_id=row['id'])
                                    st.rerun()
                            with col_btn2:
                                if st.button(f"✏️ Editar", key=f"btn_edit_gal2_{row['id']}"):
                                    st.session_state['edit_mala_id'] = row['id']
                                    st.session_state.page = "Cadastrar Mala"
                                    st.rerun()
    else:
        st.info("Nenhuma mala cadastrada.")

# --- CADASTRAR MALA ---
elif st.session_state.page == "Cadastrar Mala":

    st.subheader("Cadastrar Nova Mala")
    
    # Obter próximo código
    proximo_codigo = db.get_proximo_codigo()
    st.info(f"O próximo código gerado automaticamente será: **{proximo_codigo}**")
    
    # Carregar Gestores para o formulário
    df_gestores = get_gestores_cached()
    opcoes_gestores = {}
    if not df_gestores.empty:
        opcoes_gestores = {row['nome']: row['id'] for _, row in df_gestores.iterrows()}
        
    with st.form("form_mala", clear_on_submit=True):
        col1, col2 = st.columns(2)
        # codigo = col1.text_input("Código da Mala (Ex: M001)") # Removido
        
        # Opção "Outro" para tamanho personalizado
        tamanho_selecao = col1.selectbox("Tamanho / Tipo", ["P", "M", "G", "Frasqueira", "Bolsa", "Mochila", "Malinha", "Diversos", "Outro"], key="cad_tamanho_sel")
        
        if tamanho_selecao == "Outro":
            tamanho_personalizado = col1.text_input("Digite o Tamanho/Descrição", key="cad_tamanho_desc")
            tamanho = tamanho_personalizado
        else:
            tamanho = tamanho_selecao
            
        marca = col2.text_input("Marca", key="cad_marca")
        
        col3, col4 = st.columns(2)
        cor = col3.text_input("Cor", key="cad_cor")
        dimensoes = col4.text_input("Dimensões (cm) (Opcional)", placeholder="Ex: 55x35x24", key="cad_dimensoes")
        valor_pago = st.number_input("Valor Pago (R$) (Opcional)", min_value=0.0, step=10.0, value=0.0, key="cad_valor")
        
        # Data da Compra
        data_compra = st.date_input("Data da Compra", date.today(), key="cad_data_compra")
        
        # Seleção de Gestor
        gestor_id = None
        if opcoes_gestores:
            # Ordenar lista para "Caixa da Empresa" e "Cartão de Crédito" aparecerem primeiro
            lista_gestores = list(opcoes_gestores.keys())
            
            # Remover para reordenar
            if "Caixa da Empresa" in lista_gestores: lista_gestores.remove("Caixa da Empresa")
            if "Cartão de Crédito" in lista_gestores: lista_gestores.remove("Cartão de Crédito")
            
            # Adicionar no início
            lista_gestores = ["Caixa da Empresa", "Cartão de Crédito"] + lista_gestores
            
            gestor_selecionado = st.selectbox("Quem pagou essa mala? (Investidor/Origem)", ["Selecione...", "Não Informado"] + lista_gestores)
            
            if gestor_selecionado not in ["Selecione...", "Não Informado"]:
                gestor_id = int(opcoes_gestores[gestor_selecionado])
        else:
            st.info("Cadastre gestores na aba 'Análise Financeira'.")
            
        # Forma de Pagamento e Parcelas
        col_pag1, col_pag2 = st.columns(2)
        
        # Tentar inferir forma de pagamento pelo gestor
        index_pagamento = 0
        if gestor_selecionado == "Cartão de Crédito":
            index_pagamento = 1 # Cartão de Crédito
            
        forma_pagamento = col_pag1.selectbox("Forma de Pagamento", ["Dinheiro/Pix", "Cartão de Crédito", "Débito"], index=index_pagamento)
        
        parcelas = 1
        if forma_pagamento == "Cartão de Crédito":
            parcelas = col_pag2.number_input("Nº de Parcelas", min_value=1, max_value=24, value=1, step=1)
        
        imagem = st.file_uploader("Foto da Mala (Opcional)", type=["jpg", "png", "jpeg", "img", "heic", "heif"], key="cad_imagem")
        
        submit = st.form_submit_button("Cadastrar")
        
        if submit:
            # Tentar cadastrar com o código gerado
            # Se houver concorrência, pode falhar, então idealmente geramos no insert ou tratamos erro
            # Para simplicidade aqui, vamos usar o gerado.
            
            # Recalcular código para garantir (caso outro usuário tenha cadastrado nesse meio tempo)
            codigo_final = db.get_proximo_codigo()
            
            # Salvar imagem se houver
            imagem_path = None
            if imagem:
                try:
                    # Usar PIL para processar a imagem
                    img = Image.open(imagem)
                    
                    # Redimensionar se for muito grande (max largura 1024px)
                    if img.width > 1024:
                        ratio = 1024.0 / img.width
                        new_height = int(img.height * ratio)
                        img = img.resize((1024, new_height))
                    
                    # Garantir nome de arquivo seguro
                    extensao = imagem.name.split('.')[-1].lower()
                    if not extensao or extensao in ['heic', 'heif']:
                        extensao = "jpg" # Converter HEIC para JPG
                        
                    nome_arquivo = f"{codigo_final}_{int(datetime.now().timestamp())}.{extensao}"
                    
                    # Caminhos
                    caminho_relativo = f"imagens_malas/{nome_arquivo}"
                    caminho_completo = os.path.join("imagens_malas", nome_arquivo)
                    
                    # Salvar
                    if img.mode != 'RGB':
                        img = img.convert('RGB') # Converter para RGB antes de salvar como JPG
                        
                    img.save(caminho_completo)
                    
                    # Salvar no banco o caminho relativo
                    imagem_path = caminho_relativo
                except Exception as e:
                    st.error(f"Erro ao salvar imagem: {e}")
            
            if tamanho:
                if db.add_mala(codigo_final, tamanho, cor, marca, valor_pago if valor_pago > 0 else None, imagem_path, gestor_id, data_compra=data_compra, forma_pagamento=forma_pagamento, parcelas=parcelas, dimensoes=dimensoes):
                    st.success(f"Mala {codigo_final} cadastrada com sucesso!")
                    if imagem_path:
                        st.info("Imagem salva com sucesso!")
                    # clear_on_submit=True no form ja limpa todos os campos automaticamente
                    st.rerun() # Recarregar para atualizar o proximo codigo
                else:
                    st.error("Erro ao cadastrar mala. Tente novamente.")
            else:
                st.warning("Preencha o tamanho.")
                
    st.divider()
    
    # Seção de Gerenciamento (Exclusão e Edição)
    st.markdown("### ⚙️ Gerenciar Estoque")
    
    malas_cadastradas = db.get_malas()
    
    if not malas_cadastradas.empty:
        # Criar tabs para separar Excluir, Editar e Vender
        tab_editar, tab_vender_mala, tab_excluir = st.tabs(["✏️ Editar Mala", "🛒 Vender Mala", "🗑️ Excluir Mala"])
        
        with tab_editar:
            opcoes_mala = malas_cadastradas.apply(lambda x: f"{x['codigo']} - {x['marca']} - {x['tamanho']} ({x['cor']})", axis=1)
            mala_editar_str = st.selectbox("Selecione a Mala para Editar", options=opcoes_mala, key="sel_editar_mala")
            
            # Recuperar dados
            mala_edit_selecionada = malas_cadastradas[opcoes_mala == mala_editar_str].iloc[0]
            
            with st.form("form_editar_mala"):
                st.write(f"Editando: **{mala_edit_selecionada['codigo']}**")

                # Mostrar foto da mala
                img_path_ed = mala_edit_selecionada.get('imagem_path', '')
                if img_path_ed and os.path.exists(str(img_path_ed)):
                    st.image(img_path_ed, caption=f"Foto: {mala_edit_selecionada['codigo']}", width=200)
                else:
                    st.info("Esta mala não possui foto cadastrada.")
                
                col_ed1, col_ed2 = st.columns(2)
                
                # Tamanho com suporte a "Outro"
                tamanho_atual = mala_edit_selecionada['tamanho']
                opcoes_tamanho = ["P", "M", "G", "Frasqueira", "Bolsa", "Mochila", "Malinha", "Diversos", "Outro"]
                
                # Tenta achar o índice, se não achar, assume que é personalizado ("Outro")
                if tamanho_atual in ["P", "M", "G", "Frasqueira"]:
                    index_tamanho = opcoes_tamanho.index(tamanho_atual)
                    tamanho_custom_valor = ""
                else:
                    index_tamanho = opcoes_tamanho.index("Outro")
                    tamanho_custom_valor = tamanho_atual
                
                novo_tamanho_sel = col_ed1.selectbox("Tamanho", opcoes_tamanho, index=index_tamanho)
                
                if novo_tamanho_sel == "Outro":
                    novo_tamanho = col_ed1.text_input("Descrição do Tamanho", value=tamanho_custom_valor)
                else:
                    novo_tamanho = novo_tamanho_sel
                
                nova_marca = col_ed2.text_input("Marca", value=mala_edit_selecionada['marca'])
                
                col_ed3, col_ed4 = st.columns(2)
                nova_cor = col_ed3.text_input("Cor", value=mala_edit_selecionada['cor'])
                # Tratar valor_pago que pode ser None
                val_pago_atual = float(mala_edit_selecionada['valor_pago']) if pd.notna(mala_edit_selecionada['valor_pago']) else 0.0
                novo_valor = col_ed4.number_input("Valor Pago (R$)", min_value=0.0, step=10.0, value=val_pago_atual)
                
                dim_atual = ''
                if 'dimensoes' in mala_edit_selecionada and pd.notna(mala_edit_selecionada['dimensoes']):
                    dim_atual = str(mala_edit_selecionada['dimensoes'])
                nova_dimensoes = st.text_input("Dimensões (cm) (Opcional)", value=dim_atual, placeholder="Ex: 55x35x24", key="ed_dimensoes")
                
                # Nova Data de Compra
                col_ed5, col_ed6 = st.columns(2)
                
                # Tentar obter data de compra, senão hoje
                if 'data_compra' in mala_edit_selecionada and pd.notna(mala_edit_selecionada['data_compra']):
                     data_compra_atual = pd.to_datetime(mala_edit_selecionada['data_compra']).date()
                else:
                     data_compra_atual = date.today()
                     
                nova_data_compra = col_ed5.date_input("Data da Compra", value=data_compra_atual)
                
                # Gestor na Edição
                gestor_atual_id_mala = mala_edit_selecionada['gestor_id'] if 'gestor_id' in mala_edit_selecionada and pd.notna(mala_edit_selecionada['gestor_id']) else None
                idx_gestor_mala = 0
                
                lista_gestores_edit = ["Não Informado"] + list(opcoes_gestores.keys())
                
                # Reordenar para manter padrão
                if "Caixa da Empresa" in lista_gestores_edit: lista_gestores_edit.remove("Caixa da Empresa")
                if "Cartão de Crédito" in lista_gestores_edit: lista_gestores_edit.remove("Cartão de Crédito")
                lista_gestores_edit = ["Não Informado", "Caixa da Empresa", "Cartão de Crédito"] + [g for g in lista_gestores_edit if g not in ["Não Informado", "Caixa da Empresa", "Cartão de Crédito"]]
                
                if gestor_atual_id_mala:
                     for i, nome_g in enumerate(lista_gestores_edit):
                        if nome_g in opcoes_gestores and opcoes_gestores[nome_g] == gestor_atual_id_mala:
                            idx_gestor_mala = i
                            break
                            
                novo_gestor_nome_mala = col_ed6.selectbox("Gestor Responsável", lista_gestores_edit, index=idx_gestor_mala)
                novo_gestor_id_mala = opcoes_gestores[novo_gestor_nome_mala] if novo_gestor_nome_mala != "Não Informado" else None
                
                # Forma de Pagamento e Parcelas (Edição)
                col_pag_ed1, col_pag_ed2 = st.columns(2)
                
                pgto_atual = mala_edit_selecionada.get('forma_pagamento', 'Dinheiro/Pix')
                if pd.isna(pgto_atual): pgto_atual = 'Dinheiro/Pix'
                
                opcoes_pgto = ["Dinheiro/Pix", "Cartão de Crédito", "Débito"]
                idx_pgto = 0
                if pgto_atual in opcoes_pgto:
                    idx_pgto = opcoes_pgto.index(pgto_atual)
                    
                nova_forma_pagamento = col_pag_ed1.selectbox("Forma de Pagamento", opcoes_pgto, index=idx_pgto, key="ed_pgto")
                
                parcelas_atual = mala_edit_selecionada.get('parcelas', 1)
                if pd.isna(parcelas_atual): parcelas_atual = 1
                
                novas_parcelas = 1
                if nova_forma_pagamento == "Cartão de Crédito":
                    novas_parcelas = col_pag_ed2.number_input("Nº de Parcelas", min_value=1, max_value=24, value=int(parcelas_atual), step=1, key="ed_parcelas")

                nova_imagem = st.file_uploader("Atualizar Foto (Opcional)", type=["jpg", "png", "jpeg", "img", "heic", "heif"])
                
                if st.form_submit_button("Salvar Alterações"):
                    # Processar imagem se houver
                    novo_imagem_path = mala_edit_selecionada['imagem_path'] if pd.notna(mala_edit_selecionada['imagem_path']) else None
                    
                    if nova_imagem:
                         try:
                            img = Image.open(nova_imagem)
                            if img.width > 1024:
                                ratio = 1024.0 / img.width
                                new_height = int(img.height * ratio)
                                img = img.resize((1024, new_height))
                            
                            extensao = nova_imagem.name.split('.')[-1].lower()
                            if not extensao or extensao in ['heic', 'heif']:
                                extensao = "jpg"
                                
                            nome_arquivo = f"{mala_edit_selecionada['codigo']}_edit_{int(datetime.now().timestamp())}.{extensao}"
                            caminho_relativo = f"imagens_malas/{nome_arquivo}"
                            caminho_completo = os.path.join("imagens_malas", nome_arquivo)
                            
                            if img.mode != 'RGB':
                                img = img.convert('RGB')
                                
                            img.save(caminho_completo)
                            novo_imagem_path = caminho_relativo
                         except Exception as e:
                            st.error(f"Erro ao salvar imagem: {e}")
                    
                    db.update_mala(
                        int(mala_edit_selecionada['id']), 
                        novo_tamanho, 
                        nova_cor, 
                        nova_marca, 
                        novo_valor if novo_valor > 0 else None,
                        novo_imagem_path,
                        novo_gestor_id_mala,
                        data_compra=nova_data_compra,
                        forma_pagamento=nova_forma_pagamento,
                        parcelas=novas_parcelas,
                        dimensoes=nova_dimensoes
                    )
                    st.success("Mala atualizada com sucesso!")
                    st.rerun()
            
            with st.expander("📏 Atualizar Dimensões em Lote"):
                lista_malas_lote = {f"{row['codigo']} - {row['marca']} - {row['tamanho']} ({row['cor']})": int(row['id']) for _, row in malas_cadastradas.iterrows()}
                selecionadas = st.multiselect("Selecione as malas", options=list(lista_malas_lote.keys()), key="lote_dim_malas")
                dim_lote = st.text_input("Dimensões (cm)", placeholder="Ex: 55x35x24", key="lote_dim_valor")
                if st.button("Salvar Dimensões nas Selecionadas", key="btn_lote_dim"):
                    ids = [lista_malas_lote[s] for s in selecionadas]
                    ok, msg = db.update_malas_dimensoes(ids, dim_lote)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

        with tab_vender_mala:
            st.write("Selecione uma mala cadastrada para registrar como **vendida**. "
                     "A mala será marcada como 'Vendida' e sumirá do estoque disponível para aluguel.")
            st.info("💡 Dica: Use esta aba quando a mala já está cadastrada. Para mala avulsa, use a aba '🛒 Vender Mala' do menu lateral.")

            malas_vendaveis = malas_cadastradas[malas_cadastradas["status"].isin(["Disponível", "Quebrada"])]

            if malas_vendaveis.empty:
                st.warning("Nenhuma mala disponível para venda no cadastro (todas estão Alugadas, Vendidas ou Quebrada).")
            else:
                opcoes_v = malas_vendaveis.apply(
                    lambda x: f"{x['codigo']} - {x['marca']} - {x['tamanho']} ({x['cor']})", axis=1
                )
                mala_vender_str = st.selectbox(
                    "Selecione a Mala para Vender",
                    options=opcoes_v,
                    key="sel_vender_mala_cad",
                )
                row_v = malas_vendaveis[opcoes_v == mala_vender_str].iloc[0]
                custo_aquisicao_v = float(row_v.get("valor_pago") or 0)

                st.info(f"💰 Custo de aquisição (valor pago) registrado no cadastro: **R$ {custo_aquisicao_v:,.2f}**")

                # --- Bloco FORA do form: tipo + valor de venda ---
                col_v_tipo, col_v_calc = st.columns(2)
                with col_v_tipo:
                    tipo_mala_v = st.selectbox("Tipo", ["Nova", "Usada"], key="venda_cad_tipo")

                with col_v_calc:
                    st.markdown("#### 💲 Valor de venda")
                    modo_valor_v = st.radio(
                        "Como definir o valor de venda?",
                        ["Porcentagem sobre o custo", "Valor manual"],
                        horizontal=True,
                        key="venda_cad_modo_valor",
                    )
                    if modo_valor_v == "Porcentagem sobre o custo":
                        percentual_v = st.number_input(
                            "Porcentagem de lucro sobre o custo (%)",
                            min_value=0.0,
                            step=5.0,
                            value=50.0,
                            key="venda_cad_percentual",
                            help="Ex: 50% sobre o custo. Custo R$ 200 + 50% = R$ 300.",
                        )
                        valor_calculado_v = custo_aquisicao_v * (1 + percentual_v / 100.0)
                        st.success(f"📐 Cálculo: R$ {custo_aquisicao_v:,.2f} × (1 + {percentual_v:.1f}%) = **R$ {valor_calculado_v:,.2f}**")
                        st.caption("Você pode ajustar o valor final abaixo se quiser.")
                        valor_venda_v = st.number_input(
                            "Valor final de venda (R$)",
                            min_value=0.0,
                            step=10.0,
                            value=float(round(valor_calculado_v, 2)),
                            key="venda_cad_valor",
                        )
                    else:
                        valor_venda_v = st.number_input(
                            "Valor de venda (R$)",
                            min_value=0.0,
                            step=50.0,
                            value=0.0,
                            key="venda_cad_valor",
                        )

                # Lucro estimado
                if valor_venda_v > 0:
                    lucro_estimado_v = valor_venda_v - custo_aquisicao_v
                    margem_v = (lucro_estimado_v / valor_venda_v * 100) if valor_venda_v > 0 else 0
                    cor_v = "🟢" if lucro_estimado_v > 0 else ("🔴" if lucro_estimado_v < 0 else "⚪")
                    st.write(
                        f"{cor_v} **Lucro estimado:** R$ {lucro_estimado_v:,.2f}  •  **Margem:** {margem_v:.1f}%"
                    )

                st.divider()

                # --- Bloco DENTRO do form: pagamento, data, cliente, observação ---
                with st.form("form_vender_mala_cad"):
                    col_v1, col_v2 = st.columns(2)
                    with col_v1:
                        forma_pagamento_v = st.selectbox(
                            "Forma de pagamento",
                            ["Dinheiro", "PIX", "Cartão de Crédito", "Cartão de Débito", "Boleto", "Transferência", "Outro"],
                            key="venda_cad_pagamento",
                        )
                    with col_v2:
                        data_venda_v = st.date_input("Data da venda", value=datetime.now().date(), key="venda_cad_data")

                    try:
                        df_clientes_v = db.get_clientes_cached()
                    except Exception:
                        df_clientes_v = pd.DataFrame()
                    if df_clientes_v is None or df_clientes_v.empty:
                        st.warning("Sem cliente cadastrado. Use 'Cliente avulso' abaixo.")
                        cliente_id_v = None
                        cliente_nome_v = st.text_input("Nome do cliente (avulso)", key="venda_cad_cliente_nome")
                    else:
                        cliente_tipo_v = st.radio(
                            "Cliente",
                            ["Cadastrado", "Avulso"],
                            horizontal=True,
                            key="venda_cad_cliente_tipo",
                        )
                        if cliente_tipo_v == "Cadastrado":
                            opcoes_c = [f"{c['nome']} (id {c['id']})" for _, c in df_clientes_v.iterrows()]
                            sel_c = st.selectbox("Selecione o cliente", opcoes_c, key="venda_cad_cliente_sel")
                            if sel_c:
                                cid_v = int(sel_c.split("id ")[-1].rstrip(")"))
                                linha_c = df_clientes_v[df_clientes_v["id"] == cid_v]
                                if not linha_c.empty:
                                    cliente_id_v = int(linha_c.iloc[0]["id"])
                                    cliente_nome_v = str(linha_c.iloc[0]["nome"])
                                else:
                                    cliente_id_v = None
                                    cliente_nome_v = ""
                            else:
                                cliente_id_v = None
                                cliente_nome_v = ""
                        else:
                            cliente_id_v = None
                            cliente_nome_v = st.text_input("Nome do cliente (avulso)", key="venda_cad_cliente_nome_avulso")

                    observacao_v = st.text_area("Observação", height=80, key="venda_cad_obs")
                    submitted_v = st.form_submit_button("💾 Registrar Venda desta Mala", use_container_width=True)

                    if submitted_v:
                        if valor_venda_v <= 0:
                            st.error("Informe um valor de venda maior que zero.")
                        elif not cliente_nome_v or not str(cliente_nome_v).strip():
                            st.error("Informe o nome do cliente (cadastrado ou avulso).")
                        else:
                            ok_v, err_v = db.add_venda_mala(
                                mala_id=int(row_v["id"]),
                                mala_codigo=str(row_v["codigo"]),
                                mala_tamanho=str(row_v["tamanho"]),
                                cliente_id=cliente_id_v,
                                cliente_nome=str(cliente_nome_v).strip(),
                                valor_venda=float(valor_venda_v),
                                custo_aquisicao=custo_aquisicao_v,
                                tipo_mala=tipo_mala_v,
                                forma_pagamento=forma_pagamento_v,
                                observacao=str(observacao_v or "").strip(),
                                data_venda=data_venda_v.isoformat(),
                            )
                            if ok_v:
                                invalidate_cache()
                                st.success(f"✅ Mala {row_v['codigo']} marcada como Vendida para {cliente_nome_v}.")
                                st.balloons()
                                st.rerun()
                            else:
                                st.error(f"❌ Erro ao registrar venda: {err_v}")

        with tab_excluir:
            st.write("Selecione uma mala para excluir do sistema:")
            
            col_exc1, col_exc2 = st.columns([2, 1])
            
            with col_exc1:
                # Reutilizando a lista, mas com nova key
                mala_excluir_str = st.selectbox("Selecione a Mala para Excluir", options=opcoes_mala, key="sel_excluir_tab")
            
            # Obter ID e Imagem para confirmação
            mala_selecionada = malas_cadastradas[opcoes_mala == mala_excluir_str].iloc[0]
            id_excluir = mala_selecionada['id']
            
            with col_exc2:
                if 'imagem_path' in mala_selecionada and mala_selecionada['imagem_path']:
                    try:
                        st.image(mala_selecionada['imagem_path'], caption="Mala Selecionada", width=150)
                    except:
                        st.warning("Imagem não encontrada")
                
                st.write("") # Espaçamento
                if st.button("🗑️ Confirmar Exclusão", type="primary"):
                    sucesso, msg = db.delete_mala(int(id_excluir))
                    if sucesso:
                        # Tentar remover arquivo de imagem se existir
                        if 'imagem_path' in mala_selecionada and mala_selecionada['imagem_path']:
                            try:
                                if os.path.exists(mala_selecionada['imagem_path']):
                                    os.remove(mala_selecionada['imagem_path'])
                            except:
                                pass
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
    else:
        st.info("Nenhuma mala cadastrada para gerenciar.")

    st.divider()
    st.subheader("Estoque de Malas")
    
    # Campo de Busca para o Estoque
    busca_mala = st.text_input("🔍 Buscar Mala no Estoque (Ex: 'P Cinza' ou 'M001')", placeholder="Digite cor, tamanho ou código...")
    
    # --- NOVO: Filtro de Disponibilidade por Data ---
    with st.expander("📅 Consultar Disponibilidade por Período (Novo)", expanded=False):
        col_disp1, col_disp2, col_disp3 = st.columns([2, 2, 1])
        dt_inicio_disp = col_disp1.date_input("Data Início", value=date.today(), key="dt_ini_disp")
        dt_fim_disp = col_disp2.date_input("Data Fim", value=date.today() + timedelta(days=7), key="dt_fim_disp")
        
        if col_disp3.button("Verificar Disponibilidade", type="primary"):
            st.markdown("### 📊 Resultado da Consulta")
            
            # Buscar dados
            df_disp = db.get_disponibilidade_periodo(dt_inicio_disp, dt_fim_disp)
            
            if not df_disp.empty:
                # Métricas por Tamanho
                st.markdown("#### Malas por Tamanho:")
                resumo_tamanho = df_disp.groupby('tamanho')['status_periodo'].value_counts().unstack(fill_value=0)
                
                # Garantir colunas Livre e Ocupada
                if 'Livre' not in resumo_tamanho.columns: resumo_tamanho['Livre'] = 0
                if 'Ocupada' not in resumo_tamanho.columns: resumo_tamanho['Ocupada'] = 0
                
                # Exibir Cards
                cols_tam = st.columns(len(resumo_tamanho))
                for i, (tamanho, row) in enumerate(resumo_tamanho.iterrows()):
                    with cols_tam[i]:
                        st.metric(f"Tamanho {tamanho}", f"{row['Livre']} Livres", f"{row['Ocupada']} Ocupadas", delta_color="normal")
                
                st.divider()
                
                # Lista de Malas Livres Detalhada
                col_livres, col_ocupadas = st.columns(2)
                
                with col_livres:
                    st.markdown("#### ✅ Malas Livres")
                    malas_livres = df_disp[df_disp['status_periodo'] == 'Livre']
                    
                    if not malas_livres.empty:
                        # Agrupar por tamanho para facilitar leitura
                        for tamanho in sorted(malas_livres['tamanho'].unique()):
                            st.write(f"**Tamanho {tamanho}:**")
                            itens = malas_livres[malas_livres['tamanho'] == tamanho]
                            # Mostrar como tags
                            tags = [f"{row['codigo']} ({row['cor']})" for _, row in itens.iterrows()]
                            st.info(", ".join(tags))
                    else:
                        st.error("Nenhuma mala livre para este período!")

                with col_ocupadas:
                    st.markdown("#### ❌ Malas Ocupadas")
                    # Filtrar apenas as ocupadas
                    malas_ocupadas = df_disp[df_disp['status_periodo'] == 'Ocupada'].copy()
                    
                    if not malas_ocupadas.empty:
                         # Agrupar por tamanho
                         for tamanho in sorted(malas_ocupadas['tamanho'].unique()):
                             st.write(f"**Tamanho {tamanho}:**")
                             itens_oc = malas_ocupadas[malas_ocupadas['tamanho'] == tamanho]
                             
                             for _, row in itens_oc.iterrows():
                                 # Formatar datas se existirem
                                 datas_str = ""
                                 if pd.notna(row.get('data_saida')) and pd.notna(row.get('data_prevista_retorno')):
                                     d1 = pd.to_datetime(row['data_saida']).strftime('%d/%m')
                                     d2 = pd.to_datetime(row['data_prevista_retorno']).strftime('%d/%m')
                                     datas_str = f"({d1} a {d2})"
                                     
                                 cliente_str = f"- {row['cliente_nome']}" if pd.notna(row.get('cliente_nome')) else ""
                                 
                                 st.error(f"**{row['codigo']}** {row['cor']} {datas_str} {cliente_str}")
                    else:
                        st.success("Nenhuma mala ocupada neste período!")
                
                st.divider()
                
                # Acessórios (Estimativa baseada em reservas)
                st.markdown("#### 👜 Acessórios Agendados (Uso Estimado):")
                lista_acessorios = db.get_acessorios_periodo(dt_inicio_disp, dt_fim_disp)
                if lista_acessorios:
                    # Contar frequência
                    from collections import Counter
                    contagem = Counter(lista_acessorios)
                    
                    # Exibir
                    texto_acessorios = ""
                    for item, qtd in contagem.items():
                        texto_acessorios += f"- **{qtd}x** {item}\n"
                    st.warning(f"Neste período, os seguintes itens já estão reservados em outros contratos:\n\n{texto_acessorios}\n\n*Verifique se há estoque físico suficiente.*")
                else:
                    st.success("Nenhum acessório reservado especificamente para este período (Estoque Total Disponível).")
                    
            else:
                st.warning("Nenhuma mala cadastrada no sistema.")
    
    df_malas = db.get_malas()
    
    # Reordenar e renomear colunas para exibição
    if not df_malas.empty:
        # Filtrar se houver busca
        if busca_mala:
            busca_mala = busca_mala.lower()
            # Criar coluna combinada para busca
            df_malas['busca_str'] = df_malas.apply(lambda x: f"{x['codigo']} {x['tamanho']} {x['cor']} {x['marca']}".lower(), axis=1)
            # Filtrar
            df_malas = df_malas[df_malas['busca_str'].str.contains(busca_mala)]
            
            if df_malas.empty:
                st.warning("Nenhuma mala encontrada com esses termos.")
            else:
                st.info(f"Encontradas {len(df_malas)} malas.")
        
        # Preparar DataFrame para exibição com imagens
        colunas_exibicao = ['codigo', 'tamanho', 'dimensoes', 'cor', 'marca', 'status', 'valor_pago']
        
        # Verificar se a coluna imagem_path existe no DataFrame (para compatibilidade com BD antigo antes da migração)
        if 'imagem_path' in df_malas.columns:
            colunas_exibicao.append('imagem_path')
            
        df_exibicao = df_malas[colunas_exibicao].copy()
        df_exibicao.rename(columns={'valor_pago': 'Custo Aquisição (R$)', 'imagem_path': 'Foto'}, inplace=True)
        
        # Configurar coluna de imagem
        st.dataframe(
            df_exibicao,
            column_config={
                "Foto": st.column_config.ImageColumn(
                    "Foto", help="Foto da Mala"
                ),
                "Custo Aquisição (R$)": st.column_config.NumberColumn(
                    "Custo Aquisição (R$)", format="R$ %.2f"
                )
            },
            use_container_width=True
        )
    else:
        st.info("Nenhuma mala cadastrada.")

# --- CADASTRAR CLIENTE ---
elif st.session_state.page == "Cadastrar Cliente":
    st.subheader("Cadastrar Novo Cliente")
    
    with st.form("form_cliente"):
        # Usar key dinâmica para resetar formulário
        key_suffix = st.session_state.form_cliente_key
        
        nome = st.text_input("Nome Completo", key=f"cli_nome_{key_suffix}")
        
        col1, col2 = st.columns(2)
        documento = col1.text_input("Documento (CPF)", key=f"cli_documento_{key_suffix}")
        cep = col2.text_input("CEP", key=f"cli_cep_{key_suffix}")
        
        col_tel, col_cid = st.columns([1, 1])
        telefone = col_tel.text_input("Celular/WhatsApp", key=f"cli_tel_{key_suffix}")
        cidade = col_cid.text_input("Cidade/UF", value="Votorantim/SP", key=f"cli_cid_{key_suffix}")
        
        endereco = st.text_input("Endereço Completo (Rua, Nº, Bairro)", key=f"cli_end_{key_suffix}")
        
        submit = st.form_submit_button("Cadastrar")
        
        if submit:
            if nome:
                cliente_existente = db.buscar_cliente_por_documento(documento)
                if cliente_existente:
                    st.error(f"⚠️ Cliente já cadastrado: **{cliente_existente['nome']}** (Telefone: {cliente_existente['telefone']})")
                    col_del, col_info = st.columns([1, 2])
                    with col_del:
                        confirmar_excluir = st.checkbox(f"Excluir cliente ID {cliente_existente['id']}", value=False, key=f"chk_del_cli_{cliente_existente['id']}")
                        if confirmar_excluir:
                            if st.button(f"⚠️ Confirmar Exclusão de {cliente_existente['nome']}", key=f"btn_del_cli_{cliente_existente['id']}"):
                                db.delete_cliente(cliente_existente['id'])
                                st.success(f"Cliente {cliente_existente['nome']} excluído!")
                                st.rerun()
                    with col_info:
                        st.info("Caso contrário, apenas mude o documento do novo cliente.")
                else:
                    sucesso, erro_add = db.add_cliente(nome, documento, cep, endereco, cidade, telefone)
                    if sucesso:
                        invalidate_cache()
                        st.success(f"Cliente {nome} cadastrado com sucesso!")
                        st.session_state.form_cliente_key += 1
                        st.rerun()
                    else:
                        st.error(f"❌ Não foi possível cadastrar: {erro_add}")
            else:
                st.warning("Nome é obrigatório.")
                
    st.divider()
    st.subheader("Clientes Cadastrados e Gerenciamento")
    
    df_clientes = get_clientes_cached()
    
    if not df_clientes.empty:
        # Criar tabs
        tab_lista, tab_editar = st.tabs(["📋 Lista de Clientes", "✏️ Editar Cliente"])
        
        with tab_lista:
            st.dataframe(df_clientes, use_container_width=True)
            
        with tab_editar:
            opcoes_cliente = df_clientes.apply(lambda x: f"{x['nome']} (ID: {x['id']})", axis=1)
            cliente_editar_str = st.selectbox("Selecione o Cliente para Editar", options=opcoes_cliente, key="sel_editar_cliente")
            
            # Recuperar dados
            cliente_selecionado = df_clientes[opcoes_cliente == cliente_editar_str].iloc[0]
            
            with st.form("form_editar_cliente"):
                novo_nome = st.text_input("Nome Completo", value=cliente_selecionado['nome'])
                col_ed1, col_ed2 = st.columns(2)
                # Tratar campos que podem ser None/NaN
                doc_atual = cliente_selecionado['documento'] if pd.notna(cliente_selecionado['documento']) else ""
                cep_atual = cliente_selecionado['cep'] if 'cep' in cliente_selecionado and pd.notna(cliente_selecionado['cep']) else ""
                tel_atual = cliente_selecionado['telefone'] if 'telefone' in cliente_selecionado and pd.notna(cliente_selecionado['telefone']) else ""
                end_atual = cliente_selecionado['endereco'] if 'endereco' in cliente_selecionado and pd.notna(cliente_selecionado['endereco']) else ""
                cid_atual = cliente_selecionado['cidade'] if 'cidade' in cliente_selecionado and pd.notna(cliente_selecionado['cidade']) else ""
                
                novo_documento = col_ed1.text_input("Documento (CPF)", value=doc_atual)
                novo_cep = col_ed2.text_input("CEP", value=cep_atual)
                
                col_ed3, col_ed4 = st.columns([1, 1])
                novo_telefone = col_ed3.text_input("Celular/WhatsApp", value=tel_atual)
                nova_cidade = col_ed4.text_input("Cidade/UF", value=cid_atual)
                
                novo_endereco = st.text_input("Endereço Completo", value=end_atual)
                
                if st.form_submit_button("Salvar Alterações"):
                    db.update_cliente(int(cliente_selecionado['id']), novo_nome, novo_documento, novo_cep, novo_endereco, nova_cidade, novo_telefone)
                    st.success("Cliente atualizado com sucesso!")
                    st.rerun()
    else:
        st.info("Nenhum cliente cadastrado.")

# --- NOVO ALUGUEL ---
elif st.session_state.page == "Novo Aluguel":
    st.subheader("Registrar Novo Aluguel")
    
    with st.expander("Passo 1: Selecionar Período da Viagem", expanded=True):
        col_data1, col_data2 = st.columns(2)
        data_viagem_inicio = col_data1.date_input("Início da Viagem", date.today() + timedelta(days=1))
        data_viagem_fim = col_data2.date_input("Fim da Viagem", date.today() + timedelta(days=2))
        
        if data_viagem_inicio > data_viagem_fim:
            st.error("Data de início não pode ser maior que a data de fim da viagem.")
            st.stop()
            
        # Calcular datas efetivas de bloqueio (Retirada -1 dia, Devolução +1 dia)
        data_retirada = data_viagem_inicio - timedelta(days=1)
        data_devolucao = data_viagem_fim + timedelta(days=1)
        
        # Calcular dias de viagem
        dias_viagem = (data_viagem_fim - data_viagem_inicio).days + 1
        dias_bloqueio = (data_devolucao - data_retirada).days + 1
        
        st.info(f"""
        **Resumo do Período:**
        - **Duração da Viagem:** {dias_viagem} dias
        - **Dias de Bloqueio da Mala:** {dias_bloqueio} dias (inclui retirada e devolução)
        
        **Cronograma:**
        - **Retirada (1 dia antes):** {data_retirada.strftime('%d/%m/%Y')}
        - **Devolução (1 dia depois):** {data_devolucao.strftime('%d/%m/%Y')}
        """)
            
    # Buscar malas disponíveis para o período efetivo de bloqueio
    malas_disponiveis = db.get_malas_disponiveis_por_data(data_retirada, data_devolucao)
    
    st.info(f"Malas disponíveis para o período de bloqueio ({data_retirada.strftime('%d/%m/%Y')} a {data_devolucao.strftime('%d/%m/%Y')}): {len(malas_disponiveis)}")
    
    clientes = get_clientes_cached()
    
    # Se houver mala pré-selecionada, verificar se ela está disponível, mesmo que não esteja na lista inicial (caso já esteja ocupada em outra data, mas não nesta)
    # A função get_malas_disponiveis já filtra por data. Se a mala pré-selecionada não vier, é porque está ocupada NESTA data.
    
    if clientes.empty:
        st.warning("Cadastre clientes antes de realizar um aluguel.")
    else:
        # Colocando os dicionários e selects FORA do form para permitir interatividade (atualizar imagem)
        col1, col2 = st.columns(2)
        
        dict_malas = {f"{row['codigo']} - {row['marca']} - {row['tamanho']} ({row['cor']})": row['id'] for index, row in malas_disponiveis.iterrows()}
        dict_clientes = {f"{row['nome']} - {row['telefone']}": row['id'] for index, row in clientes.iterrows()}
        
        # Verificar se há uma mala pré-selecionada (vinda do Dashboard)
        preselected_index = 0
        mala_pre_selecionada_indisponivel = False
        
        if st.session_state.preselected_mala_id:
            # Encontrar o índice da mala pré-selecionada na lista de disponíveis
            if st.session_state.preselected_mala_id in malas_disponiveis['id'].values:
                # Encontrar a chave correspondente no dict_malas
                for i, (key, value) in enumerate(dict_malas.items()):
                    if value == st.session_state.preselected_mala_id:
                        preselected_index = i
                        break
            else:
                # A mala foi pré-selecionada mas NÃO está disponível para as datas
                mala_pre_selecionada_indisponivel = True
                
        if malas_disponiveis.empty and not mala_pre_selecionada_indisponivel:
             st.warning("Não há malas disponíveis para este período.")
        elif mala_pre_selecionada_indisponivel:
             st.error("⚠️ A mala selecionada no Dashboard **NÃO está disponível** para as datas escolhidas. Por favor, escolha outra data ou outra mala.")
             # Opção para limpar seleção
             if st.button("Limpar Seleção"):
                 st.session_state.preselected_mala_id = None
                 st.rerun()
        else:
            mala_selecionada_str = col1.selectbox("Selecione a Mala", list(dict_malas.keys()), index=preselected_index)
            cliente_selecionado_str = col2.selectbox("Selecione o Cliente", list(dict_clientes.keys()))
            
            mala_id = dict_malas[mala_selecionada_str]
            cliente_id = dict_clientes[cliente_selecionado_str]

            # Buscar CEP do cliente para calcular frete
            cliente_info_df = clientes[clientes['id'] == cliente_id]
            cliente_cep = ""
            if not cliente_info_df.empty and 'cep' in cliente_info_df.columns:
                cliente_cep = cliente_info_df.iloc[0].get('cep', '') or ''

            # Função para calcular frete (com cache)
            @st.cache_data(ttl=3600, show_spinner=False)
            def calcular_frete_cep_cached(cep_destino):
                if not cep_destino or cep_destino.strip() == '':
                    return 0.0
                cep_origem = "18117-706"
                lat_origem, lon_origem = -23.5447, -47.4389
                lat_dest, lon_dest = get_coordinates_from_cep(cep_destino)
                if lat_dest and lon_dest:
                    dist_linear = haversine(lat_origem, lon_origem, lat_dest, lon_dest)
                    fator_rota = 1.3
                    dist_total = dist_linear * fator_rota * 4
                    valor_km = db.get_config('valor_km_padrao', 1.00)
                    return dist_total * float(valor_km)
                return 0.0

            # Calcular frete automaticamente (apenas se cliente ainda não tiver frete)
            # Verificar se cliente já tem frete calculado
            cliente_ja_tem_frete = db.cliente_tem_frete_calculado(cliente_id)
            
            if cliente_ja_tem_frete:
                # Cliente já pagou frete, não cobrar novamente
                frete_calculado = 0.0
                st.info("🚚 **Frete:** Cliente já possui frete calculado em outro aluguel (não cobrado novamente).")
            else:
                # Cliente novo ou sem frete, calcular
                if cliente_cep and cliente_cep.strip():
                    frete_calculado = calcular_frete_cep_cached(cliente_cep)
                else:
                    frete_calculado = 0.0
            
            # Mostrar imagem da mala selecionada
            mala_info = malas_disponiveis[malas_disponiveis['id'] == mala_id].iloc[0]
            if 'imagem_path' in mala_info and mala_info['imagem_path']:
                st.image(mala_info['imagem_path'], caption=f"Foto da Mala {mala_info['codigo']}", width=300)
                
            with st.form("form_aluguel"):
                # Campo de Destino (Novo) e Acessórios
                col_extra1, col_extra2 = st.columns(2)
                destino = col_extra1.text_input("Destino da Viagem (Cidade/Estado)", placeholder="Ex: Rio de Janeiro, RJ")
                acessorios = col_extra2.text_input("Acessórios Adicionais", placeholder="Ex: Cadeado, Capa, Tag...")

                # Mostrar Frete Calculado (referência, não é cobrado)
                # Buscar valor do km padrão (R$ 0,70)
                valor_km_frete = float(db.get_config('valor_km_padrao', 0.70))
                
                if cliente_ja_tem_frete:
                    # Não mostrar nada, já informamos acima
                    pass
                elif cliente_cep and cliente_cep.strip():
                    st.info(f"🚚 **Frete Calculado (referência):** R$ {frete_calculado:,.2f} (baseado no CEP {cliente_cep} do cliente)")
                else:
                    st.warning("🚚 **Cliente sem CEP cadastrado.** Digite a distância estimada para calcular o frete.")
                    # Permitir que o usuário digite a distância estimada
                    distancia_estimada = st.number_input(
                        "📍 Distância estimada de IDA (km)", 
                        min_value=0.0, 
                        step=10.0, 
                        value=0.0,
                        help="Distância em quilômetros de ida. O cálculo considera ida e volta (4 viagens)."
                    )
                    if distancia_estimada > 0:
                        # 4 viagens: Ida para levar + Volta + Ida para buscar + Volta
                        dist_total_frete = distancia_estimada * 4
                        frete_calculado = dist_total_frete * valor_km_frete
                        st.success(f"🚚 **Frete Estimado:** R$ {frete_calculado:,.2f} ({dist_total_frete:.0f} km x R$ {valor_km_frete:.2f}/km)")
                
                col_val1, col_val2, col_val3, col_val4 = st.columns(4)
                valor = col_val1.number_input("Valor do Aluguel (R$)", min_value=0.0, step=10.0)
                taxa_entrega = col_val2.number_input("Taxa de Entrega (R$)", min_value=0.0, step=5.0, help="Valor cobrado para levar/buscar a mala.")
                valor_acessorios = col_val3.number_input("Valor Acessórios (R$)", min_value=0.0, step=5.0)
                valor_sinal = col_val4.number_input("Valor Sinal/Reserva (R$)", min_value=0.0, step=10.0, help="Valor pago adiantado.")
                
                total_geral = valor + taxa_entrega + valor_acessorios
                st.markdown(f"**💰 Total a Pagar:** R$ {total_geral:.2f}")

                observacao = st.text_area("📝 Observação / Lembrete", placeholder="Ex: Cliente pediu para lembra-lo sobre...")
                
                col_pag1, col_pag2 = st.columns(2)
                pago = col_pag1.checkbox("Pagamento TOTAL já realizado?", value=False, help="Marque apenas se o cliente pagou TUDO (Aluguel + Taxa).")
                is_permuta = col_pag2.checkbox("🤝 É Parceria/Permuta?", value=False, help="Marque se for troca de serviços (ex: Influencer). O valor não entrará no caixa.")
                
                submit = st.form_submit_button("Confirmar Aluguel")
                
            if submit:
                # Definir status de pagamento
                status_custom = None
                if is_permuta:
                    status_custom = "Permuta"
                    # Se for permuta, consideramos que não houve pagamento em dinheiro (pago=False para lógica de caixa, mas status define)
                
                # Mensagem de confirmação antes de salvar (simulada com st.warning, pois st.form não suporta modal direto)
                # Mas como st.form_submit_button já envia, vamos fazer a validação e mostrar o sucesso com detalhes
                
                st.info(f"📝 **Resumo do Pedido:**\n"
                        f"- Cliente: {cliente_selecionado_str.split(' - ')[0]}\n"
                        f"- Mala: {mala_selecionada_str}\n"
                        f"- Destino: {destino}\n"
                        f"- Acessórios: {acessorios if acessorios else 'Nenhum'} (R$ {valor_acessorios:.2f})\n"
                        f"- Período: {data_retirada.strftime('%d/%m')} até {data_devolucao.strftime('%d/%m')}\n"
                        f"- Total: R$ {total_geral:.2f}\n"
                        f"- Tipo: {'Permuta/Parceria' if is_permuta else 'Aluguel Normal'}")
                        
                # Salvar as datas efetivas de bloqueio (Retirada e Devolução)
                sucesso, msg = db.criar_aluguel(int(mala_id), int(cliente_id), data_retirada, data_devolucao, valor, pago, valor_sinal, taxa_entrega, status_pagamento_custom=status_custom, destino=destino, acessorios=acessorios, valor_acessorios=valor_acessorios, observacao=observacao if observacao else None, frete_calculado=frete_calculado)
                
                if sucesso:
                    msg_sinal = f" (Sinal de R$ {valor_sinal:.2f} recebido)" if valor_sinal > 0 else ""
                    st.success(f"✅ **Aluguel Confirmado!** Mala bloqueada de {data_retirada.strftime('%d/%m/%Y')} até {data_devolucao.strftime('%d/%m/%Y')}{msg_sinal}.")
                    
                    # Limpar pré-seleção após aluguel
                    st.session_state.preselected_mala_id = None
                    
                    # Botão para atualizar a página e limpar o formulário
                    st.button("🆕 Fazer Novo Aluguel", on_click=st.rerun)
                else:
                    st.error(msg)



# --- DEVOLUÇÕES E GERENCIAMENTO DE ALUGUÉIS --- (Revertido para versão estável)
elif st.session_state.page == "Devoluções":
    st.subheader("Gerenciar Aluguéis Ativos e Devoluções")
    
    alugueis_ativos = db.get_alugueis_ativos()
    
    if alugueis_ativos.empty:
        st.info("Não há aluguéis ativos no momento.")
    else:
        with st.expander("📦 Consultar Malas a Entregar por Data", expanded=False):
            data_consulta = st.date_input("Data da Entrega/Retirada", value=date.today(), key="dt_consulta_entrega")
            df_consulta = alugueis_ativos.copy()
            df_consulta['data_saida_dt'] = pd.to_datetime(df_consulta['data_saida']).dt.date
            df_do_dia = df_consulta[df_consulta['data_saida_dt'] == data_consulta].copy()
            
            if df_do_dia.empty:
                st.info("Nenhuma mala para entregar nessa data.")
            else:
                st.write(f"Encontradas {len(df_do_dia)} entregas/retiradas nessa data.")
                st.dataframe(
                    df_do_dia[
                        [
                            'mala_codigo',
                            'mala_dimensoes',
                            'cliente_nome',
                            'cliente_telefone',
                            'cliente_endereco',
                            'cliente_cidade',
                            'cliente_cep',
                            'data_saida',
                            'data_prevista_retorno',
                            'status_pagamento',
                        ]
                    ],
                    column_config={
                        "mala_codigo": "Mala",
                        "mala_dimensoes": "Medidas",
                        "cliente_nome": "Cliente",
                        "cliente_telefone": "Telefone",
                        "cliente_endereco": "Endereço",
                        "cliente_cidade": "Cidade",
                        "cliente_cep": "CEP",
                        "data_saida": "Entrega/Retirada",
                        "data_prevista_retorno": "Fim Contrato",
                        "status_pagamento": "Pagamento",
                    },
                    use_container_width=True,
                )

        # Filtro de Busca (Nome do Cliente ou Código da Mala)
        termo_busca = st.text_input("🔍 Buscar Aluguel (Nome Cliente ou Código Mala)", placeholder="Digite para filtrar...")
        
        if termo_busca:
            termo_busca = termo_busca.lower()
            mask_busca = (
                alugueis_ativos['cliente_nome'].str.lower().str.contains(termo_busca) |
                alugueis_ativos['mala_codigo'].str.lower().str.contains(termo_busca)
            )
            alugueis_ativos = alugueis_ativos[mask_busca]
            
        if alugueis_ativos.empty and termo_busca:
            st.warning("Nenhum aluguel encontrado com esse termo.")
        elif not alugueis_ativos.empty:
            st.write(f"Exibindo {len(alugueis_ativos)} aluguéis encontrados.")
            
            # Ordenar por Data de Saída (as primeiras a sair aparecem primeiro)
            # Em caso de empate na data, ordena por nome do cliente
            alugueis_ativos = alugueis_ativos.sort_values(by=['data_saida', 'cliente_nome'])
            
            # Iterar sobre os aluguéis e mostrar cards
        num_columns = 3
        chunks = [alugueis_ativos.iloc[i:i + num_columns] for i in range(0, len(alugueis_ativos), num_columns)]
        
        for chunk in chunks:
            cols = st.columns(num_columns)
            for i, (_, row) in enumerate(chunk.iterrows()):
                with cols[i]:
                    with st.container(border=True):
                        # Cabeçalho do Card
                        st.markdown(f"#### {row['mala_codigo']} ({row['tamanho']}) - {row['marca']}")
                        
                        # Imagem
                        if row['imagem_path'] and os.path.exists(row['imagem_path']):
                            st.image(row['imagem_path'], use_container_width=True)
                        else:
                            st.image("https://via.placeholder.com/300x200?text=Sem+Foto", use_container_width=True)
                        
                        st.markdown(f"**Cliente:** {row['cliente_nome']}")
                        
                        # Mostrar Acessórios se houver
                        if 'acessorios' in row and pd.notna(row['acessorios']) and row['acessorios']:
                            st.info(f"👜 **Acessórios:** {row['acessorios']}")
                        
                        # Calcular datas
                        dt_saida = pd.to_datetime(row['data_saida']).date()
                        dt_prevista = pd.to_datetime(row['data_prevista_retorno']).date()
                        # Data sugerida de devolução é 1 dia APÓS o fim do contrato (dia seguinte)
                        dt_sugerida_devolucao = dt_prevista + timedelta(days=1)
                        
                        st.text(f"Saída: {dt_saida.strftime('%d/%m/%Y')}")
                        st.text(f"Fim Contrato: {dt_prevista.strftime('%d/%m/%Y')}")
                        st.markdown(f"**Devolução Ideal:** {dt_sugerida_devolucao.strftime('%d/%m/%Y')}")
                        
                        # Lembrete de Retirada/Devolução no Dashboard (Lógica visual)
                        # Se hoje é dia de retirada ou devolução, destacar
                        hoje = date.today()
                        if dt_saida == hoje:
                            st.error("🚨 **HOJE:** Cliente retira a mala!")
                        elif dt_prevista == hoje:
                            st.warning("⚠️ **HOJE:** Fim do contrato (Devolução Prevista)")
                        elif dt_sugerida_devolucao == hoje:
                            st.info("ℹ️ **HOJE:** Data sugerida para devolução física.")
                        elif hoje > dt_sugerida_devolucao:
                             st.error(f"🔴 **ATRASADO:** {abs((hoje - dt_sugerida_devolucao).days)} dias de atraso!")
                        
                        # Valor Editável e Status de Pagamento
                        valor_atual = float(row['valor']) if pd.notna(row['valor']) else 0.0
                        valor_sinal_atual = float(row['valor_sinal']) if 'valor_sinal' in row and pd.notna(row['valor_sinal']) else 0.0
                        taxa_entrega_atual = float(row['taxa_entrega']) if 'taxa_entrega' in row and pd.notna(row['taxa_entrega']) else 0.0
                        valor_acessorios_atual = float(row['valor_acessorios']) if 'valor_acessorios' in row and pd.notna(row['valor_acessorios']) else 0.0
                        status_pagto = row['status_pagamento'] if 'status_pagamento' in row else 'Pendente'
                        
                        # Calcular Restante
                        total_com_taxa = valor_atual + taxa_entrega_atual + valor_acessorios_atual
                        valor_restante = total_com_taxa - valor_sinal_atual
                        if status_pagto == 'Pago':
                            valor_restante = 0.0
                        
                        # Usar um expander para edição para não poluir o card
                        # Título dinâmico
                        titulo_expander = f"💰 Total: R$ {total_com_taxa:.2f}"
                        if status_pagto == 'Permuta':
                            titulo_expander += " (🤝 Permuta)"
                        elif status_pagto == 'Pendente' and valor_sinal_atual > 0:
                            titulo_expander += f" (Falta: R$ {valor_restante:.2f})"
                        elif status_pagto == 'Pago':
                            titulo_expander += " (Pago ✅)"
                        
                        with st.expander(titulo_expander):
                            # Campo Destino Editável
                            novo_destino = st.text_input("Destino", value=row.get('destino', '') or '', key=f"dest_{row['id']}")
                            
                            col_edit_1, col_edit_2, col_edit_3, col_edit_4 = st.columns(4)
                            novo_valor = col_edit_1.number_input(f"Valor Aluguel", min_value=0.0, step=10.0, value=valor_atual, key=f"val_{row['id']}")
                            nova_taxa = col_edit_2.number_input(f"Taxa Entrega", min_value=0.0, step=5.0, value=taxa_entrega_atual, key=f"taxa_{row['id']}")
                            novo_valor_acessorios = col_edit_3.number_input(f"Valor Acessórios", min_value=0.0, step=5.0, value=valor_acessorios_atual, key=f"acess_{row['id']}")
                            novo_sinal = col_edit_4.number_input(f"Sinal Pago", min_value=0.0, step=10.0, value=valor_sinal_atual, key=f"sinal_{row['id']}")
                            
                            if st.button("Salvar Valores/Destino", key=f"btn_save_{row['id']}"):
                                db.update_aluguel_valor(row['id'], novo_valor, novo_sinal, nova_taxa, novo_valor_acessorios, novo_destino)
                                st.success("Atualizado com sucesso!")
                                st.rerun()
                            
                            st.divider()
                            st.write(f"**Aluguel:** R$ {novo_valor:.2f} + **Entrega:** R$ {nova_taxa:.2f} + **Acessórios:** R$ {novo_valor_acessorios:.2f}")
                            st.write(f"**Total Geral:** R$ {(novo_valor + nova_taxa + novo_valor_acessorios):.2f}")
                            st.write(f"**Sinal Pago:** R$ {novo_sinal:.2f}")
                            
                            if status_pagto != 'Pago' and status_pagto != 'Permuta':
                                st.write(f"**Restante a Pagar:** R$ {(novo_valor + nova_taxa + novo_valor_acessorios - novo_sinal):.2f}")
                            
                            st.write("---")
                            st.write("Status do Pagamento:")
                            
                            if status_pagto == 'Permuta':
                                st.info("🤝 **Permuta/Parceria**")
                                if st.button("Mudar para Pendente", key=f"btn_pend_perm_{row['id']}"):
                                    db.update_aluguel_pagamento(row['id'], 'Pendente')
                                    st.rerun()
                            elif status_pagto == 'Pago':
                                st.success("✅ Pago Totalmente")
                                if st.button("Marcar como Pendente", key=f"btn_pend_{row['id']}"):
                                    db.update_aluguel_pagamento(row['id'], 'Pendente')
                                    st.rerun()
                            else:
                                st.warning("⏳ Pendente")
                                col_act1, col_act2 = st.columns(2)
                                if col_act1.button("Marcar Pago", key=f"btn_pago_{row['id']}"):
                                    db.update_aluguel_pagamento(row['id'], 'Pago')
                                    st.rerun()
                                if col_act2.button("Marcar Permuta", key=f"btn_perm_{row['id']}"):
                                    db.update_aluguel_pagamento(row['id'], 'Permuta')
                                    st.rerun()
                    
                    with st.expander("💥 Quebra da Mala (Cliente)"):
                        valor_avaria = st.number_input("Valor cobrado pela quebra (R$)", min_value=0.0, step=10.0, value=0.0, key=f"av_val_{row['id']}")
                        obs_avaria = st.text_input("Observação (Opcional)", value="", key=f"av_obs_{row['id']}")
                        confirmar_quebra = st.checkbox("Confirmo que a mala será retirada do sistema", value=False, key=f"av_conf_{row['id']}")

                        if st.button("Registrar Quebra e Retirar Mala", key=f"btn_quebra_{row['id']}", type="secondary", disabled=not confirmar_quebra):
                            mala_id_atual = int(row['mala_id']) if 'mala_id' in row and pd.notna(row['mala_id']) else None
                            if mala_id_atual is None:
                                df_tmp = db.get_malas()
                                sel = df_tmp[df_tmp['codigo'] == row['mala_codigo']]
                                if not sel.empty:
                                    mala_id_atual = int(sel.iloc[0]['id'])

                            if mala_id_atual is None:
                                st.error("Não foi possível identificar o ID da mala.")
                            else:
                                ok_fin, msg_fin = db.finalizar_aluguel(int(row['id']), date.today())
                                if not ok_fin:
                                    st.error(msg_fin)
                                    st.stop()

                                if valor_avaria > 0:
                                    ok_av, msg_av = db.add_avaria(int(row['id']), float(valor_avaria), obs_avaria if obs_avaria else None)
                                    if not ok_av:
                                        st.error(msg_av)
                                        st.stop()

                                ok_m, msg_m = db.marcar_mala_quebrada(mala_id_atual)
                                if not ok_m:
                                    st.error(msg_m)
                                    st.stop()

                                st.session_state['ultima_mala_quebrada'] = row['mala_codigo']
                                ok_t, msg_t, resultados = db.auto_trocar_alugueis_futuros_mala_quebrada(mala_id_atual, date.today())
                                if ok_t and resultados:
                                    ok_cnt = len([r for r in resultados if r.get('status') == 'ok'])
                                    fal_cnt = len([r for r in resultados if r.get('status') != 'ok'])
                                    st.success(f"Mala {row['mala_codigo']} marcada como quebrada e retirada do sistema. Trocas futuras: {ok_cnt} ok, {fal_cnt} com falha.")
                                    with st.expander("Ver detalhes das trocas futuras"):
                                        for r in resultados:
                                            if r.get('status') == 'ok':
                                                st.write(f"Aluguel {r.get('aluguel_id')}: trocado para mala ID {r.get('nova_mala_id')}")
                                            else:
                                                st.write(f"Aluguel {r.get('aluguel_id')}: {r.get('motivo')}")
                                elif ok_t:
                                    st.success(f"Mala {row['mala_codigo']} marcada como quebrada e retirada do sistema. Nenhum aluguel futuro para trocar.")
                                else:
                                    st.warning(msg_t)

                                st.rerun()

                    with st.expander("📅 Prorrogar / Estender Aluguel"):
                        st.write(f"**Data atual de retorno:** {dt_prevista.strftime('%d/%m/%Y')}")
                        st.write(f"**Valor atual:** R$ {valor_atual:.2f}")
                        nova_data = st.date_input("Nova data de retorno", value=dt_prevista + timedelta(days=3), key=f"prorrog_data_{row['id']}")
                        valor_adicional = st.number_input("Valor adicional a adicionar (R$)", min_value=0.0, step=10.0, value=0.0, key=f"prorrog_val_{row['id']}")
                        obs_prorrog = st.text_input("Motivo da prorrogação (opcional)", key=f"prorrog_obs_{row['id']}", placeholder="Ex: Cliente decidiu ficar mais 3 dias")
                        if st.button("✅ Confirmar Prorrogação", key=f"btn_prorrog_{row['id']}"):
                            ok, msg = db.prorrogar_aluguel(int(row['id']), nova_data.isoformat(), float(valor_adicional), obs_prorrog if obs_prorrog else None)
                            if ok:
                                st.success(f"✅ {msg}")
                                st.rerun()
                            else:
                                st.error(f"Erro: {msg}")

                        obs_atual = row.get('observacao', '') if pd.notna(row.get('observacao')) else ''
                        if obs_atual:
                            st.info(f"📝 **Observação:** {obs_atual}")

                    # Botão para Trocar Mala (Correção)
                    with st.expander("🔄 Trocar Mala (Correção)"):
                        st.warning("Use se escolheu a mala errada.")
                        
                        # Carregar malas disponíveis no período deste aluguel
                        dt_saida_mala = pd.to_datetime(row['data_saida']).date()
                        dt_retorno_mala = pd.to_datetime(row['data_prevista_retorno']).date()
                        malas_livres = db.get_malas_disponiveis_por_data(dt_saida_mala, dt_retorno_mala)
                        
                        if not malas_livres.empty:
                            dict_livres = {f"{m['codigo']} - {m.get('tamanho', '')} - {m.get('dimensoes', '')} - {m.get('cor', '')} - {m.get('marca', '')}": m['id'] for _, m in malas_livres.iterrows()}
                            nova_mala_escolhida = st.selectbox("Nova Mala (Livre no Período)", list(dict_livres.keys()), key=f"sel_troca_{row['id']}")
                            id_nova_mala = dict_livres[nova_mala_escolhida]
                            
                            if st.button("Confirmar Troca", key=f"btn_troca_{row['id']}"):
                                # ID da mala antiga já vem na query agora (row['mala_id'])
                                id_mala_antiga = int(row['mala_id']) if 'mala_id' in row else None
                                
                                if id_mala_antiga is None:
                                     # Fallback se a coluna não existir ainda no dataframe carregado em memória
                                     mala_antiga_df = db.get_malas()
                                     id_mala_antiga = mala_antiga_df[mala_antiga_df['codigo'] == row['mala_codigo']].iloc[0]['id']
                                
                                sucesso, msg = db.trocar_mala_aluguel(row['id'], int(id_mala_antiga), int(id_nova_mala))
                                if sucesso:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
                        else:
                            st.info("Sem malas disponíveis para troca neste período.")

                    # Botão para Corrigir Datas
                    with st.expander("📅 Corrigir Datas (Erro de Agendamento)"):
                        st.info("💡 Agora o sistema verifica automaticamente se as novas datas conflitam com outros aluguéis.")
                        col_d1, col_d2 = st.columns(2)
                        
                        data_saida_atual = pd.to_datetime(row['data_saida']).date()
                        data_prevista_atual = pd.to_datetime(row['data_prevista_retorno']).date()
                        
                        nova_data_saida = col_d1.date_input("Nova Data Saída", value=data_saida_atual, key=f"dt_sai_edit_{row['id']}")
                        nova_data_prevista = col_d2.date_input("Nova Data Retorno", value=data_prevista_atual, key=f"dt_ret_edit_{row['id']}")
                        
                        if st.button("Salvar Novas Datas", key=f"btn_save_dt_{row['id']}"):
                            if nova_data_prevista < nova_data_saida:
                                st.error("Data de retorno não pode ser anterior à saída.")
                            else:
                                sucesso, msg = db.update_aluguel_datas(row['id'], nova_data_saida, nova_data_prevista)
                                if sucesso:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)

                    st.divider()

                    # --- Acrescentar Mala para este Cliente ---
                    with st.expander("➕ Acrescentar Mala para este Cliente"):
                        st.info(f"Cliente: **{row['cliente_nome']}** | Período atual: {dt_saida.strftime('%d/%m')} até {dt_prevista.strftime('%d/%m')}")
                        st.caption("Adicione uma mala extra ao mesmo cliente, mantendo o mesmo período e cliente.")
                        
                        # Usar as mesmas datas do aluguel existente
                        data_ret_acresc = dt_saida
                        data_devol_acresc = dt_prevista
                        
                        # Buscar malas disponíveis para o mesmo período
                        malas_disp_acresc = db.get_malas_disponiveis_por_data(data_ret_acresc, data_devol_acresc)
                        
                        if malas_disp_acresc.empty:
                            st.warning("Não há malas disponíveis para este período.")
                        else:
                            dict_malas_acresc = {f"{m['codigo']} - {m.get('marca', '')} - {m.get('tamanho', '')} ({m.get('cor', '')})": m['id'] for _, m in malas_disp_acresc.iterrows()}
                            
                            mala_acresc_str = st.selectbox("Selecione a Mala Extra", list(dict_malas_acresc.keys()), key=f"acre_mala_{row['id']}")
                            mala_acresc_id = dict_malas_acresc[mala_acresc_str]
                            
                            col_ac1, col_ac2 = st.columns(2)
                            valor_acresc = col_ac1.number_input("Valor da mala extra (R$)", min_value=0.0, step=10.0, key=f"acre_val_{row['id']}")
                            taxa_acresc = col_ac2.number_input("Taxa de entrega extra (R$)", min_value=0.0, step=5.0, key=f"acre_tax_{row['id']}")
                            
                            acessorios_acresc = st.text_input("Acessórios extras", placeholder="Ex: Cadeado, Capa...", key=f"acre_acess_{row['id']}")
                            valor_acess_acresc = st.number_input("Valor acessórios extras (R$)", min_value=0.0, step=5.0, key=f"acre_vac_{row['id']}")
                            
                            total_acresc = valor_acresc + taxa_acresc + valor_acess_acresc
                            st.markdown(f"**Total desta mala extra:** R$ {total_acresc:.2f}")
                            
                            if st.button("✅ Adicionar Mala Extra", key=f"btn_acre_{row['id']}"):
                                sucesso_acre, msg_acre = db.criar_aluguel(
                                    int(mala_acresc_id),
                                    int(row['cliente_id']),
                                    data_ret_acresc,
                                    data_devol_acresc,
                                    valor_acresc,
                                    False,
                                    0.0,
                                    taxa_acresc,
                                    None,
                                    acessorios_acresc if acessorios_acresc else None,
                                    valor_acess_acresc,
                                    None,
                                    0.0
                                )
                                if sucesso_acre:
                                    st.success(f"✅ Mala extra adicionada ao cliente {row['cliente_nome']}!")
                                    st.rerun()
                                else:
                                    st.error(f"Erro: {msg_acre}")

                    st.divider()
                    
                    # Ação de Devolução
                    st.markdown(f"**Devolução Ideal:** {dt_sugerida_devolucao.strftime('%d/%m/%Y')}")
                    data_devolucao_real = st.date_input("Data Devolução Real", value=dt_sugerida_devolucao, key=f"dt_dev_{row['id']}")
                    
                    precisa_confirmar = (status_pagto not in ['Pago', 'Permuta']) and (valor_restante > 0.01)
                    confirmacao_devolucao = True
                    if precisa_confirmar:
                        st.error(f"Pagamento não está totalmente quitado. Falta: R$ {valor_restante:.2f}")
                        confirmacao_devolucao = st.checkbox("Registrar devolução mesmo com pagamento pendente", value=False, key=f"chk_dev_{row['id']}")

                    if st.button("✅ Registrar Devolução", key=f"btn_dev_{row['id']}", type="primary", disabled=(precisa_confirmar and not confirmacao_devolucao)):
                        # Usar função registrar_devolucao em vez de finalizar_aluguel para manter padrão se houver
                        # Mas checando o código, parece que finalizar_aluguel é o nome correto ou similar
                        # Vamos usar finalizar_aluguel com a data escolhida
                        sucesso, msg = db.finalizar_aluguel(int(row['id']), data_devolucao_real)
                        if sucesso:
                             st.success(f"Mala {row['mala_codigo']} devolvida com sucesso!")
                             st.rerun()
                        else:
                             st.error(msg)

                    # Botão para Cancelar Aluguel
                    if st.button("❌ Cancelar Aluguel", key=f"btn_cancel_{row['id']}", help="Use se o cliente desistiu ou o aluguel foi lançado errado. O valor será removido do financeiro."):
                         sucesso, msg = db.cancelar_aluguel(int(row['id']))
                         if sucesso:
                             st.success(msg)
                             st.rerun()
                         else:
                             st.error(msg)

    st.divider()
    st.subheader("Histórico de Devoluções")
    df_devolucoes = db.get_historico_devolucoes()
    if df_devolucoes.empty:
        st.info("Ainda não há devoluções registradas.")
    else:
        termo_hist = st.text_input("🔍 Buscar no Histórico (Cliente ou Mala)", placeholder="Digite para filtrar...", key="busca_hist_dev")
        df_hist_show = df_devolucoes.copy()
        if termo_hist:
            t = termo_hist.lower()
            df_hist_show['cliente_nome'] = df_hist_show['cliente_nome'].fillna('')
            df_hist_show['mala_codigo'] = df_hist_show['mala_codigo'].fillna('')
            df_hist_show = df_hist_show[
                df_hist_show['cliente_nome'].str.lower().str.contains(t) |
                df_hist_show['mala_codigo'].str.lower().str.contains(t)
            ]

        st.dataframe(
            df_hist_show[
                [
                    'data_retorno_real',
                    'mala_codigo',
                    'cliente_nome',
                    'data_saida',
                    'data_prevista_retorno',
                    'status_pagamento',
                    'total_geral',
                    'valor_sinal',
                    'restante',
                    'valor_avaria',
                    'destino',
                    'acessorios',
                ]
            ],
            column_config={
                "data_retorno_real": "Devolução",
                "mala_codigo": "Mala",
                "cliente_nome": "Cliente",
                "data_saida": "Saída",
                "data_prevista_retorno": "Fim Contrato",
                "status_pagamento": "Pagamento",
                "total_geral": st.column_config.NumberColumn("Total (R$)", format="R$ %.2f"),
                "valor_sinal": st.column_config.NumberColumn("Sinal (R$)", format="R$ %.2f"),
                "restante": st.column_config.NumberColumn("Restante (R$)", format="R$ %.2f"),
                "valor_avaria": st.column_config.NumberColumn("Avaria (R$)", format="R$ %.2f"),
                "destino": "Destino",
                "acessorios": "Acessórios",
            },
            use_container_width=True,
        )
        
        with st.expander("✏️ Alterar Pagamento (Histórico)"):
            df_opt = df_hist_show.copy()
            df_opt['cliente_nome'] = df_opt['cliente_nome'].fillna('')
            df_opt['mala_codigo'] = df_opt['mala_codigo'].fillna('')
            df_opt['data_retorno_real'] = pd.to_datetime(df_opt['data_retorno_real'], errors='coerce')
            
            opcoes = {}
            for _, r in df_opt.iterrows():
                data_dev = r['data_retorno_real'].strftime('%d/%m/%Y') if pd.notna(r['data_retorno_real']) else ''
                opcoes[f"{int(r['id'])} - {r['mala_codigo']} - {r['cliente_nome']} ({data_dev})"] = int(r['id'])
            
            if opcoes:
                escolha = st.selectbox("Selecione a devolução", list(opcoes.keys()), key="sel_hist_pgto")
                aluguel_id_sel = opcoes[escolha]
                
                linha = df_opt[df_opt['id'] == aluguel_id_sel].iloc[0]
                st.write(f"Pagamento atual: {linha.get('status_pagamento', '')}")
                if pd.notna(linha.get('restante')) and float(linha.get('restante')) > 0:
                    st.write(f"Restante: R$ {float(linha.get('restante')):.2f}")
                
                col_pg1, col_pg2, col_pg3 = st.columns(3)
                if col_pg1.button("Marcar como Pago ✅", key="btn_hist_pago"):
                    db.update_aluguel_pagamento(aluguel_id_sel, 'Pago')
                    st.success("Pagamento atualizado para Pago.")
                    st.rerun()
                if col_pg2.button("Marcar como Permuta 🤝", key="btn_hist_permuta"):
                    db.update_aluguel_pagamento(aluguel_id_sel, 'Permuta')
                    st.success("Pagamento atualizado para Permuta.")
                    st.rerun()
                if col_pg3.button("Marcar como Pendente ⏳", key="btn_hist_pendente"):
                    db.update_aluguel_pagamento(aluguel_id_sel, 'Pendente')
                    st.success("Pagamento atualizado para Pendente.")
                    st.rerun()
            else:
                st.info("Nenhuma devolução para editar.")

        with st.expander("🔄 Restaurar Devolução / Quebra"):
            st.warning("⚠️ Use esta função apenas se precisa corrigir um registro feito por engano.")
            df_r = df_hist_show.copy()
            df_r['cliente_nome'] = df_r['cliente_nome'].fillna('')
            df_r['mala_codigo'] = df_r['mala_codigo'].fillna('')
            df_r['data_retorno_real'] = pd.to_datetime(df_r['data_retorno_real'], errors='coerce')
            
            opcoes_r = {}
            for _, r in df_r.iterrows():
                data_dev = r['data_retorno_real'].strftime('%d/%m/%Y') if pd.notna(r['data_retorno_real']) else ''
                avaria_txt = f" [AVARIA R$ {float(r['valor_avaria']):.2f}]" if pd.notna(r.get('valor_avaria')) and float(r.get('valor_avaria', 0)) > 0 else ""
                opcoes_r[f"{int(r['id'])} - {r['mala_codigo']} - {r['cliente_nome']} ({data_dev}){avaria_txt}"] = int(r['id'])
            
            if opcoes_r:
                escolha_r = st.selectbox("Selecione a devolução para restaurar", list(opcoes_r.keys()), key="sel_hist_rest")
                aluguel_id_r = opcoes_r[escolha_r]
                
                linha_r = df_r[df_r['id'] == aluguel_id_r].iloc[0]
                
                st.write(f"**Mala:** {linha_r.get('mala_codigo', 'N/A')}")
                st.write(f"**Cliente:** {linha_r.get('cliente_nome', 'N/A')}")
                st.write(f"**Valor Avaria:** R$ {float(linha_r.get('valor_avaria', 0) or 0):.2f}")
                
                if st.button("🔄 Restaurar (Voltar para Aluguel Ativo)", key="btn_restaurar_dev"):
                    ok, msg = db.restaurar_aluguel_finalizado(aluguel_id_r)
                    if ok:
                        st.success(f"Aluguel restaurado! {msg}")
                        st.rerun()
                    else:
                        st.error(f"Erro: {msg}")
            else:
                st.info("Nenhuma devolução para restaurar.")

# --- CALENDÁRIO ---
elif st.session_state.page == "Calendário de Reservas":
    col_cal_1, col_cal_2 = st.columns([3, 1])
    col_cal_1.subheader("Calendário de Disponibilidade e Reservas")
    
    df_reservas = db.get_todos_alugueis()
    
    if not df_reservas.empty:
        # Filtro de Mês para PDF
        col_pdf1, col_pdf2 = st.columns([2, 1])
        with col_pdf1:
            # Converter para datetime
            df_reservas['data_saida_dt'] = pd.to_datetime(df_reservas['data_saida'])
            # Criar coluna auxiliar de Mês/Ano
            df_reservas['mes_ano'] = df_reservas['data_saida_dt'].dt.strftime('%Y-%m')
            
            # Pegar meses únicos e ordenar
            meses_disponiveis = sorted(df_reservas['mes_ano'].unique().tolist(), reverse=True)
            
            # Modo de Seleção: Mês ou Período
            modo_selecao = st.radio("Filtrar por:", ["Mês Específico", "Período Personalizado"], horizontal=True)
            
            if modo_selecao == "Mês Específico":
                # Adicionar opção "Todos"
                opcoes_mes = ["Todos"] + meses_disponiveis
                mes_selecionado = st.selectbox("📅 Selecione o Mês", opcoes_mes)
                periodo_custom = None
            else:
                mes_selecionado = None
                hoje = date.today()
                periodo_custom = st.date_input(
                    "📅 Selecione o Período (Início e Fim)",
                    value=(hoje, hoje + timedelta(days=30)),
                    format="DD/MM/YYYY"
                )
            
            # Botão de atualização manual
            if st.button("🔄 Atualizar Calendário"):
                st.rerun()
        
        with col_pdf2:
            st.write("") # Espaço para alinhar botão
            st.write("")
            
            # Escolha de formato PDF
            st.write("Formato do PDF:")
            formato_pdf = st.radio("Formato do PDF", ["Lista (Tabela Detalhada)", "Grade (Visual Mensal)"], horizontal=True, label_visibility="collapsed", key="pdf_format_radio")
            
            # Filtrar dados para o PDF
            df_pdf = pd.DataFrame()
            titulo_pdf = ""
            nome_arq = ""
            
            if modo_selecao == "Mês Específico":
                if mes_selecionado != "Todos":
                    df_pdf = df_reservas[df_reservas['mes_ano'] == mes_selecionado]
                    nome_arq = f"cronograma_{mes_selecionado}.pdf"
                    titulo_pdf = f"{mes_selecionado}"
                else:
                    df_pdf = df_reservas
                    nome_arq = f"cronograma_geral_{date.today()}.pdf"
                    titulo_pdf = "Geral"
            else:
                # Filtrar por período customizado
                if isinstance(periodo_custom, tuple) and len(periodo_custom) == 2:
                    start_date, end_date = periodo_custom
                    # Filtrar onde (saida <= end) E (retorno >= start) -> Intersecção
                    # Mas para cronograma, geralmente queremos o que COMEÇA no período ou ESTÁ ATIVO?
                    # Vamos pegar tudo que tem intersecção com o período
                    # Converter start_date e end_date para datetime para comparação segura
                    start_dt = pd.to_datetime(start_date)
                    end_dt = pd.to_datetime(end_date)
                    
                    # As colunas já foram convertidas para datetime antes? Sim, mas vamos garantir
                    df_temp = df_reservas.copy()
                    df_temp['data_saida'] = pd.to_datetime(df_temp['data_saida'])
                    df_temp['data_prevista_retorno'] = pd.to_datetime(df_temp['data_prevista_retorno'])
                    
                    mask = (
                        (df_temp['data_saida'].dt.date <= end_date) & 
                        (df_temp['data_prevista_retorno'].dt.date >= start_date)
                    )
                    df_pdf = df_temp[mask]
                    nome_arq = f"cronograma_{start_date}_{end_date}.pdf"
                    titulo_pdf = f"{start_date.strftime('%d/%m')} a {end_date.strftime('%d/%m')}"
                else:
                    st.warning("Selecione data de início e fim.")
            
            # Gerar PDF
            if not df_pdf.empty:
                df_pdf = df_pdf.sort_values(by='data_saida')
                
                # Mapear escolha para código
                if "Grade" in formato_pdf or "Visual" in formato_pdf:
                    mode_pdf = 'visual'
                else:
                    mode_pdf = 'list'
                
                # Debug visual (feedback para o usuário)
                # st.write(f"Gerando PDF em modo: {mode_pdf}") 
                
                # Se for visual e "Todos", avisar que vai pegar o mês atual
                if mode_pdf == 'visual' and mes_selecionado == "Todos":
                     st.caption("⚠️ O PDF Visual exibe apenas o mês atual quando o filtro é 'Todos'. Selecione um mês específico para ver outros.")
                
                pdf_bytes = create_pdf_schedule(df_pdf, titulo_pdf, mode=mode_pdf)
                
                # Nome do arquivo dinâmico para evitar cache
                import time
                ts = int(time.time())
                
                st.download_button(
                    label=f"📄 Baixar PDF ({'Grade Visual' if mode_pdf == 'visual' else 'Lista Tabela'})",
                    data=pdf_bytes,
                    file_name=f"{nome_arq.replace('.pdf', '')}_{mode_pdf}_{ts}.pdf",
                    mime="application/pdf"
                )
            else:
                st.warning("Sem dados.")
    
    # Opções de visualização
    view_mode = st.radio("Modo de Visualização", ["Calendário Mensal", "Linha do Tempo (Gantt)"], horizontal=True)
    
    if df_reservas.empty:
        st.info("Não há reservas registradas para exibir no calendário.")
    else:
        # Converter colunas de data para datetime
        # Garantir que é datetime antes de pegar .dt.date
        df_reservas['data_saida'] = pd.to_datetime(df_reservas['data_saida'])
        df_reservas['data_prevista_retorno'] = pd.to_datetime(df_reservas['data_prevista_retorno'])
        
        # Agora para comparação no calendário visual, usaremos .date() individualmente ou .dt.date se precisar coluna
        
        if view_mode == "Calendário Mensal":
            # Preparar eventos para o calendário
            events = []
            
            # Dicionário para agrupar reservas por mala para facilitar visualização
            malas_com_reserva = df_reservas['mala_codigo'].unique()
            
            for _, row in df_reservas.iterrows():
                # Simplificar título para economizar espaço
                # Ex: M001 (Maria) em vez de M001 | Maria Silva...
                nome_curto = row['cliente_nome'].split()[0] if row['cliente_nome'] else "Cli"
                titulo_evento = f"{row['mala_codigo']} ({nome_curto})"
                
                # Cores diferentes para status diferentes (ex: se tivesse status 'Reservado' vs 'Ativo')
                # Por enquanto, vamos diferenciar Retirada e Aluguel
                
                # Evento de Retirada (Vermelho) - Marcador no dia de início
                events.append({
                    "title": f"📍 {row['mala_codigo']}",
                    "start": row['data_saida'].strftime('%Y-%m-%d'),
                    # Remover 'end' para evento pontual de dia inteiro, ou manter igual start
                    "color": "#FF4B4B", # Vermelho
                    "display": "list-item",
                    "textColor": "#FF4B4B",
                    "allDay": True
                })
                
                # Evento de Devolução (Azul) - Marcador no dia previsto de retorno
                events.append({
                    "title": f"🏁 {row['mala_codigo']}",
                    "start": row['data_prevista_retorno'].strftime('%Y-%m-%d'),
                    "color": "#1E90FF", # Azul
                    "display": "list-item",
                    "textColor": "#1E90FF",
                    "allDay": True
                })
                
                # Evento de Aluguel (Barra contínua)
                # O calendário fullcalendar trata a data final como exclusiva, então adicionamos 1 dia
                data_fim_cal = (row['data_prevista_retorno'] + timedelta(days=1)).strftime('%Y-%m-%d')
                
                events.append({
                    "title": titulo_evento,
                    "start": row['data_saida'].strftime('%Y-%m-%d'),
                    "end": data_fim_cal,
                    "color": "#28a745", # Verde
                    "allDay": True,
                    "extendedProps": {
                        "description": f"Aluguel da mala {row['mala_codigo']} para {row['cliente_nome']}"
                    }
                })
                
            calendar_options = {
                "headerToolbar": {
                    "left": "prev,next today",
                    "center": "title",
                    "right": "dayGridMonth,listWeek"
                },
                "initialView": "dayGridMonth",
                "navLinks": True,
                "selectable": True,
                "selectMirror": True,
                "dayMaxEvents": 4, # Voltar a limitar, mas com número razoável (4 eventos + botão 'more')
                "firstDay": 1, # Segunda-feira
                "contentHeight": "auto", 
                "height": "auto", 
                "fixedWeekCount": False,
                "eventDisplay": "block",
                "eventTimeFormat": {
                    "hour": "2-digit",
                    "minute": "2-digit",
                    "meridiem": False
                }
            }
            
            st.markdown("""
            <style>
                /* Fonte menor para caber mais */
                .fc-event-title {
                    font-size: 0.75em !important;
                    white-space: nowrap !important; /* Não quebrar linha para ficar compacto */
                    overflow: hidden;
                    text-overflow: ellipsis;
                }
                .fc-daygrid-event {
                    padding: 1px 2px !important;
                    margin-bottom: 1px !important;
                }
                /* Botão "+ more" mais discreto */
                .fc-more-link {
                    font-size: 0.8em;
                    color: #555;
                }
                /* Legenda */
                .legenda-cal {
                    background-color: #f0f2f6; 
                    padding: 10px; 
                    border-radius: 8px; 
                    margin-bottom: 15px; 
                    display: flex; 
                    gap: 15px; 
                    flex-wrap: wrap;
                    align-items: center;
                    font-size: 0.9em;
                }
            </style>
            <div class="legenda-cal">
                <div style="color: black;"><b>Legenda:</b></div>
                <div style="color: black;"><span style="color: #28a745; font-size: 1.2em;">■</span> Alugado (Mala Ocupada)</div>
                <div style="color: black;"><span style="color: #FF4B4B; font-size: 1.2em;">●</span> Dia de Retirada</div>
                <div style="color: black;"><span style="color: #1E90FF; font-size: 1.2em;">●</span> Dia de Devolução</div>
            </div>
            """, unsafe_allow_html=True)
            
            calendar(events=events, options=calendar_options)
            
        else:
            # Criar gráfico de Gantt
            fig = px.timeline(
                df_reservas, 
                x_start="data_saida", 
                x_end="data_prevista_retorno", 
                y="mala_codigo",
                color="status",
                hover_data=["cliente_nome", "mala_cor"],
                title="Cronograma de Aluguéis",
                labels={"mala_codigo": "Mala", "data_saida": "Início", "data_prevista_retorno": "Fim", "status": "Status"}
            )
            
            # Ordenar eixo Y para facilitar leitura
            fig.update_yaxes(categoryorder="category ascending")
            
            # Melhorar layout
            fig.update_layout(
                xaxis_title="Data",
                yaxis_title="Mala",
                showlegend=True,
                height=600
            )
            
            st.plotly_chart(fig, use_container_width=True)
        
        st.divider()
        st.write("**Lista Detalhada de Reservas:**")
        
        # Formatar datas para exibição na tabela
        df_display = df_reservas.copy()
        df_display['data_saida'] = df_display['data_saida'].dt.strftime('%d/%m/%Y')
        df_display['data_prevista_retorno'] = df_display['data_prevista_retorno'].dt.strftime('%d/%m/%Y')
        
        st.dataframe(
            df_display[['mala_codigo', 'cliente_nome', 'data_saida', 'data_prevista_retorno', 'status', 'mala_cor']],
            use_container_width=True
        )

# --- ANÁLISE FINANCEIRA ---
elif st.session_state.page == "Análise Financeira":
    st.subheader("Análise Financeira e Controle de Gastos")
    
    # Criar abas para separar Análise de ROI e Controle de Gastos Extras
    tab_geral, tab_analise, tab_gastos, tab_vendas, tab_usuarios = st.tabs(["💼 Balanço Geral do Negócio", "📊 Análise de Aluguéis & ROI", "💸 Controle de Gastos Extras", "🛒 Vendas de Malas", "👥 Usuários"])
    
    with tab_geral:
        st.subheader("💰 Visão Macro do Negócio")
        
        # --- NOVO: Gráfico de Evolução do Faturamento Mensal ---
        st.markdown("### 📈 Evolução do Faturamento Mensal")
        df_fat_mensal = db.get_faturamento_mensal()
        
        if not df_fat_mensal.empty:
            # Melhorar formatação do mês para o gráfico (Ex: 2024-03 -> Mar/24)
            df_fat_mensal['mes_formatado'] = pd.to_datetime(df_fat_mensal['mes_ano']).dt.strftime('%b/%y')
            
            # Criar gráfico de linha suave com área preenchida
            fig_fat = px.line(
                df_fat_mensal, 
                x='mes_formatado', 
                y='faturamento', 
                markers=True,
                title="Crescimento do Faturamento",
                labels={'faturamento': 'Faturamento (R$)', 'mes_formatado': 'Mês'},
                text='faturamento'
            )
            # Personalizar visual
            fig_fat.update_traces(
                texttemplate='R$ %{text:.2f}', 
                textposition='top center', 
                line_color='#28a745', 
                line_width=4,
                line_shape='spline' # Suavizar curva
            )
            # Adicionar área preenchida
            fig_fat.update_traces(fill='tozeroy', fillcolor='rgba(40, 167, 69, 0.2)')
            
            fig_fat.update_layout(
                yaxis_title="Valor (R$)", 
                xaxis_title=None, 
                showlegend=False,
                height=400,
                hovermode="x unified"
            )
            
            st.plotly_chart(fig_fat, use_container_width=True)
        else:
            st.info("Sem dados suficientes para gerar a curva de faturamento.")
            
        st.divider()
        # -------------------------------------------------------
        
        st.info("💡 **Dúvida Comum:** O 'Saldo Disponível' agora considera apenas o que saiu do **Caixa da Empresa**. Investimentos feitos por sócios (dinheiro externo) são mostrados separadamente e não deixam o saldo negativo.")
        
        # Carregar dados
        df_fin_macro = db.get_analise_financeira()
        df_gastos_macro = db.get_gastos_extras()
        
        # Calcular Totais Gerais
        total_faturamento = df_fin_macro['total_faturado'].sum() if not df_fin_macro.empty else 0.0
        
        # Separar Investimentos em Malas (Caixa vs Externo)
        investimento_malas_caixa = 0.0
        investimento_malas_externo = 0.0
        
        if not df_fin_macro.empty:
            # Considerar 'Caixa da Empresa' como saída do caixa. Outros (ou None) como Externo.
            investimento_malas_caixa = df_fin_macro[df_fin_macro['gestor_nome'] == 'Caixa da Empresa']['custo_aquisicao'].sum()
            investimento_malas_externo = df_fin_macro[df_fin_macro['gestor_nome'] != 'Caixa da Empresa']['custo_aquisicao'].sum()
            
        # Separar Gastos Extras (Caixa vs Externo)
        gastos_extras_caixa = 0.0
        gastos_extras_externo = 0.0
        
        if not df_gastos_macro.empty:
            gastos_extras_caixa = df_gastos_macro[df_gastos_macro['gestor_nome'] == 'Caixa da Empresa']['valor'].sum()
            gastos_extras_externo = df_gastos_macro[df_gastos_macro['gestor_nome'] != 'Caixa da Empresa']['valor'].sum()
        
        # Totais Calculados
        total_saidas_caixa = investimento_malas_caixa + gastos_extras_caixa
        total_investido_externo = investimento_malas_externo + gastos_extras_externo
        
        saldo_liquido_real = total_faturamento - total_saidas_caixa
        
        # Métricas Principais com Nomes Claros
        col_macro1, col_macro2, col_macro3, col_macro4 = st.columns(4)
        
        col_macro1.metric(
            "📈 Faturamento Bruto", 
            f"R$ {total_faturamento:,.2f}", 
            help="Total de dinheiro que entrou com aluguéis."
        )
        
        col_macro2.metric(
            "🔄 Reinvestido (Do Caixa)", 
            f"R$ {total_saidas_caixa:,.2f}", 
            delta=f"-R$ {total_saidas_caixa:,.2f}", 
            delta_color="inverse",
            help="Dinheiro do próprio negócio usado para comprar malas ou pagar contas (Gestor: Caixa da Empresa)."
        )
        
        col_macro3.metric(
            "💵 Saldo em Caixa", 
            f"R$ {saldo_liquido_real:,.2f}", 
            delta=f"Lucro Real" if saldo_liquido_real > 0 else "Negativo",
            help="O que sobrou no caixa da empresa (Faturamento - Reinvestimentos do Caixa)."
        )
        
        col_macro4.metric(
            "💼 Aporte Sócios (Externo)", 
            f"R$ {total_investido_externo:,.2f}",
            help="Dinheiro investido pelos sócios (não sai do caixa da empresa)."
        )
        
        st.divider()
        
        # Indicador de Reinvestimento (Baseado apenas no que saiu do caixa)
        if total_faturamento > 0:
            perc_reinvestido = (total_saidas_caixa / total_faturamento)
            st.write(f"📊 **Taxa de Reinvestimento Orgânico:** Você usou **{perc_reinvestido:.1%}** do faturamento para crescer o negócio.")
            st.progress(min(perc_reinvestido, 1.0))
        
        st.divider()
        
        # Gráfico Waterfall (Cascata) Ajustado
        fig_waterfall = px.bar(
            x=["Faturamento", "Reinvestimento (Caixa)", "Saldo Disponível", "Aporte Externo (Informativo)"],
            y=[total_faturamento, -total_saidas_caixa, saldo_liquido_real, total_investido_externo],
            text=[f"+ {total_faturamento:,.2f}", f"- {total_saidas_caixa:,.2f}", f"= {saldo_liquido_real:,.2f}", f"({total_investido_externo:,.2f})"],
            title="Fluxo de Caixa Real (Descontando Aportes de Sócios)",
            color=["Faturamento", "Reinvestimento (Caixa)", "Saldo Disponível", "Aporte Externo (Informativo)"],
            color_discrete_map={
                "Faturamento": "#28a745", # Verde
                "Reinvestimento (Caixa)": "#EF553B",   # Vermelho
                "Saldo Disponível": "#1E90FF" if saldo_liquido_real >= 0 else "#B22222", # Azul ou Vermelho Escuro
                "Aporte Externo (Informativo)": "#FFA500" # Laranja
            }
        )
        fig_waterfall.update_traces(textposition='outside')
        fig_waterfall.update_layout(showlegend=False, yaxis_title="Valor (R$)")
        st.plotly_chart(fig_waterfall, use_container_width=True)
        
        # Botão para Baixar PDF do Balanço Geral
        totais_balanco = {
            'faturamento': total_faturamento,
            'saidas': total_saidas_caixa, # Apenas saídas do caixa
            'saldo': saldo_liquido_real
        }
        # Buscar extrato para o PDF
        # df_extrato já foi carregado no 'Extrato Detalhado' abaixo, mas para garantir ordem e pureza:
        df_extrato_pdf = db.get_extrato_financeiro()
        
        pdf_balanco_bytes = create_pdf_balanco_geral(df_extrato_pdf, totais_balanco)
        
        st.download_button(
            label="📄 Baixar Relatório de Balanço Geral (PDF)",
            data=pdf_balanco_bytes,
            file_name=f"balanco_geral_{date.today()}.pdf",
            mime="application/pdf"
        )
        
        st.divider()
        
        # --- NOVO: Extrato Detalhado (O que o usuário pediu) ---
        st.markdown("### 📝 Extrato Detalhado (Como cheguei nesse saldo?)")
        st.info("Aqui você vê exatamente a conta: **Entradas (Aluguéis)** menos **Saídas (Compras e Gastos)**.")
        
        df_extrato = db.get_extrato_financeiro()
        
        if not df_extrato.empty:
            # Colorir valores
            def color_valor(val):
                color = 'green' if val >= 0 else 'red'
                return f'color: {color}'

            # Renomear colunas
            df_exibicao_extrato = df_extrato[['data', 'tipo', 'descricao', 'valor']].copy()
            df_exibicao_extrato.columns = ['Data', 'Tipo', 'Descrição', 'Valor (R$)']
            
            # Formatar Data
            df_exibicao_extrato['Data'] = pd.to_datetime(df_exibicao_extrato['Data']).dt.strftime('%d/%m/%Y')
            
            st.dataframe(
                df_exibicao_extrato.style.map(color_valor, subset=['Valor (R$)']).format({'Valor (R$)': 'R$ {:,.2f}'}),
                use_container_width=True,
                height=400
            )
        else:
            st.warning("Nenhuma movimentação registrada ainda.")

        # Detalhamento das Saídas (Gráfico de Pizza)
        st.write("##### Para onde foi o dinheiro reinvestido? (Do Caixa)")
        df_saidas = pd.DataFrame({
            'Tipo': ['Compra de Malas (Caixa)', 'Gastos Extras (Caixa)'],
            'Valor': [investimento_malas_caixa, gastos_extras_caixa]
        })
        fig_saidas = px.pie(df_saidas, values='Valor', names='Tipo', title='Onde o dinheiro do caixa foi gasto?', hole=0.4, color_discrete_sequence=['#EF553B', '#FFA15A'])
        fig_saidas.update_traces(textposition='inside', textinfo='percent+label+value')
        st.plotly_chart(fig_saidas, use_container_width=True)

        # NOVO: Tabela Unificada de Saídas para Conferência
        st.divider()
        st.markdown("### 🕵️‍♀️ Conferência Detalhada de Saídas")
        with st.expander("Ver lista completa (Malas + Extras) para achar duplicados", expanded=True):
            st.info("💡 **Dica:** Se você cadastrou o valor da mala no 'Cadastro de Mala' **E** também lançou em 'Gastos Extras', o valor aparecerá duplicado aqui. **Apague o Gasto Extra** correspondente na aba 'Controle de Gastos Extras'.")
            
            # Dados das Malas
            df_malas_conf = db.get_malas()
            lista_malas = []
            if not df_malas_conf.empty:
                 for _, row in df_malas_conf.iterrows():
                     if pd.notna(row['valor_pago']) and row['valor_pago'] > 0:
                         gestor = row['gestor_nome'] if 'gestor_nome' in row and pd.notna(row['gestor_nome']) else "Não Informado"
                         lista_malas.append({
                             'Tipo (Origem)': '📦 Cadastro de Mala',
                             'Descrição': f"Mala {row['codigo']} - {row['marca']} ({row['tamanho']})",
                             'Gestor': gestor,
                             'Valor': row['valor_pago'],
                             'Ação Necessária': 'Editar em "Cadastrar Mala" > "Gerenciar"'
                         })
            
            # Dados dos Gastos Extras
            df_gastos_conf = db.get_gastos_extras()
            lista_gastos = []
            if not df_gastos_conf.empty:
                for _, row in df_gastos_conf.iterrows():
                    lista_gastos.append({
                        'Tipo (Origem)': '💸 Gasto Extra',
                        'Descrição': f"{row['descricao']} ({row['categoria']})",
                        'Gestor': row['gestor_nome'] if pd.notna(row['gestor_nome']) else "Não Informado",
                        'Valor': row['valor'],
                        'Ação Necessária': f"Excluir ID {row['id']} em 'Controle de Gastos'"
                    })
            
            # Unir e Mostrar
            if lista_malas or lista_gastos:
                df_unificado = pd.DataFrame(lista_malas + lista_gastos)
                # Ordenar por valor para facilitar achar duplicados
                df_unificado = df_unificado.sort_values(by='Valor', ascending=False)
                
                st.dataframe(
                    df_unificado.style.format({'Valor': 'R$ {:.2f}'}),
                    use_container_width=True
                )
            else:
                st.info("Nenhuma saída registrada.")

    with tab_analise:
        st.subheader("Análise de Retorno sobre Investimento (ROI)")

        df_fin = db.get_analise_financeira()

        # --- Projeção de Aluguéis a Receber (EM DESTAQUE NO TOPO) ---
        df_ativos = db.get_alugueis_ativos()

        # Filtros por Mês
        col_filtro1, col_filtro2 = st.columns([1, 2])
        mes_filtro = col_filtro1.selectbox("Filtrar por Mês", ["Todos", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"], index=0)
        anos_disponiveis = sorted({pd.to_datetime(a['data_saida']).year for _, a in df_ativos.iterrows() if pd.notna(a.get('data_saida'))}, reverse=True)
        if not anos_disponiveis:
            anos_disponiveis = [date.today().year]
        ano_filtro = col_filtro2.selectbox("Filtrar por Ano", anos_disponiveis, index=0)

        total_a_receber = 0
        total_bruto = 0
        total_sinal = 0
        qtd_pendente = 0
        total_a_receber_filtrado = 0
        total_bruto_filtrado = 0
        total_sinal_filtrado = 0
        qtd_pendente_filtrado = 0

        if not df_ativos.empty:
            for _, row in df_ativos.iterrows():
                if row.get('status_pagamento') == 'Pendente':
                    data_saida = pd.to_datetime(row.get('data_saida'))
                    mes_atual = data_saida.month if pd.notna(data_saida) else None
                    ano_atual = data_saida.year if pd.notna(data_saida) else None
                    mes_nome = ["Todos", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"][mes_atual] if mes_atual else "Todos"

                    sinal = float(row.get('valor_sinal', 0) or 0)
                    valor_aluguel = float(row.get('valor', 0))

                    # Totais SEM filtro
                    total_bruto += valor_aluguel
                    total_sinal += sinal
                    total_a_receber += valor_aluguel - sinal
                    qtd_pendente += 1

                    # Totais COM filtro
                    if (mes_filtro == "Todos" or mes_nome == mes_filtro) and (ano_filtro == ano_atual or ano_filtro == "Todos"):
                        total_bruto_filtrado += valor_aluguel
                        total_sinal_filtrado += sinal
                        total_a_receber_filtrado += valor_aluguel - sinal
                        qtd_pendente_filtrado += 1

        # Usar valores filtrados se filtro ativo, senão usar totais
        usar_filtro = mes_filtro != "Todos" or len(anos_disponiveis) > 1
        total_bruto_exib = total_bruto_filtrado if usar_filtro else total_bruto
        total_sinal_exib = total_sinal_filtrado if usar_filtro else total_sinal
        total_a_receber_exib = total_a_receber_filtrado if usar_filtro else total_a_receber
        qtd_exib = qtd_pendente_filtrado if usar_filtro else qtd_pendente

        col_proj1, col_proj2, col_proj3, col_proj4 = st.columns(4)
        col_proj1.metric("💰 A Receber (Líquido)", f"R$ {total_a_receber_exib:,.2f}", help="Valor total a receber (valor do aluguel - sinal recebido)")
        col_proj2.metric("💵 Bruto (Total)", f"R$ {total_bruto_exib:,.2f}", help="Valor bruto total pendente sem descontar o sinal")
        col_proj3.metric("📥 Sinal Recebido", f"R$ {total_sinal_exib:,.2f}", help="Valor de sinais já recebidos (deduzidos do líquido)")
        col_proj4.metric("📋 Qtd. Pendente", f"{qtd_exib}", f"Filtrado" if usar_filtro else "Total")

        if df_fin.empty:
            st.info("Não há dados suficientes para análise.")
        else:
            # Calcular Lucro/Prejuízo e ROI
            df_fin['custo_aquisicao'] = df_fin['custo_aquisicao'].fillna(0)
            df_fin['saldo'] = df_fin['total_faturado'] - df_fin['custo_aquisicao']
            df_fin['status_roi'] = df_fin['saldo'].apply(lambda x: 'Lucro' if x > 0 else 'A recuperar')
            
            # --- NOVO: Histórico Completo de Transações ---
            st.write("### 📜 Histórico Completo de Aluguéis (Desde o Início)")
            st.info("Aqui você vê todas as movimentações financeiras registradas no sistema, desde o primeiro aluguel.")
            
            # Buscar todos os aluguéis (incluindo finalizados)
            historico_alugueis = db.get_historico_completo()
            
            # Filtrar cancelados (remover do histórico visual)
            if not historico_alugueis.empty:
                historico_alugueis = historico_alugueis[historico_alugueis['status'] != 'Cancelado']
            
            if not historico_alugueis.empty:
                # Converter datas
                historico_alugueis['data_saida'] = pd.to_datetime(historico_alugueis['data_saida']).dt.strftime('%d/%m/%Y')
                historico_alugueis['data_retorno'] = pd.to_datetime(historico_alugueis['data_prevista_retorno']).dt.strftime('%d/%m/%Y')
                
                # Formatar valores
                historico_alugueis['valor_total'] = historico_alugueis.apply(lambda x: x['valor'] + (x['taxa_entrega'] if pd.notna(x['taxa_entrega']) else 0), axis=1)
                
                # Renomear colunas para exibição amigável
                df_hist_exibicao = historico_alugueis[['id', 'data_saida', 'data_retorno', 'mala_codigo', 'cliente_nome', 'valor_total', 'status_pagamento', 'valor_sinal']].copy()
                df_hist_exibicao.columns = ['ID', 'Data Saída', 'Data Retorno', 'Mala', 'Cliente', 'Valor Total (R$)', 'Pagamento', 'Sinal']
                
                st.dataframe(
                    df_hist_exibicao.drop(columns=['Sinal']).style.format({'Valor Total (R$)': 'R$ {:.2f}'}),
                    use_container_width=True,
                    hide_index=True
                )
                
                # Calcular Faturamento Total Acumulado (sincronizado com o Relatório Geral)
                # Soma Valor Total se Pago, OU Soma Sinal se Pendente
                def calcular_faturamento_real(row):
                    if row['Pagamento'] == 'Pago':
                        return row['Valor Total (R$)']
                    elif row['Pagamento'] == 'Pendente':
                        return row['Sinal'] if pd.notna(row['Sinal']) else 0.0
                    else:
                        return 0.0
                
                total_historico = df_hist_exibicao.apply(calcular_faturamento_real, axis=1).sum()
                st.metric("Faturamento Total Acumulado (Todos os Tempos)", f"R$ {total_historico:,.2f}", help="Soma de todos os aluguéis já pagos + sinais recebidos de aluguéis pendentes.")
                
            else:
                st.warning("Nenhum histórico de aluguel encontrado.")
                
            st.divider()

            # --- NOVO: Relatório de Totais ---
            st.markdown("### 📊 Relatório Geral de Resultados")
            
            # Calcular totais adicionais
            total_alugueis_finalizados = len(db.get_todos_alugueis()[db.get_todos_alugueis()['status'] == 'Finalizado'])
            
            # Usar container para destacar o resumo
            with st.container(border=True):
                col_res1, col_res2, col_res3 = st.columns(3)
                
                total_investido = df_fin['custo_aquisicao'].sum()
                total_retorno = df_fin['total_faturado'].sum() # Já filtrado por 'Pago' na query
                saldo_geral = total_retorno - total_investido
                
                col_res1.metric("💰 Total Recebido (Caixa)", f"R$ {total_retorno:,.2f}", help="Soma de todos os aluguéis com pagamento confirmado.")
                col_res2.metric("✅ Aluguéis Concluídos", f"{total_alugueis_finalizados}", help="Total de aluguéis finalizados até hoje.")
                col_res3.metric("📈 Lucro Líquido Total", f"R$ {saldo_geral:,.2f}", delta_color="normal", help="Total Recebido - Total Investido na Compra das Malas")

            st.divider()
            
            # Métricas Gerais (Investimento)
            st.write("### Análise de Investimento")
            col1, col2 = st.columns(2)
            col1.metric("Total Investido em Malas", f"R$ {total_investido:,.2f}")
            col2.metric("Retorno sobre Investimento (ROI)", f"{(total_retorno/total_investido - 1):.1%}" if total_investido > 0 else "N/A")
            
            st.divider()
            
            # --- NOVO: Ranking de Malas Mais Alugadas ---
            st.write("### 🏆 Ranking de Popularidade (Quais malas saem mais?)")

            # Ordenar por quantidade de aluguéis (decrescente)
            # Garantir que qtd_alugueis existe (caso o banco não tenha retornado por algum motivo de cache, mas deve ter)
            if 'qtd_alugueis' in df_fin.columns:
                df_ranking = df_fin.sort_values(by='qtd_alugueis', ascending=False).reset_index(drop=True)

                # Criar coluna descritiva amigável
                # Ex: "M001 - Mala P (Bege)"
                df_ranking['descricao'] = df_ranking.apply(lambda x: f"{x['codigo']} - {x['tamanho']} ({x['cor']}) - {x['marca']}", axis=1)

                # Selecionar colunas relevantes
                df_ranking_view = df_ranking[['descricao', 'qtd_alugueis', 'total_faturado', 'custo_aquisicao']]
                df_ranking_view.columns = ['Mala (Detalhes)', 'Qtd. Aluguéis', 'Total Faturado (R$)', 'Custo (R$)']

                # Exibir top 3 em destaque (metricas)
                if len(df_ranking) >= 3:
                    top3 = df_ranking.head(3)
                    col_top1, col_top2, col_top3 = st.columns(3)
                    col_top1.metric("🥇 1º Lugar", f"{top3.iloc[0]['codigo']} ({top3.iloc[0]['cor']})", f"{top3.iloc[0]['qtd_alugueis']} aluguéis")
                    col_top2.metric("🥈 2º Lugar", f"{top3.iloc[1]['codigo']} ({top3.iloc[1]['cor']})", f"{top3.iloc[1]['qtd_alugueis']} aluguéis")
                    col_top3.metric("🥉 3º Lugar", f"{top3.iloc[2]['codigo']} ({top3.iloc[2]['cor']})", f"{top3.iloc[2]['qtd_alugueis']} aluguéis")
                elif not df_ranking.empty:
                    # Se tiver menos de 3, mostra o que tem
                    st.metric("🥇 Mais Alugada", f"{df_ranking.iloc[0]['codigo']} ({df_ranking.iloc[0]['cor']})", f"{df_ranking.iloc[0]['qtd_alugueis']} aluguéis")

                # Tabela completa
                st.dataframe(
                    df_ranking_view.style.format({
                        'Total Faturado (R$)': 'R$ {:.2f}',
                        'Custo (R$)': 'R$ {:.2f}'
                    }).background_gradient(subset=['Qtd. Aluguéis'], cmap='Blues'),
                    use_container_width=True
                )

                # --- Ranking por Valor Total Alugado ---
                st.divider()
                st.write("### 💰 Ranking por Valor Total Alugado (Maior Faturamento)")

                df_ranking_valor = df_fin.sort_values(by='total_faturado', ascending=False).reset_index(drop=True)
                df_ranking_valor['descricao'] = df_ranking_valor.apply(lambda x: f"{x['codigo']} - {x['tamanho']} ({x['cor']}) - {x['marca']}", axis=1)
                df_ranking_valor_view = df_ranking_valor[['descricao', 'qtd_alugueis', 'total_faturado', 'custo_aquisicao']]
                df_ranking_valor_view.columns = ['Mala (Detalhes)', 'Qtd. Aluguéis', 'Total Faturado (R$)', 'Custo (R$)']

                if len(df_ranking_valor) >= 3:
                    top3v = df_ranking_valor.head(3)
                    col_v1, col_v2, col_v3 = st.columns(3)
                    col_v1.metric("🥇 1º Lugar", f"{top3v.iloc[0]['codigo']} ({top3v.iloc[0]['cor']})", f"R$ {top3v.iloc[0]['total_faturado']:,.2f}")
                    col_v2.metric("🥈 2º Lugar", f"{top3v.iloc[1]['codigo']} ({top3v.iloc[1]['cor']})", f"R$ {top3v.iloc[1]['total_faturado']:,.2f}")
                    col_v3.metric("🥉 3º Lugar", f"{top3v.iloc[2]['codigo']} ({top3v.iloc[2]['cor']})", f"R$ {top3v.iloc[2]['total_faturado']:,.2f}")
                elif not df_ranking_valor.empty:
                    st.metric("🥇 Maior Faturamento", f"{df_ranking_valor.iloc[0]['codigo']} ({df_ranking_valor.iloc[0]['cor']})", f"R$ {df_ranking_valor.iloc[0]['total_faturado']:,.2f}")

                st.dataframe(
                    df_ranking_valor_view.style.format({
                        'Total Faturado (R$)': 'R$ {:.2f}',
                        'Custo (R$)': 'R$ {:.2f}'
                    }).background_gradient(subset=['Total Faturado (R$)'], cmap='Greens'),
                    use_container_width=True
                )

                # Botão de Download PDF do Ranking
                pdf_ranking_bytes = create_pdf_ranking(df_ranking)
                st.download_button(
                    label="📄 Baixar Ranking em PDF",
                    data=pdf_ranking_bytes,
                    file_name=f"ranking_popularidade_{date.today()}.pdf",
                    mime="application/pdf"
                )

                # --- Ranking de Clientes ---
                st.divider()
                st.write("### 🏅 Ranking de Clientes (Por Dias de Aluguel)")

                df_ranking_cli = db.get_ranking_clientes()
                if not df_ranking_cli.empty:
                    df_ranking_cli['total_faturado'] = df_ranking_cli['total_faturado'].fillna(0)

                    col_cli1, col_cli2 = st.columns(2)
                    col_cli1.metric("🥇 Cliente que mais alugou (por dias)", f"{df_ranking_cli.iloc[0]['cliente_nome']}", f"{int(df_ranking_cli.iloc[0]['qtd_dias_aluguel'])} dias / {int(df_ranking_cli.iloc[0]['qtd_alugueis'])} aluguéis")
                    col_cli2.metric("💰 Maior faturamento", f"{df_ranking_cli.iloc[0]['cliente_nome']}", f"R$ {df_ranking_cli.iloc[0]['total_faturado']:,.2f}")

                    df_cli_view = df_ranking_cli[['cliente_nome', 'cliente_telefone', 'qtd_dias_aluguel', 'qtd_alugueis', 'qtd_malas_diferentes', 'total_faturado']].copy()
                    df_cli_view.columns = ['Cliente', 'Telefone', 'Dias de Aluguel', 'Qtd. Aluguéis', 'Malas Diferentes', 'Total (R$)']

                    st.dataframe(
                        df_cli_view.style.format({
                            'Total (R$)': 'R$ {:.2f}'
                        }).background_gradient(subset=['Dias de Aluguel'], cmap='Oranges'),
                        use_container_width=True
                    )

                    # --- Ranking por Qtd de Aluguéis (Vezes Alugado) ---
                    st.divider()
                    st.write("### 🔄 Ranking de Clientes (Por Vezes Alugado)")

                    df_ranking_vezes = df_ranking_cli.sort_values(by='qtd_alugueis', ascending=False).reset_index(drop=True)
                    df_ranking_vezes_view = df_ranking_vezes[['cliente_nome', 'cliente_telefone', 'qtd_alugueis', 'qtd_dias_aluguel', 'qtd_malas_diferentes', 'total_faturado']].copy()
                    df_ranking_vezes_view.columns = ['Cliente', 'Telefone', 'Vezes Alugado', 'Dias de Aluguel', 'Malas Diferentes', 'Total (R$)']

                    col_v1, col_v2 = st.columns(2)
                    col_v1.metric("🥇 Mais vezes", f"{df_ranking_vezes.iloc[0]['cliente_nome']}", f"{int(df_ranking_vezes.iloc[0]['qtd_alugueis'])} aluguéis")
                    col_v2.metric("💰 Faturamento", f"{df_ranking_vezes.iloc[0]['cliente_nome']}", f"R$ {df_ranking_vezes.iloc[0]['total_faturado']:,.2f}")

                    st.dataframe(
                        df_ranking_vezes_view.style.format({
                            'Total (R$)': 'R$ {:.2f}'
                        }).background_gradient(subset=['Vezes Alugado'], cmap='Purples'),
                        use_container_width=True
                    )
                else:
                    st.info("Nenhum dado de aluguel encontrado.")
            else:
                st.warning("Atualize a página para ver o ranking.")
            
            st.divider()
            
            # Gráfico Comparativo
            st.write("### Comparativo: Custo de Aquisição x Total Faturado por Mala")
            
            # Transformar dados para formato longo (tidy) para o gráfico agrupado
            df_melted = df_fin.melt(
                id_vars=['codigo', 'marca'], 
                value_vars=['custo_aquisicao', 'total_faturado'],
                var_name='Tipo', 
                value_name='Valor'
            )
            
            # Mapear nomes para legenda
            df_melted['Tipo'] = df_melted['Tipo'].map({
                'custo_aquisicao': 'Custo de Aquisição',
                'total_faturado': 'Total Faturado'
            })
            
            fig = px.bar(
                df_melted, 
                x='codigo', 
                y='Valor', 
                color='Tipo',
                barmode='group',
                hover_data=['marca'],
                title='Custo vs Faturamento por Mala',
                color_discrete_map={'Custo de Aquisição': '#EF553B', 'Total Faturado': '#00CC96'}
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Novo: Gráfico de Pizza (Faturamento por Mala)
            st.write("### 🍕 Investimento vs Retorno (Proporção)")
            
            if total_investido > 0:
                df_pie_total = pd.DataFrame({
                    'Tipo': ['Investimento (Custo)', 'Retorno (Faturamento)'],
                    'Valor': [total_investido, total_retorno]
                })
                
                fig_pizza = px.pie(
                    df_pie_total, 
                    values='Valor', 
                    names='Tipo', 
                    title='Proporção: Quanto Investi vs Quanto Ganhei',
                    hole=0.4,
                    color='Tipo',
                    color_discrete_map={'Investimento (Custo)': '#EF553B', 'Retorno (Faturamento)': '#00CC96'}
                )
                fig_pizza.update_traces(textposition='inside', textinfo='percent+label+value')
                st.plotly_chart(fig_pizza, use_container_width=True)
            else:
                st.info("Sem dados de investimento para gerar gráfico.")
            
            st.divider()
            
            # --- NOVO: Projeção de Retorno (Breakeven) ---
            st.write("### 🔮 Projeção de Retorno")
            
            if total_investido > 0:
                # Calcular média de faturamento diário (desde o primeiro aluguel até hoje)
                # Pegar a data do primeiro aluguel
                if not historico_alugueis.empty:
                    primeira_data = pd.to_datetime(historico_alugueis['data_saida'], format='%d/%m/%Y').min()
                    hoje = pd.Timestamp(date.today())
                    dias_operacao = (hoje - primeira_data).days
                    if dias_operacao < 1: dias_operacao = 1
                    
                    media_faturamento_dia = total_retorno / dias_operacao
                    
                    # Se ainda estamos no prejuízo
                    if saldo_geral < 0:
                        falta_recuperar = abs(saldo_geral)
                        if media_faturamento_dia > 0:
                            dias_para_pagar = falta_recuperar / media_faturamento_dia
                            data_estimada_pagamento = hoje + pd.Timedelta(days=dias_para_pagar)
                            
                            st.warning(f"🔴 Ainda falta recuperar **R$ {falta_recuperar:,.2f}** do investimento inicial.")
                            st.write(f"💸 Faturamento Médio Diário: **R$ {media_faturamento_dia:,.2f}**")
                            st.info(f"📅 Previsão para recuperar todo o investimento: **{data_estimada_pagamento.strftime('%d/%m/%Y')}** (em cerca de {int(dias_para_pagar)} dias)")
                        else:
                            st.warning("Ainda não há faturamento suficiente para projetar o retorno.")
                    else:
                        st.success(f"🎉 Parabéns! Você já recuperou todo o investimento e está com **R$ {saldo_geral:,.2f}** de Lucro Puro!")
                else:
                    st.info("Registre o primeiro aluguel para ver as projeções.")
            
            st.divider()
            
            # --- NOVO: Análise por Tamanho (P/M/G) ---
            st.write("### 📦 Performance por Tamanho (Investimento x Lucro)")
            
            # Agrupar dados por tamanho
            # Precisamos normalizar os tamanhos se houver "Outro", mas vamos assumir o que está no banco
            df_tamanho = df_fin.groupby('tamanho')[['custo_aquisicao', 'total_faturado']].sum().reset_index()
            df_tamanho['lucro'] = df_tamanho['total_faturado'] - df_tamanho['custo_aquisicao']
            
            # Gráfico de Barras Agrupadas por Tamanho
            df_tamanho_melted = df_tamanho.melt(
                id_vars=['tamanho'],
                value_vars=['custo_aquisicao', 'total_faturado', 'lucro'],
                var_name='Métrica',
                value_name='Valor (R$)'
            )
            
            df_tamanho_melted['Métrica'] = df_tamanho_melted['Métrica'].map({
                'custo_aquisicao': 'Investido (Compra)',
                'total_faturado': 'Faturado (Aluguel)',
                'lucro': 'Lucro/Prejuízo Líquido'
            })
            
            fig_tam = px.bar(
                df_tamanho_melted,
                x='tamanho',
                y='Valor (R$)',
                color='Métrica',
                barmode='group',
                title='Comparativo Financeiro por Tamanho de Mala',
                text_auto='.2s',
                color_discrete_map={
                    'Investido (Compra)': '#FFA500', # Laranja
                    'Faturado (Aluguel)': '#1E90FF', # Azul
                    'Lucro/Prejuízo Líquido': '#28a745' # Verde
                }
            )
            # Ajustar cor do lucro negativo para vermelho se possível, mas no Plotly simples é fixo por grupo.
            # Vamos manter fixo, mas a barra negativa vai para baixo.
            
            st.plotly_chart(fig_tam, use_container_width=True)
            
            # Tabela Resumo por Tamanho
            st.write("**Resumo Financeiro por Tamanho:**")
            st.dataframe(
                df_tamanho.style.format({
                    'custo_aquisicao': 'R$ {:.2f}',
                    'total_faturado': 'R$ {:.2f}',
                    'lucro': 'R$ {:.2f}'
                }).background_gradient(subset=['lucro'], cmap='RdYlGn'),
                use_container_width=True
            )

            st.divider()
            st.write("### Detalhamento por Mala")
            
            # Botão de Download PDF
            if not df_fin.empty:
                pdf_fin_bytes = create_pdf_analise_financeira(df_fin)
                st.download_button(
                    label="📄 Baixar Relatório Financeiro (PDF)",
                    data=pdf_fin_bytes,
                    file_name=f"relatorio_financeiro_{date.today()}.pdf",
                    mime="application/pdf"
                )
            
            # Exibir tabela com formatação condicional
            st.dataframe(
                df_fin[['codigo', 'marca', 'tamanho', 'custo_aquisicao', 'total_faturado', 'saldo', 'status_roi']].style.format({
                    'custo_aquisicao': 'R$ {:.2f}',
                    'total_faturado': 'R$ {:.2f}',
                    'saldo': 'R$ {:.2f}'
                }).background_gradient(subset=['saldo'], cmap='RdYlGn'),
                use_container_width=True
            )

    with tab_gastos:
        st.subheader("Controle de Gastos Extras e Investimentos")
        st.warning("⚠️ **ATENÇÃO:** Não registre a **COMPRA DE MALAS** aqui! O valor pago nas malas deve ser preenchido diretamente no cadastro da mala (Menu 'Cadastrar Mala'). Se você registrar aqui também, o valor será duplicado no balanço.")
        st.info("Use esta aba apenas para outros gastos: Marketing, Manutenção, Impostos, etc.")

        # --- Seção de Gestores ---
        with st.expander("👥 Gerenciar Gestores (Quem gastou?)"):
            col_ges1, col_ges2 = st.columns([1, 2])
            
            with col_ges1:
                st.write("**Cadastrar Novo Gestor**")
                nome_gestor = st.text_input("Nome do Gestor", key="novo_gestor_nome")
                if st.button("Salvar Gestor"):
                    if nome_gestor:
                        sucesso, msg = db.add_gestor(nome_gestor)
                        if sucesso:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                    else:
                        st.warning("Digite o nome do gestor.")
            
            with col_ges2:
                st.write("**Gestores Cadastrados**")
                df_gestores = db.get_gestores()
                if not df_gestores.empty:
                    # Mostrar tabela com botão de excluir
                    for index, row in df_gestores.iterrows():
                        col_list1, col_list2 = st.columns([3, 1])
                        col_list1.write(f"👤 {row['nome']}")
                        if col_list2.button("Excluir", key=f"del_gestor_{row['id']}"):
                            sucesso, msg = db.delete_gestor(row['id'])
                            if sucesso:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
                else:
                    st.info("Nenhum gestor cadastrado.")

        st.divider()
        
        # Carregar Gestores para o formulário
        df_gestores = db.get_gestores()
        opcoes_gestores = {}
        if not df_gestores.empty:
            opcoes_gestores = {row['nome']: row['id'] for _, row in df_gestores.iterrows()}
        
        # Formulário para adicionar gasto
        with st.form("form_gasto_extra"):
            st.write("#### Registrar Novo Gasto")
            col_g1, col_g2 = st.columns(2)
            data_gasto = col_g1.date_input("Data do Gasto", date.today())
            categoria = col_g2.selectbox("Categoria", ["Marketing/Propaganda", "Manutenção Geral", "Impostos", "Transporte", "Material de Escritório", "Outros"])
            
            col_g3, col_g4 = st.columns(2)
            descricao = col_g3.text_input("Descrição (Ex: Anúncio no Instagram)")
            valor_gasto = col_g4.number_input("Valor (R$)", min_value=0.0, step=10.0)
            
            # Seleção de Gestor
            gestor_id = None
            if opcoes_gestores:
                gestor_selecionado = st.selectbox("Gestor Responsável", list(opcoes_gestores.keys()))
                gestor_id = int(opcoes_gestores[gestor_selecionado])
            else:
                st.warning("⚠️ Cadastre um gestor acima para vincular ao gasto.")
            
            if st.form_submit_button("Adicionar Gasto"):
                if descricao and valor_gasto > 0:
                    if not opcoes_gestores:
                        st.error("É necessário cadastrar um gestor primeiro!")
                    else:
                        sucesso, msg = db.add_gasto_extra(data_gasto, descricao, categoria, valor_gasto, gestor_id)
                        if sucesso:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                else:
                    st.warning("Preencha a descrição e o valor.")
        
        st.divider()
        
        # --- Saldo Anterior por Data ---
        with st.expander("📅 Saldo Anterior em uma Data Específica", expanded=False):
            st.write("Consulte o saldo acumulado (investimentos + gastos) até uma data.")
            col_data1, col_data2 = st.columns([1, 2])
            data_ref_saldo = col_data1.date_input("Data de Referência", value=date.today(), key="dt_ref_saldo")
            
            df_all_malas = db.get_malas_para_gastos()
            df_all_extras = db.get_gastos_extras()
            
            lista_saldo = []
            
            # Malas com data_compra <= data_ref
            if not df_all_malas.empty:
                for _, row in df_all_malas.iterrows():
                    if pd.notna(row.get('data_compra')):
                        dt_compra = pd.to_datetime(row['data_compra']).date()
                        if dt_compra <= data_ref_saldo and pd.notna(row['valor_pago']) and row['valor_pago'] > 0:
                            gestor = row.get('gestor_nome', 'Não Informado') if pd.notna(row.get('gestor_nome')) else 'Não Informado'
                            lista_saldo.append({'Data': dt_compra, 'Descrição': f"Compra {row['codigo']} ({row.get('tamanho', '')})", 'Categoria': 'Compra de Produto', 'Gestor': gestor, 'Valor': row['valor_pago'], 'Tipo': 'Saída'})
            
            # Gastos Extras com data <= data_ref
            if not df_all_extras.empty:
                for _, row in df_all_extras.iterrows():
                    if pd.notna(row.get('data')):
                        dt_gasto = pd.to_datetime(row['data']).date()
                        if dt_gasto <= data_ref_saldo:
                            gestor = row.get('gestor_nome', 'Não Informado') if pd.notna(row.get('gestor_nome')) else 'Não Informado'
                            lista_saldo.append({'Data': dt_gasto, 'Descrição': row.get('descricao', ''), 'Categoria': row.get('categoria', 'Extra'), 'Gestor': gestor, 'Valor': row['valor'], 'Tipo': 'Saída'})
            
            if lista_saldo:
                df_saldo_ant = pd.DataFrame(lista_saldo)
                total_saldo_ant = df_saldo_ant['Valor'].sum()
                st.metric(f"Total Investido até {data_ref_saldo.strftime('%d/%m/%Y')}", f"R$ {total_saldo_ant:,.2f}")
                
                # Detalhe por gestor
                st.write("**Detalhe por Gestor:**")
                df_por_gestor_saldo = df_saldo_ant.groupby('Gestor')['Valor'].sum().reset_index()
                st.dataframe(df_por_gestor_saldo, use_container_width=True)
            else:
                st.info("Nenhum investimento ou gasto registrado até esta data.")

        # --- Últimas Movimentações do Caixa ---
        with st.expander("💰 Últimas Movimentações do Caixa (Entradas e Saídas)", expanded=False):
            df_extrato = db.get_extrato_financeiro()
            if not df_extrato.empty:
                df_extrato['data'] = pd.to_datetime(df_extrato['data'], errors='coerce')
                df_extrato = df_extrato.sort_values('data', ascending=False).head(50)
                st.dataframe(
                    df_extrato[['data', 'tipo', 'descricao', 'valor']],
                    column_config={
                        "data": "Data",
                        "tipo": "Tipo",
                        "descricao": "Descrição",
                        "valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                    },
                    use_container_width=True
                )
            else:
                st.info("Nenhuma movimentação registrada.")

        # --- Restaurar Tudo por Data ---
        with st.expander("⚠️ Restaurar Tudo (Remover Malas e Gastos por Período)", expanded=False):
            st.warning("⚠️ Use esta função para **REMOVER** malas e gastos extras cadastrados por engano em um período. Esta ação não pode ser desfeita!")
            col_r1, col_r2 = st.columns(2)
            data_inicio = col_r1.date_input("Data Início (inclusiva)", value=date.today(), key="dt_rest_inicio")
            data_fim = col_r2.date_input("Data Fim (inclusiva)", value=date.today(), key="dt_rest_fim")
            confirmar = st.checkbox("Confirmar que deseja remover estes registros permanentemente", value=False, key="chk_confirma_rest")

            if confirmar:
                registros = db.get_registros_entre_datas(data_inicio, data_fim)
                qtd_malas = len(registros['malas'])
                qtd_gastos = len(registros['gastos'])
                total_valor = sum(r['valor_pago'] or 0 for r in registros['malas']) + sum(r['valor'] or 0 for r in registros['gastos'])
                st.error(f"Isto vai remover: **{qtd_malas} malas** e **{qtd_gastos} gastos extras** (total: R$ {total_valor:,.2f})")

                col_prev1, col_prev2 = st.columns(2)
                with col_prev1:
                    if registros['malas']:
                        st.write("**Malas a remover:**")
                        df_malas_prev = pd.DataFrame(registros['malas'])
                        st.dataframe(df_malas_prev[['codigo', 'tamanho', 'cor', 'marca', 'valor_pago', 'data_compra']], use_container_width=True)
                with col_prev2:
                    if registros['gastos']:
                        st.write("**Gastos extras a remover:**")
                        df_gastos_prev = pd.DataFrame(registros['gastos'])
                        st.dataframe(df_gastos_prev[['descricao', 'categoria', 'valor', 'data']], use_container_width=True)

                if st.button("⚠️ CONFIRMAR REMOÇÃO PERMANENTE", type="primary"):
                    ok, msg = db.restaurar_tudo_entre_datas(data_inicio, data_fim)
                    if ok:
                        st.success(f"Remoção concluída! {msg}")
                        st.rerun()
                    else:
                        st.error(f"Erro: {msg}")
            else:
                st.info("Marque a caixa de confirmação acima para habilitar a remoção.")

        # --- Lixeira: Ver e Restaurar Itens Excluídos ---
        with st.expander("🗑️ Lixeira (Itens Excluídos - Restaurar)", expanded=False):
            st.write("Aqui você pode ver os itens que foram removidos e restaurá-los se necessário.")
            df_lixeira = db.get_lixeira()
            if df_lixeira.empty:
                st.info("Lixeira vazia. Nenhum item excluído.")
            else:
                st.write(f"**{len(df_lixeira)} item(ns) na lixeira**")
                for idx, row in df_lixeira.iterrows():
                    dados = row.get('dados_parsed', {})
                    col_l1, col_l2, col_l3 = st.columns([3, 1, 1])
                    with col_l1:
                        if row['tipo'] == 'Mala':
                            st.write(f"🧳 **{dados.get('codigo', 'N/A')}** - {dados.get('tamanho', '')} - {dados.get('marca', '')}")
                            st.caption(f"Valor: R$ {dados.get('valor_pago', 0):,.2f} | Excluído em: {row.get('data_exclusao', 'N/A')}")
                        else:
                            st.write(f"💸 **{dados.get('descricao', 'N/A')}** - {dados.get('categoria', '')}")
                            st.caption(f"Valor: R$ {dados.get('valor', 0):,.2f} | Excluído em: {row.get('data_exclusao', 'N/A')}")
                    with col_l2:
                        if st.button(f"♻️ Restaurar", key=f"rest_lix_{row['id']}"):
                            ok, msg = db.restaurar_da_lixeira(row['id'])
                            if ok:
                                st.success(f"✅ {msg}")
                                st.rerun()
                            else:
                                st.error(f"Erro: {msg}")
                    with col_l3:
                        if st.button(f"🗑️ Excluir Permanentemente", key=f"del_lix_{row['id']}"):
                            ok, msg = db.deletar_da_lixeira(row['id'])
                            if ok:
                                st.success(f"✅ {msg}")
                                st.rerun()
                            else:
                                st.error(f"Erro: {msg}")
                    st.divider()

        # --- Conciliação: Malas vs Gastos Extras (detectar duplicados ou faltantes) ---
        with st.expander("🔍 Conciliação de Cadastros (Malas vs Gastos Extras)", expanded=False):
            st.write("Use esta ferramenta para comparar valores entre **Cadastro de Malas** e **Gastos Extras** e detectar duplicações ou pendências.")
            col_conc1, col_conc2 = st.columns(2)
            data_conc = col_conc1.date_input("Comparar cadastros até esta data", value=date.today(), key="dt_conciliacao")

            df_malas_conc = db.get_malas_para_gastos()
            df_extras_conc = db.get_gastos_extras()

            lista_conc = []

            # Todas as compras de mala no período
            if not df_malas_conc.empty:
                for _, row in df_malas_conc.iterrows():
                    if pd.notna(row.get('data_compra')):
                        dt = pd.to_datetime(row['data_compra']).date()
                        if dt <= data_conc and pd.notna(row['valor_pago']) and row['valor_pago'] > 0:
                            lista_conc.append({'Data': dt, 'Origem': 'Cadastro de Mala', 'Descrição': f"{row['codigo']} ({row.get('tamanho', '')})", 'Gestor': row.get('gestor_nome', 'N/A'), 'Valor': row['valor_pago']})

            # Gastos extras no período
            if not df_extras_conc.empty:
                for _, row in df_extras_conc.iterrows():
                    if pd.notna(row.get('data')):
                        dt = pd.to_datetime(row['data']).date()
                        if dt <= data_conc:
                            lista_conc.append({'Data': dt, 'Origem': 'Gasto Extra', 'Descrição': row.get('descricao', ''), 'Gestor': row.get('gestor_nome', 'N/A'), 'Valor': row['valor']})

            if lista_conc:
                df_conc = pd.DataFrame(lista_conc)
                df_conc = df_conc.sort_values('Data', ascending=False)

                total_malas = df_conc[df_conc['Origem'] == 'Cadastro de Mala']['Valor'].sum()
                total_extras = df_conc[df_conc['Origem'] == 'Gasto Extra']['Valor'].sum()

                col_c1, col_c2, col_c3 = st.columns(3)
                col_c1.metric("Total Malas Cadastradas", f"R$ {total_malas:,.2f}")
                col_c2.metric("Total Gastos Extras", f"R$ {total_extras:,.2f}")
                col_c3.metric("Diferença (Malas - Extras)", f"R$ {total_malas - total_extras:,.2f}")

                st.write("**Registros encontrados (ordenados por data):**")
                st.dataframe(
                    df_conc,
                    column_config={
                        "Data": "Data",
                        "Origem": "Origem",
                        "Descrição": "Descrição",
                        "Gestor": "Gestor",
                        "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                    },
                    use_container_width=True
                )

                # Alertas
                st.divider()
                st.write("**⚠️ Possíveis problemas detectados:**")

                # 1. Malas sem correspondente em gastos (alto valor de mala sem gasto extra)
                df_malas_only = df_conc[df_conc['Origem'] == 'Cadastro de Mala']
                df_extras_only = df_conc[df_conc['Origem'] == 'Gasto Extra']
                df_extras_nomes = df_extras_only['Descrição'].str.lower().tolist()

                problemas = []
                for _, row in df_malas_only.iterrows():
                    # Verificar se existe gasto extra similar (mesmo valor no mesmo dia)
                    matching = df_extras_only[(df_extras_only['Data'] == row['Data']) & (df_extras_only['Valor'] == row['Valor'])]
                    if matching.empty:
                        problemas.append(f"⚠️ Mala **{row['Descrição']}** (R$ {row['Valor']:,.2f}) em {row['Data']} — sem gasto extra correspondente")

                if problemas:
                    for p in problemas:
                        st.warning(p)
                else:
                    st.success("✅ Nenhuma inconsistência obvious detectada. Verifique manualmente os valores acima.")

                st.info("💡 **Dica:** Se cadastrou uma mala e também um gasto extra com o mesmo valor, o valor aparece DUAS VEZES no total (duplicado). Delete o gasto extra se for o caso.")
            else:
                st.info("Nenhum registro encontrado até esta data.")

        # Listagem de Gastos e Gerenciamento
        st.write("#### Visão Geral de Gastos (Malas + Extras)")
        
        # Carregar dados de AMBAS as fontes
        df_gastos_extras = db.get_gastos_extras()
        df_malas_gastos = db.get_malas_para_gastos()
        
        # Preparar dados unificados para Gráficos e Métricas
        lista_total = []
        
        # 1. Adicionar Extras
        if not df_gastos_extras.empty:
            for _, row in df_gastos_extras.iterrows():
                lista_total.append({
                    'Gestor': row['gestor_nome'] if pd.notna(row['gestor_nome']) else "Não Informado",
                    'Categoria': row['categoria'],
                    'Valor': row['valor'],
                    'Tipo': 'Extra'
                })
        
        # 2. Adicionar Malas (todas as compras, independente do tipo)
        if not df_malas_gastos.empty:
            for _, row in df_malas_gastos.iterrows():
                if pd.notna(row['valor_pago']) and row['valor_pago'] > 0:
                    gestor = row['gestor_nome'] if 'gestor_nome' in row and pd.notna(row['gestor_nome']) else "Não Informado"
                    lista_total.append({
                        'Gestor': gestor,
                        'Categoria': 'Compra de Produto',
                        'Valor': row['valor_pago'],
                        'Tipo': 'Mala'
                    })
        
        df_total_unificado = pd.DataFrame(lista_total)

        st.write(f"**Debug:** Total unificado com {len(df_total_unificado)} registros | df_malas_gastos: {len(df_malas_gastos)} | df_gastos_extras: {len(df_gastos_extras)}")
        if not df_total_unificado.empty:
            with st.expander("🔍 Ver dados crus (Debug)", expanded=False):
                st.dataframe(df_total_unificado, use_container_width=True)
        elif len(df_malas_gastos) == 0 and len(df_gastos_extras) == 0:
            st.info("Nenhum gasto registrado ainda.")

        if not df_total_unificado.empty:
            # Filtro Global
            filtro_gestor = "Todos"
            if not df_gestores.empty:
                col_filt1, col_filt2 = st.columns([1, 2])
                filtro_gestor = col_filt1.selectbox("Filtrar visualização por Gestor", ["Todos"] + list(opcoes_gestores.keys()))
            
            # Aplicar filtro
            df_exibicao_grafico = df_total_unificado.copy()
            if filtro_gestor != "Todos":
                df_exibicao_grafico = df_exibicao_grafico[df_exibicao_grafico['Gestor'] == filtro_gestor]
            
            # Métricas Unificadas
            total_geral_gestor = df_exibicao_grafico['Valor'].sum()
            
            # Tentar calcular do mês (precisaria da data na mala, mas não temos data de compra da mala, só cadastro. Vamos assumir total geral por enquanto ou usar data de hoje para simplificar a visualização do mês se fosse critico, mas melhor mostrar Total Geral)
            
            st.metric(f"Total Investido/Gasto ({filtro_gestor})", f"R$ {total_geral_gestor:,.2f}", help="Soma de Compras de Malas + Gastos Extras")
            
            # --- Gráficos Unificados ---
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                # Pizza por Categoria (Incluindo "Compra de Mala")
                df_por_cat = df_exibicao_grafico.groupby('Categoria')['Valor'].sum().reset_index()
                fig_cat = px.pie(df_por_cat, values='Valor', names='Categoria', title='Distribuição de Gastos', hole=0.4)
                st.plotly_chart(fig_cat, use_container_width=True)
                
            with col_chart2:
                # Se não filtrou gestor, mostrar Pizza de Gestores. Se filtrou, mostrar Tipo (Mala vs Extra)
                if filtro_gestor == "Todos":
                    df_por_ges = df_exibicao_grafico.groupby('Gestor')['Valor'].sum().reset_index()
                    fig_ges = px.pie(df_por_ges, values='Valor', names='Gestor', title='Quem gastou mais? (Total)', hole=0.4)
                    st.plotly_chart(fig_ges, use_container_width=True)
                else:
                    df_por_tipo = df_exibicao_grafico.groupby('Tipo')['Valor'].sum().reset_index()
                    fig_tipo = px.pie(df_por_tipo, values='Valor', names='Tipo', title='Malas vs Extras', hole=0.4)
                    st.plotly_chart(fig_tipo, use_container_width=True)
            
            st.divider()

        # --- Gerenciamento (Mantido Focado em Extras, mas com aviso) ---
        st.write("#### Gerenciar Gastos Extras (Lançamentos Manuais)")
        st.info("Abaixo você gerencia apenas os **Gastos Extras**. Para alterar valores de Malas, vá em 'Cadastrar Mala' > 'Gerenciar Estoque'.")
        
        df_gastos = db.get_gastos_extras() # Recarregar puro para a tabela
        
        if not df_gastos.empty:
             # Filtro para a tabela de extras (reaproveitar o selecionado acima se quiser, ou independente)
             # Vamos reaproveitar a lógica visual
             df_exibicao_tabela = df_gastos.copy()
             if filtro_gestor != "Todos":
                df_exibicao_tabela = df_exibicao_tabela[df_exibicao_tabela['gestor_nome'] == filtro_gestor]

             # Abas de Gerenciamento
             tab_lista, tab_editar, tab_excluir = st.tabs(["📋 Lista de Extras", "✏️ Editar Extra", "🗑️ Excluir Extra"])
             
             with tab_lista:
                st.dataframe(
                    df_exibicao_tabela[['id', 'data', 'gestor_nome', 'categoria', 'descricao', 'valor']].rename(columns={'gestor_nome': 'Gestor'}).style.format({'valor': 'R$ {:.2f}'}),
                    use_container_width=True,
                    hide_index=True
                )
             
             with tab_editar:
                lista_opcoes_edit = df_gastos.apply(lambda x: f"ID {x['id']} | {x['data']} | R$ {x['valor']:.2f} - {x['descricao']}", axis=1)
                escolha_edit = st.selectbox("Selecione o Gasto Extra para Editar", options=lista_opcoes_edit)
                
                if escolha_edit:
                    id_edit = int(escolha_edit.split(' | ')[0].replace('ID ', ''))
                    gasto_selecionado = df_gastos[df_gastos['id'] == id_edit].iloc[0]
                    
                    with st.form(f"form_edit_gasto_{id_edit}"):
                        col_e1, col_e2 = st.columns(2)
                        data_atual_edit = pd.to_datetime(gasto_selecionado['data']).date()
                        nova_data = col_e1.date_input("Data", value=data_atual_edit)
                        
                        cats = ["Marketing/Propaganda", "Manutenção Geral", "Impostos", "Transporte", "Material de Escritório", "Outros"]
                        idx_cat = cats.index(gasto_selecionado['categoria']) if gasto_selecionado['categoria'] in cats else 0
                        nova_categoria = col_e2.selectbox("Categoria", cats, index=idx_cat)
                        
                        col_e3, col_e4 = st.columns(2)
                        nova_descricao = col_e3.text_input("Descrição", value=gasto_selecionado['descricao'])
                        novo_valor = col_e4.number_input("Valor (R$)", min_value=0.0, step=10.0, value=float(gasto_selecionado['valor']))
                        
                        # Gestor
                        gestor_atual_id = gasto_selecionado['gestor_id'] if pd.notna(gasto_selecionado['gestor_id']) else None
                        idx_gestor = 0
                        
                        if gestor_atual_id:
                            for i, (k, v) in enumerate(opcoes_gestores.items()):
                                if v == gestor_atual_id:
                                    idx_gestor = i
                                    break
                        
                        novo_gestor_nome = st.selectbox("Gestor Responsável", list(opcoes_gestores.keys()), index=idx_gestor)
                        novo_gestor_id = opcoes_gestores[novo_gestor_nome] if novo_gestor_nome else None
                        
                        if st.form_submit_button("Salvar Alterações"):
                            sucesso, msg = db.update_gasto_extra(id_edit, nova_data, nova_descricao, nova_categoria, novo_valor, novo_gestor_id)
                            if sucesso:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

             with tab_excluir:
                st.warning("Atenção: A exclusão é permanente.")
                lista_opcoes_del = df_gastos.apply(lambda x: f"ID {x['id']} | {x['data']} | R$ {x['valor']:.2f} - {x['descricao']}", axis=1)
                escolha_del = st.selectbox("Selecione o Gasto para Excluir", options=lista_opcoes_del, key="sel_del_gasto")
                
                if st.button("🗑️ Confirmar Exclusão", type="primary"):
                    if escolha_del:
                        id_del = int(escolha_del.split(' | ')[0].replace('ID ', ''))
                        sucesso, msg = db.delete_gasto_extra(id_del)
                        if sucesso:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

        else:
            st.info("Nenhum gasto extra registrado.")

    with tab_vendas:
        st.subheader("🛒 Vendas de Malas (Novas e Usadas)")
        st.success(
            "✅ **Bloco informativo e separado:** O resultado de vendas de malas **NÃO entra no Saldo em Caixa** "
            "da aba 'Balanço Geral do Negócio'. O Saldo em Caixa continua considerando apenas **aluguéis - "
            "gastos extras - reinvestimentos do caixa**. Aqui você acompanha o desempenho de vendas em um "
            "lugar próprio, sem misturar com a operação de locação."
        )

        resumo_vendas = db.get_resumo_vendas()
        total_vendido = float(resumo_vendas.get("total_vendido", 0) or 0)
        total_custo = float(resumo_vendas.get("total_custo", 0) or 0)
        total_lucro = float(resumo_vendas.get("total_lucro", 0) or 0)
        total_vendas = int(resumo_vendas.get("total_vendas", 0) or 0)

        col_v1, col_v2, col_v3, col_v4 = st.columns(4)
        col_v1.metric("📦 Vendas Registradas", f"{total_vendas}", help="Quantidade total de malas vendidas (novas + usadas).")
        col_v2.metric("💰 Faturado em Vendas", f"R$ {total_vendido:,.2f}", help="Soma do valor de venda de todas as malas vendidas.")
        col_v3.metric("💵 Custo de Aquisição", f"R$ {total_custo:,.2f}", help="Soma do custo de aquisição das malas vendidas.")
        col_v4.metric("📈 Lucro de Vendas", f"R$ {total_lucro:,.2f}", help="Faturado - Custo de aquisição (somente vendas, sem misturar com o caixa).")

        margem_lucro = (total_lucro / total_vendido * 100) if total_vendido > 0 else 0.0
        st.write(
            f"📊 **Margem de Lucro nas Vendas:** **{margem_lucro:.1f}%** "
            f"(somente vendas - independente do Saldo em Caixa da locação)."
        )
        st.progress(min(max(margem_lucro / 100, 0.0), 1.0))

        st.divider()

        st.markdown("### 📈 Faturamento Mensal de Vendas")
        df_vendas_mensal = db.get_vendas_mensal()
        if not df_vendas_mensal.empty:
            df_vendas_mensal["mes_formatado"] = pd.to_datetime(df_vendas_mensal["mes_ano"]).dt.strftime("%b/%y")
            fig_vendas = px.bar(
                df_vendas_mensal,
                x="mes_formatado",
                y=["total_vendas", "total_lucro"],
                barmode="group",
                title="Vendas por mês (Faturado e Lucro)",
                labels={"value": "R$", "mes_formatado": "Mês", "variable": "Indicador"},
                color_discrete_map={"total_vendas": "#1E90FF", "total_lucro": "#28a745"},
            )
            fig_vendas.update_traces(texttemplate="R$ %{y:,.2f}", textposition="outside")
            fig_vendas.update_layout(height=400, hovermode="x unified")
            st.plotly_chart(fig_vendas, use_container_width=True)
        else:
            st.info("Nenhuma venda registrada até o momento. Cadastre uma venda na aba '🛒 Vender Mala'.")

        st.divider()

        st.markdown("### 📋 Vendas Recentes")
        df_vendas_rec = db.get_vendas_malas()
        if df_vendas_rec is None or df_vendas_rec.empty:
            st.info("Nenhuma venda cadastrada. Use a aba '🛒 Vender Mala' para registrar a primeira venda.")
        else:
            df_vendas_exib = df_vendas_rec[[
                "data_venda", "mala_codigo", "mala_tamanho", "tipo_mala",
                "cliente_nome", "valor_venda", "custo_aquisicao",
                "forma_pagamento", "observacao"
            ]].copy()
            df_vendas_exib["lucro"] = df_vendas_exib["valor_venda"] - df_vendas_exib["custo_aquisicao"]
            df_vendas_exib.columns = [
                "Data", "Mala", "Tamanho", "Tipo", "Cliente",
                "Valor Venda (R$)", "Custo (R$)", "Pagamento", "Observação", "Lucro (R$)"
            ]
            df_vendas_exib["Data"] = pd.to_datetime(df_vendas_exib["Data"]).dt.strftime("%d/%m/%Y")
            st.dataframe(
                df_vendas_exib.style.format({
                    "Valor Venda (R$)": "R$ {:,.2f}",
                    "Custo (R$)": "R$ {:,.2f}",
                    "Lucro (R$)": "R$ {:,.2f}",
                }),
                use_container_width=True,
                hide_index=True,
            )

        st.divider()
        st.info(
            "ℹ️ **Lembrete:** O resultado desta aba é **meramente informativo**. "
            "O **Saldo em Caixa** exibido no 'Balanço Geral do Negócio' continua sendo "
            "**Faturamento de Aluguéis - Saídas do Caixa (Gastos Extras + Reinvestimentos)**. "
            "Vendas não impactam esse saldo."
        )

    with tab_usuarios:
        st.subheader("👥 Gerenciamento de Usuários")
        st.caption("Crie novos usuários, troque senhas e ative/desative acessos. Apenas administradores gerenciam usuários.")

        df_usuarios = db.listar_usuarios()
        st.markdown("### Usuários cadastrados")
        if df_usuarios.empty:
            st.info("Nenhum usuário cadastrado.")
        else:
            df_show = df_usuarios.copy()
            df_show["ativo"] = df_show["ativo"].map({1: "✅ Sim", 0: "❌ Não"})
            df_show.columns = ["ID", "Email", "Nome", "Role", "Ativo", "Criado em"]
            st.dataframe(df_show, use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("### ➕ Adicionar novo usuário")
        with st.form("form_add_usuario", clear_on_submit=True):
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                novo_nome = st.text_input("Nome completo")
                novo_email = st.text_input("Email (será usado para login)")
            with col_u2:
                nova_senha = st.text_input("Senha (mín. 6 caracteres)", type="password")
                novo_role = st.selectbox("Perfil", ["socio", "admin"], help="Sócio tem acesso limitado; Admin tem acesso total.")
            submitted_user = st.form_submit_button("Criar Usuário", use_container_width=True)
            if submitted_user:
                if not novo_nome or not novo_email or not nova_senha:
                    st.error("Preencha todos os campos.")
                elif len(nova_senha) < 6:
                    st.error("A senha deve ter no mínimo 6 caracteres.")
                else:
                    ok_u, err_u = db.add_usuario(novo_email, novo_nome, nova_senha, novo_role)
                    if ok_u:
                        st.success(f"Usuário {novo_email} criado com perfil {novo_role}.")
                        st.rerun()
                    else:
                        st.error(f"Erro: {err_u}")

        st.divider()
        st.markdown("### 🔑 Trocar senha / Ativar-Desativar")
        if not df_usuarios.empty:
            opcoes_users = [f"{row['nome']} ({row['email']})" for _, row in df_usuarios.iterrows()]
            user_selecionado = st.selectbox("Selecione o usuário", opcoes_users, key="user_sel_admin")
            if user_selecionado:
                email_user = user_selecionado.split("(")[-1].rstrip(")")
                row_user = df_usuarios[df_usuarios["email"] == email_user].iloc[0]
                uid_user = int(row_user["id"])

                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    with st.form("form_trocar_senha"):
                        nova_senha_user = st.text_input("Nova senha", type="password", key="nova_senha_admin")
                        submit_senha = st.form_submit_button("Trocar Senha", use_container_width=True)
                        if submit_senha:
                            if len(nova_senha_user) < 6:
                                st.error("Mínimo 6 caracteres.")
                            else:
                                ok_s, err_s = db.update_usuario_senha(uid_user, nova_senha_user)
                                if ok_s:
                                    st.success("Senha atualizada.")
                                else:
                                    st.error(f"Erro: {err_s}")

                with col_a2:
                    ativo_atual = int(row_user["ativo"])
                    novo_ativo = not ativo_atual
                    label_btn = "❌ Desativar" if ativo_atual else "✅ Ativar"
                    if st.button(label_btn, use_container_width=True, key="btn_toggle_user"):
                        ok_t, err_t = db.toggle_usuario_ativo(uid_user, novo_ativo)
                        if ok_t:
                            st.success("Status alterado.")
                            st.rerun()
                        else:
                            st.error(f"Erro: {err_t}")

# --- CONTRATO DE ALUGUEL ---
elif st.session_state.page == "Contrato de Aluguel":
    st.subheader("Gerar Contrato de Locação")
    
    st.info("Aqui você pode gerar um contrato preenchido automaticamente. Selecione um cliente para incluir todas as malas dele no mesmo contrato.")
    
    alugueis = db.get_alugueis_ativos()
    
    # Criar dicionário para seleção agrupado por cliente
    if not alugueis.empty:
        # Obter lista de clientes únicos com aluguéis ativos
        clientes_ativos = alugueis[['cliente_id', 'cliente_nome']].drop_duplicates()
        opcoes_cliente = {f"{row['cliente_nome']}": row['cliente_id'] for _, row in clientes_ativos.iterrows()}
        lista_opcoes = ["Selecione um cliente..."] + list(opcoes_cliente.keys())
    else:
        opcoes_cliente = {}
        lista_opcoes = ["Nenhum aluguel ativo encontrado"]
    
    col_sel1, col_sel2 = st.columns([2, 1])
    cliente_selecionado_nome = col_sel1.selectbox("Selecione o Cliente:", lista_opcoes)
    
    # Texto Padrão com Placeholders (VERSÃO RESUMIDA E FOCADA)
    texto_padrao = """CONTRATO DE LOCAÇÃO DE MALAS

LOCADOR(A): MalaExpress, CNPJ sob nº 23.037.478/0001-91, Votorantim, SP.
LOCATÁRIO(A): {cliente_nome}, CPF: {cliente_doc}.
Endereço: {cliente_endereco} - {cliente_cidade} - CEP: {cliente_cep}.
Telefone: {cliente_telefone}.

1. DO OBJETO
O presente contrato tem por objeto a locação das seguintes malas/bagagens:
{detalhes_malas}

Destino Declarado: {destino_viagem}

2. DO PRAZO
Início: {data_saida} | Término: {data_retorno} (Total: {dias_locacao} dias).
O atraso na devolução acarretará multa de R$ 5,00 por dia.

3. DO VALOR
Total: R$ {valor_total} (Sinal: R$ {valor_sinal} | Restante: R$ {valor_restante}).

4. DAS RESPONSABILIDADES DO LOCATÁRIO
4.1. O LOCATÁRIO se compromete a devolver a(s) mala(s) nas mesmas condições de uso, conservação e limpeza em que recebeu.
4.2. Em caso de perda, roubo, furto ou danos irreparáveis, o LOCATÁRIO deverá indenizar o LOCADOR no valor de mercado dos bens, totalizando R$ {valor_indenizacao} (sendo R$ 200,00 por mala P, R$ 300,00 por mala M, R$ 400,00 por mala G e R$ 100,00 por frasqueira).
4.3. É estritamente PROIBIDO o uso da mala para transporte de substâncias ilícitas, armas, produtos perigosos ou quaisquer itens vedados por lei. O LOCATÁRIO assume total e exclusiva responsabilidade civil e criminal pelo conteúdo transportado.

5. DA ISENÇÃO DE RESPONSABILIDADE DO LOCADOR
5.1. O LOCADOR não se responsabiliza pelo conteúdo da mala, sendo a guarda e segurança dos pertences de total responsabilidade do LOCATÁRIO.
5.2. O LOCADOR não se responsabiliza por objetos deixados no interior da mala após a devolução.

6. DO FORO
Fica eleito o foro de Sorocaba, SP.

Votorantim, SP {data_hoje}.



___________________________________                         ___________________________________
MalaExpress (Locador)                                       {cliente_nome} (Locatário)"""

    texto_para_editor = texto_padrao

    if cliente_selecionado_nome != "Selecione um cliente..." and cliente_selecionado_nome != "Nenhum aluguel ativo encontrado":
        cliente_id_sel = opcoes_cliente[cliente_selecionado_nome]
        
        # Filtrar todos os aluguéis desse cliente
        alugueis_cliente = alugueis[alugueis['cliente_id'] == cliente_id_sel]
        
        if not alugueis_cliente.empty:
            try:
                # Dados do Cliente (pegar do primeiro registro)
                primeiro = alugueis_cliente.iloc[0]
                c_nome = primeiro['cliente_nome'] if primeiro['cliente_nome'] else "________________"
                c_doc = primeiro.get('cliente_doc') if primeiro.get('cliente_doc') else "________________"
                c_cep = primeiro.get('cliente_cep') if primeiro.get('cliente_cep') else "________________"
                c_end = primeiro.get('cliente_endereco') if primeiro.get('cliente_endereco') else "________________"
                c_cid = primeiro.get('cliente_cidade') if primeiro.get('cliente_cidade') else "________________"
                c_tel = primeiro.get('cliente_telefone') if primeiro.get('cliente_telefone') else "________________"
                
                # Datas (assumindo que todas as malas saem/voltam juntas ou pegar o intervalo maior)
                # Vamos pegar a menor data de saída e a maior data de retorno
                dt_saida_min = pd.to_datetime(alugueis_cliente['data_saida']).min()
                dt_retorno_max = pd.to_datetime(alugueis_cliente['data_prevista_retorno']).max()
                
                dt_saida_str = dt_saida_min.strftime('%d/%m/%Y')
                dt_retorno_str = dt_retorno_max.strftime('%d/%m/%Y')
                
                dias_locacao = (dt_retorno_max - dt_saida_min).days
                if dias_locacao < 1: dias_locacao = 1
                
                # Valores Totais
                val_aluguel_total = alugueis_cliente['valor'].sum()
                val_taxa_total = alugueis_cliente['taxa_entrega'].sum()
                val_sinal_total = alugueis_cliente['valor_sinal'].sum()
                val_acessorios_total = alugueis_cliente['valor_acessorios'].sum() if 'valor_acessorios' in alugueis_cliente.columns else 0.0
                
                total_geral = val_aluguel_total + val_taxa_total + val_acessorios_total
                restante_geral = total_geral - val_sinal_total
                
                # Calcular totais e Indenização
                total_itens = len(alugueis_cliente)
                qtd_frasqueiras = 0
                qtd_p = 0
                qtd_m = 0
                qtd_g = 0
                
                detalhes_malas_str = ""
                destinos_lista = []
                
                for idx, row in alugueis_cliente.iterrows():
                    m_tam = row['tamanho'] if row['tamanho'] else ""
                    m_marca = row['marca'] if row['marca'] else ""
                    
                    # Coletar destino
                    if 'destino' in row and pd.notna(row['destino']) and row['destino']:
                        destinos_lista.append(row['destino'])
                    
                    is_frasqueira = 'frasqueira' in m_tam.lower() or 'frasqueira' in m_marca.lower()
                    
                    if is_frasqueira:
                        qtd_frasqueiras += 1
                        tipo_str = "Tipo: Frasqueira (Tamanho Único)"
                    else:
                        if m_tam == "P":
                            qtd_p += 1
                            x_G, x_M, x_P = "   ", "   ", " x "
                        elif m_tam == "M":
                            qtd_m += 1
                            x_G, x_M, x_P = "   ", " x ", "   "
                        elif m_tam == "G":
                            qtd_g += 1
                            x_G, x_M, x_P = " x ", "   ", "   "
                        else:
                            # Se for outro tamanho ou vazio, contar como P por segurança ou ignorar na soma especifica?
                            # Vamos assumir que se não for P, M, G, pode ser tratado como P ou M.
                            # Mas para indenização vamos usar a lógica estrita.
                            x_G, x_M, x_P = "   ", "   ", "   "
                            
                        tipo_str = f"Tipo: [ ({x_G})G ({x_M})M ({x_P})P ]"
                    
                    val_acess = row.get('valor_acessorios', 0.0)
                    str_acess = row.get('acessorios', 'Nenhum') if pd.notna(row.get('acessorios')) and row.get('acessorios') else 'Nenhum'
                    if val_acess > 0:
                        str_acess += f" (R$ {val_acess:.2f})"
                        
                    bloco_mala = f"""
--- ITEM {idx+1} ---
Mala: {row['mala_codigo']} - {row['marca']}
Cor: {row.get('mala_cor', '')}
{tipo_str}
Características: {m_tam} - {row['mala_codigo']}
Acessórios: {str_acess}
"""
                    detalhes_malas_str += bloco_mala

                # Formatar Destino
                destino_final = ", ".join(list(set(destinos_lista))) if destinos_lista else "__________________________"

                qtd_malas = total_itens - qtd_frasqueiras
                
                # Calcular Valor Indenização Total
                # P: 200, M: 300, G: 400, Frasqueira: 100
                valor_indenizacao_total = (qtd_p * 200) + (qtd_m * 300) + (qtd_g * 400) + (qtd_frasqueiras * 100)
                
                # Adicionar resumo de quantidades no início
                resumo_str = f"""
Frasqueira: [ {qtd_frasqueiras} ]
Quantidade de Malas: [ {qtd_malas} ] (P:{qtd_p}, M:{qtd_m}, G:{qtd_g})
"""
                detalhes_malas_str = resumo_str + detalhes_malas_str
                
                # Substituir no texto
                texto_para_editor = texto_padrao.format(
                    cliente_nome=c_nome,
                    cliente_doc=c_doc,
                    cliente_cep=c_cep,
                    cliente_endereco=c_end,
                    cliente_cidade=c_cid,
                    cliente_telefone=c_tel,
                    detalhes_malas=detalhes_malas_str,
                    destino_viagem=destino_final,
                    data_saida=dt_saida_str,
                    data_retorno=dt_retorno_str,
                    dias_locacao=dias_locacao,
                    valor_total=f"{total_geral:.2f}",
                    valor_sinal=f"{val_sinal_total:.2f}",
                    valor_restante=f"{restante_geral:.2f}",
                    valor_indenizacao=f"{valor_indenizacao_total:.2f}",
                    data_hoje=date.today().strftime('%d/%m/%Y')
                )
            except Exception as e:
                st.error(f"Erro ao preencher dados automaticamente: {e}")
            
    # Se não selecionou nada, deixar os placeholders visíveis ou limpar?
    # Melhor deixar placeholders mas sem chaves para não dar erro no format se o usuário tentar editar
    if cliente_selecionado_nome == "Selecione um cliente...":
         # Limpar chaves para exibir como exemplo
         texto_para_editor = texto_para_editor.replace("{", "[").replace("}", "]")

    st.write("🔽 **Edite o texto abaixo se necessário (ou cole seu próprio contrato):**")
    texto_final = st.text_area("Texto do Contrato", value=texto_para_editor, height=500)
    
    if st.button("📄 Gerar PDF do Contrato", type="primary"):
        pdf_bytes = create_pdf_contrato(texto_final)
        st.success("PDF Gerado com sucesso!")
        st.download_button(
            label="⬇️ Baixar Contrato em PDF",
            data=pdf_bytes,
            file_name=f"contrato_{date.today()}.pdf",
            mime="application/pdf"
        )

# --- ACESSO MOBILE ---
elif st.session_state.page == "📱 Acesso Mobile":
    st.subheader("📱 Conectar via Celular (Internet)")
    
    st.info("Esta opção permite acessar o sistema mesmo usando 4G/5G, fora de casa.")
    
    # Iniciar Ngrok
    public_url = start_ngrok()
    
    if public_url:
        st.success("Túnel de acesso remoto ATIVO!")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"### 🔗 Link de Acesso (Mundial)")
            st.code(public_url, language="text")
            st.info("Envie este link para seu WhatsApp e abra no celular.")
            st.warning("Nota: Se aparecer uma tela de aviso do Ngrok, clique em 'Visit Site'.")
            
        with col2:
            st.markdown(f"### 📷 QR Code")
            
            # Gerar QR Code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(public_url)
            qr.make(fit=True)
            
            img_qr = qr.make_image(fill_color="black", back_color="white")
            
            # Converter para bytes para exibir no Streamlit
            buf = BytesIO()
            img_qr.save(buf)
            st.image(buf, caption="Escaneie para acessar via Internet", width=300)
    else:
        st.error("Não foi possível iniciar o túnel remoto automaticamente.")
        st.markdown("""
        **Possível solução:**
        1. Crie uma conta grátis em [ngrok.com](https://dashboard.ngrok.com/signup)
        2. Copie seu Authtoken
        3. No terminal, digite: `ngrok config add-authtoken SEU_TOKEN_AQUI`
        4. Reinicie o sistema.
        """)
    
    st.divider()
    
    # Opção Local (Backup)
    with st.expander("Ver opção de acesso apenas via Wi-Fi Local (Backup)"):
        ip_local = get_local_ip()
        url_local = f"http://{ip_local}:8501"
        st.write(f"Link Local: `{url_local}`")

    st.markdown("### 💻 Acesso no PC")
    st.write("Para facilitar o acesso neste computador:")
    st.write("1. Verifique se o arquivo `INICIAR_SISTEMA` está na sua Área de Trabalho.")
    st.write("2. Se não estiver, vá até a pasta do projeto e crie um atalho (Botão direito -> Enviar para -> Área de Trabalho).")
    st.write("3. Basta clicar duas vezes nesse ícone sempre que quiser usar o sistema.")

# --- VENDER MALA ---
elif st.session_state.page == "🛒 Vender Mala":
    st.subheader("🛒 Venda de Malas (Novas e Usadas)")

    st.info(
        "💡 As vendas são registradas em um bloco separado do Saldo em Caixa da locação. "
        "O caixa da locação continua mostrando apenas aluguéis, gastos extras e reinvestimentos do caixa."
    )

    tab_nova, tab_consulta = st.tabs(["➕ Registrar Venda", "📋 Histórico de Vendas"])

    with tab_nova:
        st.markdown("### Registrar nova venda")
        st.write("Defina a mala, o custo e a forma de calcular o valor de venda. Você pode usar uma **porcentagem sobre o custo** ou digitar o **valor manual** — o sistema aceita o valor que você colocar.")

        # --- Bloco FORA do form para permitir recálculo dinâmico ---
        col_a, col_b = st.columns(2)
        with col_a:
            tipo_mala = st.selectbox("Tipo da Mala", ["Nova", "Usada"], key="venda_tipo")
            mala_opcao = st.radio(
                "Mala do estoque?",
                ["Usar mala do cadastro", "Mala avulsa (sem cadastro)"],
                horizontal=True,
                key="venda_origem",
            )

            mala_id = None
            mala_codigo = ""
            mala_tamanho = ""
            custo_aquisicao = 0.0
            custo_conhecido = False

            if mala_opcao == "Usar mala do cadastro":
                try:
                    df_malas = db.get_malas()
                except Exception:
                    df_malas = pd.DataFrame()
                df_disponiveis = df_malas[df_malas["status"].isin(["Disponível", "Quebrada"])] if not df_malas.empty else df_malas
                if df_disponiveis.empty:
                    st.warning("Nenhuma mala disponível para venda no cadastro. Cadastre uma mala ou use a opção 'Mala avulsa'.")
                    mala_escolhida = None
                else:
                    opcoes = [f"{row['codigo']} - {row['tamanho']} - {row.get('marca', '')}" for _, row in df_disponiveis.iterrows()]
                    mala_escolhida = st.selectbox("Mala", opcoes, key="venda_mala_select")
                    if mala_escolhida:
                        codigo = mala_escolhida.split(" - ")[0]
                        linha = df_disponiveis[df_disponiveis["codigo"] == codigo]
                        if not linha.empty:
                            row = linha.iloc[0]
                            mala_id = int(row["id"])
                            mala_codigo = str(row["codigo"])
                            mala_tamanho = str(row["tamanho"])
                            custo_aquisicao = float(row.get("valor_pago") or 0)
                            custo_conhecido = True
                            st.info(f"💰 Custo de aquisição (valor pago) registrado no cadastro: **R$ {custo_aquisicao:,.2f}**")
            else:
                mala_codigo = st.text_input("Código / referência da mala", key="venda_mala_codigo")
                mala_tamanho = st.text_input("Tamanho (ex: P, M, G)", key="venda_mala_tamanho")
                custo_aquisicao = st.number_input(
                    "Custo de aquisição (R$)",
                    min_value=0.0,
                    step=10.0,
                    value=0.0,
                    key="venda_mala_custo",
                )
                custo_conhecido = True

        with col_b:
            # --- Cálculo de valor de venda ---
            st.markdown("#### 💲 Valor de venda")
            modo_valor = st.radio(
                "Como definir o valor de venda?",
                ["Porcentagem sobre o custo", "Valor manual"],
                horizontal=True,
                key="venda_modo_valor",
            )

            if modo_valor == "Porcentagem sobre o custo" and custo_conhecido:
                percentual = st.number_input(
                    "Porcentagem de lucro sobre o custo (%)",
                    min_value=0.0,
                    step=5.0,
                    value=50.0,
                    key="venda_percentual",
                    help="Ex: 50% sobre o custo. Custo R$ 200 + 50% = R$ 300.",
                )
                valor_calculado = custo_aquisicao * (1 + percentual / 100.0)
                st.success(f"📐 Cálculo: R$ {custo_aquisicao:,.2f} × (1 + {percentual:.1f}%) = **R$ {valor_calculado:,.2f}**")
                st.caption("Você pode ajustar o valor final abaixo se quiser.")
                valor_venda = st.number_input(
                    "Valor final de venda (R$)",
                    min_value=0.0,
                    step=10.0,
                    value=float(round(valor_calculado, 2)),
                    key="venda_valor",
                )
            else:
                if modo_valor == "Porcentagem sobre o custo" and not custo_conhecido:
                    st.warning("Selecione primeiro uma mala do cadastro (ou preencha o custo) para usar a porcentagem.")
                valor_venda = st.number_input(
                    "Valor de venda (R$)",
                    min_value=0.0,
                    step=50.0,
                    value=0.0,
                    key="venda_valor",
                )

            # Mostrar lucro estimado
            if custo_conhecido and valor_venda > 0:
                lucro_estimado = valor_venda - custo_aquisicao
                margem = (lucro_estimado / valor_venda * 100) if valor_venda > 0 else 0
                cor_lucro = "🟢" if lucro_estimado > 0 else ("🔴" if lucro_estimado < 0 else "⚪")
                st.write(
                    f"{cor_lucro} **Lucro estimado:** R$ {lucro_estimado:,.2f}  •  **Margem:** {margem:.1f}%"
                )

        st.divider()

        # --- Bloco DENTRO do form (validação só no submit) ---
        with st.form("form_venda_mala", clear_on_submit=True):
            col_b2, col_c2 = st.columns(2)

            with col_b2:
                forma_pagamento = st.selectbox(
                    "Forma de pagamento",
                    ["Dinheiro", "PIX", "Cartão de Crédito", "Cartão de Débito", "Boleto", "Transferência", "Outro"],
                    key="venda_pagamento",
                )
                data_venda = st.date_input("Data da venda", value=datetime.now().date(), key="venda_data")

            with col_c2:
                try:
                    df_clientes = db.get_clientes_cached()
                except Exception:
                    df_clientes = pd.DataFrame()
                if df_clientes is None or df_clientes.empty:
                    st.warning("Sem cliente cadastrado. Use 'Cliente avulso' abaixo.")
                    cliente_id = None
                    cliente_nome = st.text_input("Nome do cliente (avulso)", key="venda_cliente_nome")
                else:
                    cliente_opcao = st.radio(
                        "Cliente",
                        ["Cadastrado", "Avulso"],
                        horizontal=True,
                        key="venda_cliente_tipo",
                    )
                    if cliente_opcao == "Cadastrado":
                        opcoes_clientes = [f"{row['nome']} (id {row['id']})" for _, row in df_clientes.iterrows()]
                        cliente_sel = st.selectbox("Selecione o cliente", opcoes_clientes, key="venda_cliente_sel")
                        if cliente_sel:
                            cid = int(cliente_sel.split("id ")[-1].rstrip(")"))
                            linha = df_clientes[df_clientes["id"] == cid]
                            if not linha.empty:
                                cliente_id = int(linha.iloc[0]["id"])
                                cliente_nome = str(linha.iloc[0]["nome"])
                            else:
                                cliente_id = None
                                cliente_nome = ""
                        else:
                            cliente_id = None
                            cliente_nome = ""
                    else:
                        cliente_id = None
                        cliente_nome = st.text_input("Nome do cliente (avulso)", key="venda_cliente_nome_avulso")

            observacao = st.text_area("Observação", height=80, key="venda_obs")

            submitted = st.form_submit_button("💾 Registrar Venda", use_container_width=True)

            if submitted:
                if valor_venda <= 0:
                    st.error("Informe um valor de venda maior que zero.")
                elif not cliente_nome or not str(cliente_nome).strip():
                    st.error("Informe o nome do cliente (cadastrado ou avulso).")
                else:
                    sucesso, erro_venda = db.add_venda_mala(
                        mala_id=mala_id,
                        mala_codigo=str(mala_codigo or "").strip(),
                        mala_tamanho=str(mala_tamanho or "").strip(),
                        cliente_id=cliente_id,
                        cliente_nome=str(cliente_nome).strip(),
                        valor_venda=float(valor_venda),
                        custo_aquisicao=float(custo_aquisicao or 0),
                        tipo_mala=tipo_mala,
                        forma_pagamento=forma_pagamento,
                        observacao=str(observacao or "").strip(),
                        data_venda=data_venda.isoformat(),
                    )
                    if sucesso:
                        invalidate_cache()
                        st.success(f"✅ Venda registrada para {cliente_nome}.")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(f"❌ Erro ao registrar venda: {erro_venda}")

    with tab_consulta:
        st.markdown("### Histórico de Vendas")
        colf1, colf2 = st.columns(2)
        with colf1:
            filtro_inicio = st.date_input("De", value=datetime.now().date() - pd.Timedelta(days=90), key="venda_filtro_ini")
        with colf2:
            filtro_fim = st.date_input("Até", value=datetime.now().date(), key="venda_filtro_fim")

        df_vendas = db.get_vendas_malas(filtro_inicio.isoformat(), filtro_fim.isoformat())

        if df_vendas is None or df_vendas.empty:
            st.info("Nenhuma venda registrada no período selecionado.")
        else:
            resumo = db.get_resumo_vendas()
            cm1, cm2, cm3, cm4 = st.columns(4)
            cm1.metric("Vendas no período", f"{len(df_vendas)}")
            cm2.metric("Faturado (período)", f"R$ {df_vendas['valor_venda'].sum():,.2f}")
            cm3.metric("Custo de aquisição", f"R$ {df_vendas['custo_aquisicao'].sum():,.2f}")
            cm4.metric("Lucro (período)", f"R$ {(df_vendas['valor_venda'].sum() - df_vendas['custo_aquisicao'].sum()):,.2f}")

            st.markdown("#### Acumulado geral de vendas")
            ga1, ga2, ga3, ga4 = st.columns(4)
            ga1.metric("Total de vendas", f"{resumo['total_vendas']}")
            ga2.metric("Faturado total", f"R$ {resumo['total_vendido']:,.2f}")
            ga3.metric("Custo total", f"R$ {resumo['total_custo']:,.2f}")
            ga4.metric("Lucro total", f"R$ {resumo['total_lucro']:,.2f}")

            df_exibir = df_vendas[[
                "data_venda", "mala_codigo", "mala_tamanho", "tipo_mala",
                "cliente_nome", "valor_venda", "custo_aquisicao",
                "forma_pagamento", "observacao"
            ]].copy()
            df_exibir["lucro"] = df_exibir["valor_venda"] - df_exibir["custo_aquisicao"]
            st.dataframe(df_exibir, use_container_width=True, hide_index=True)

            st.markdown("#### Excluir venda (reverte mala para Disponível)")
            id_excluir = st.number_input(
                "ID da venda para excluir",
                min_value=0,
                step=1,
                value=0,
                key="venda_excluir_id",
            )
            if st.button("Excluir venda selecionada", key="venda_btn_excluir"):
                if id_excluir > 0:
                    ok_del, erro_del = db.delete_venda_mala(int(id_excluir))
                    if ok_del:
                        invalidate_cache()
                        st.success(f"Venda {id_excluir} removida.")
                        st.rerun()
                    else:
                        st.error(f"Erro: {erro_del}")

# --- CALCULADORA DE FRETE ---
elif st.session_state.page == "🚚 Calculadora de Frete":
    st.subheader("🚚 Calculadora de Frete (Ida e Volta)")
    
    st.info("Cálculo baseado na distância entre a sede (Votorantim) e o cliente.")
    
    # Endereço Fixo
    cep_origem = "18117-706"
    # Coordenadas aproximadas de Votorantim/SP para fallback
    lat_origem_fixo, lon_origem_fixo = -23.5447, -47.4389 
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📍 Dados do Cliente")
        
        # Opção para selecionar cliente cadastrado
        clientes_df = db.get_clientes()
        if not clientes_df.empty:
            opcoes_clientes = {f"{row['nome']} - {row['documento']}": row for _, row in clientes_df.iterrows()}
            cliente_selecionado = st.selectbox("Selecione um Cliente Cadastrado (Opcional)", ["-- Digitar Manualmente --"] + list(opcoes_clientes.keys()))
            
            cep_preenchido = ""
            cliente_id_sel = None
            
            if cliente_selecionado != "-- Digitar Manualmente --":
                dados_cliente = opcoes_clientes[cliente_selecionado]
                cliente_id_sel = dados_cliente['id']
                cep_banco = dados_cliente['cep']
                if cep_banco:
                    cep_preenchido = cep_banco
                else:
                    st.warning("Este cliente não tem CEP cadastrado.")
        else:
            cliente_id_sel = None
            cep_preenchido = ""
            st.info("Sem clientes cadastrados.")
        
        cep_cliente = st.text_input("CEP do Cliente", value=cep_preenchido, placeholder="00000-000")
        # Carregar valor_km salvo ou usar padrão (R$ 0,70 por km)
        valor_km_salvo = db.get_config('valor_km_padrao', 0.70)
        valor_km = st.number_input("Valor por KM (R$)", value=float(valor_km_salvo), step=0.10, format="%.2f", help="Valor cobrado por quilômetro rodado (ida e volta). Padrão: R$ 0,70")
        
        # Botão para salvar como padrão
        if st.button("💾 Salvar Valor como Padrão"):
            db.set_config('valor_km_padrao', valor_km)
            st.success(f"Valor R$ {valor_km:.2f} definido como padrão para os próximos cálculos!")
        
        if st.button("Calcular Frete", type="primary"):
            if not cep_cliente:
                st.warning("Digite o CEP do cliente.")
            else:
                with st.spinner("Buscando coordenadas e calculando distância..."):
                    # 1. Obter coordenadas Origem (Tentar buscar exato, senão usa fixo)
                    lat_origem, lon_origem = get_coordinates_from_cep(cep_origem)
                    if not lat_origem:
                        lat_origem, lon_origem = lat_origem_fixo, lon_origem_fixo
                        st.caption("Usando ponto de referência fixo de Votorantim.")
                        
                    # 2. Obter coordenadas Destino
                    lat_dest, lon_dest = get_coordinates_from_cep(cep_cliente)
                    
                    if lat_dest and lon_dest:
                        # 3. Calcular Distância Linear (Haversine)
                        dist_linear = haversine(lat_origem, lon_origem, lat_dest, lon_dest)
                        
                        # Fator de correção para rota (estrada não é linha reta) - Aprox 1.3x
                        fator_rota = 1.3
                        dist_estimada_ida = dist_linear * fator_rota
                        
                        # Ida e Volta (Entrega) + Ida e Volta (Retirada) = 4 pernas
                        dist_total_completa = dist_estimada_ida * 4
                        
                        valor_final = dist_total_completa * valor_km
                        
                        st.session_state['frete_calc'] = {
                            'dist_ida': dist_estimada_ida,
                            'dist_total': dist_total_completa,
                            'valor': valor_final,
                            'cep_cliente': cep_cliente,
                            'cliente_id': cliente_id_sel
                        }
                    else:
                        st.error("Não foi possível encontrar a localização deste CEP. Tente digitar a distância manualmente abaixo.")
                        st.session_state['frete_calc'] = None

    with col2:
        st.markdown("### 💰 Resultado")
        
        if 'frete_calc' in st.session_state and st.session_state['frete_calc']:
            res = st.session_state['frete_calc']
            
            # Recalcular valor com o input atual para ser dinâmico
            valor_atualizado = res['dist_total'] * valor_km
            
            st.metric("Distância Estimada (Ida)", f"{res['dist_ida']:.1f} km")
            st.metric("Distância Total (4 Viagens: Levar/Voltar + Buscar/Voltar)", f"{res['dist_total']:.1f} km")
            
            st.divider()
            st.metric("Valor Sugerido do Frete", f"R$ {valor_atualizado:.2f}")
            
            st.caption("*O cálculo considera: (Distância Ida x 4) x Valor Km. Inclui Entrega e Retirada.")
            
            # Botão Salvar
            if st.button("💾 Salvar no Histórico de Fretes"):
                if res.get('cliente_id'):
                    sucesso, msg = db.add_frete(int(res['cliente_id']), date.today(), res['cep_cliente'], res['dist_total'], valor_atualizado)
                    if sucesso:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.warning("Selecione um cliente cadastrado acima para salvar o histórico.")
        
        else:
            st.info("O resultado aparecerá aqui.")
            
    st.divider()
    
    # Histórico de Fretes
    st.subheader("📜 Histórico de Fretes Salvos")
    df_fretes = db.get_historico_fretes()
    
    if not df_fretes.empty:
        # Calcular totais
        total_acumulado = df_fretes['valor_frete'].sum()
        
        # Agrupar por Mês
        df_fretes['data_calculo'] = pd.to_datetime(df_fretes['data_calculo'])
        df_fretes['mes_ano'] = df_fretes['data_calculo'].dt.strftime('%Y-%m')
        
        # Mostrar métricas
        st.metric("Total Acumulado em Fretes (Histórico)", f"R$ {total_acumulado:.2f}")
        
        tab_lista, tab_mensal = st.tabs(["Lista Completa", "Por Mês"])
        
        with tab_lista:
            st.dataframe(df_fretes[['data_calculo', 'cliente_nome', 'cep_destino', 'distancia_total', 'valor_frete']], 
                         column_config={
                             "data_calculo": "Data",
                             "cliente_nome": "Cliente",
                             "cep_destino": "CEP",
                             "distancia_total": st.column_config.NumberColumn("Distância (km)", format="%.1f"),
                             "valor_frete": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f")
                         }, use_container_width=True)
            
            # Botão excluir
            with st.expander("🗑️ Excluir Frete"):
                lista_del_frete = {f"{row['id']} - {row['cliente_nome']} ({row['valor_frete']})": row['id'] for _, row in df_fretes.iterrows()}
                escolha_del_frete = st.selectbox("Selecione para excluir", list(lista_del_frete.keys()))
                if st.button("Confirmar Exclusão", key="btn_del_frete"):
                    id_del = lista_del_frete[escolha_del_frete]
                    db.delete_frete(id_del)
                    st.success("Excluído!")
                    st.rerun()

        with tab_mensal:
            df_agrupado = df_fretes.groupby('mes_ano')['valor_frete'].sum().reset_index()
            df_agrupado = df_agrupado.sort_values('mes_ano', ascending=False)
            
            st.dataframe(df_agrupado, 
                         column_config={
                             "mes_ano": "Mês/Ano",
                             "valor_frete": st.column_config.NumberColumn("Total Fretes (R$)", format="R$ %.2f")
                         }, use_container_width=True)
    else:
        st.info("Nenhum frete salvo ainda.")

    st.divider()
    
    with st.expander("🛠️ Ajuste Manual (Caso o cálculo automático falhe)"):
        dist_manual = st.number_input("Distância de IDA (km)", min_value=0.0, step=1.0)
        if dist_manual > 0:
            # 4 viagens: Ida para levar, Volta para base, Ida para buscar, Volta para base
            total_manual = dist_manual * 4 * valor_km
            st.success(f"Valor Calculado Manualmente (4 Viagens): **R$ {total_manual:.2f}**")
