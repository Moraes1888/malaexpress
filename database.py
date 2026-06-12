import sqlite3
import pandas as pd
from datetime import datetime
import os
import shutil
import hashlib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("MALAEXPRESS_DATA_DIR", BASE_DIR)
DB_NAME = os.getenv("MALAEXPRESS_DB_PATH", os.path.join(DATA_DIR, "mala_express.db"))
BACKUP_DIR = os.getenv("MALAEXPRESS_BACKUP_DIR", os.path.join(DATA_DIR, "backups"))
BUNDLED_DB_PATH = os.path.join(BASE_DIR, "mala_express.db")
SCHEMA_VERSION = 2

def ensure_data_storage():
    os.makedirs(os.path.dirname(DB_NAME), exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # No primeiro deploy online, copia o banco atual do projeto para o disco persistente.
    if not os.path.exists(DB_NAME) and os.path.exists(BUNDLED_DB_PATH) and os.path.abspath(DB_NAME) != os.path.abspath(BUNDLED_DB_PATH):
        shutil.copy2(BUNDLED_DB_PATH, DB_NAME)

def init_db():
    ensure_data_storage()
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Criar tabela de controle de versão do schema
    c.execute('''
        CREATE TABLE IF NOT EXISTS schema_version (
            versao INTEGER PRIMARY KEY,
            data_atualizacao DATE DEFAULT CURRENT_DATE
        )
    ''')
    
    # Verificar versão atual do schema
    c.execute("SELECT versao FROM schema_version ORDER BY versao DESC LIMIT 1")
    row = c.fetchone()
    versao_atual = row[0] if row else 0
    
    # Se schema já está na versão mais recente, pular migrações
    if versao_atual >= SCHEMA_VERSION:
        conn.close()
        return
    
    # Tabela de Malas (criar se não existir)
    c.execute('''
        CREATE TABLE IF NOT EXISTS malas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            tamanho TEXT NOT NULL,
            cor TEXT,
            marca TEXT,
            dimensoes TEXT,
            status TEXT DEFAULT 'Disponível',
            valor_pago REAL,
            imagem_path TEXT
        )
    ''')
    
    # Obter colunas existentes
    c.execute("PRAGMA table_info(malas)")
    columns = [column[1] for column in c.fetchall()]
    
    # Migrações - adicionar colunas que não existem
    migrations_malas = [
        ('valor_pago', "ALTER TABLE malas ADD COLUMN valor_pago REAL"),
        ('imagem_path', "ALTER TABLE malas ADD COLUMN imagem_path TEXT"),
        ('gestor_id', "ALTER TABLE malas ADD COLUMN gestor_id INTEGER"),
        ('fonte_pagamento', "ALTER TABLE malas ADD COLUMN fonte_pagamento TEXT DEFAULT 'Investimento Próprio'"),
        ('data_compra', "ALTER TABLE malas ADD COLUMN data_compra DATE"),
        ('forma_pagamento', "ALTER TABLE malas ADD COLUMN forma_pagamento TEXT"),
        ('parcelas', "ALTER TABLE malas ADD COLUMN parcelas INTEGER DEFAULT 1"),
    ]
    
    for col_name, sql in migrations_malas:
        if col_name not in columns:
            try:
                c.execute(sql)
            except:
                pass  # Coluna já pode existir via outra instalação
    
    # Garantir que dimensoes existe
    if 'dimensoes' not in columns:
        try:
            c.execute("ALTER TABLE malas ADD COLUMN dimensoes TEXT")
        except:
            pass

    # Tabela de Lixeira (parabackup antes de deletar)
    c.execute('''
        CREATE TABLE IF NOT EXISTS lixeira (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tabela TEXT NOT NULL,
            tipo TEXT NOT NULL,
            dados TEXT NOT NULL,
            data_exclusao DATE DEFAULT CURRENT_DATE
        )
    ''')

    # Tabela de Clientes
    c.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT,
            documento TEXT,
            cep TEXT
        )
    ''')
    
    # Tabela de Alugueis
    c.execute('''
        CREATE TABLE IF NOT EXISTS alugueis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mala_id INTEGER,
            cliente_id INTEGER,
            data_saida DATE,
            data_prevista_retorno DATE,
            data_retorno_real DATE,
            valor REAL,
            status TEXT DEFAULT 'Ativo',
            status_pagamento TEXT DEFAULT 'Pendente',
            FOREIGN KEY (mala_id) REFERENCES malas (id),
            FOREIGN KEY (cliente_id) REFERENCES clientes (id)
        )
    ''')
    
    # Tabela de Gastos Extras (Controle separado)
    c.execute('''
        CREATE TABLE IF NOT EXISTS gastos_extras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data DATE,
            descricao TEXT,
            categoria TEXT,
            valor REAL,
            gestor_id INTEGER,
            FOREIGN KEY (gestor_id) REFERENCES gestores (id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS avarias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aluguel_id INTEGER,
            mala_id INTEGER,
            cliente_id INTEGER,
            data DATE,
            valor REAL,
            observacao TEXT,
            FOREIGN KEY (aluguel_id) REFERENCES alugueis (id),
            FOREIGN KEY (mala_id) REFERENCES malas (id),
            FOREIGN KEY (cliente_id) REFERENCES clientes (id)
        )
    ''')
    
    # Tabela de Gestores
    c.execute('''
        CREATE TABLE IF NOT EXISTS gestores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Tabela de Histórico de Fretes (Controle paralelo)
    c.execute('''
        CREATE TABLE IF NOT EXISTS fretes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            data_calculo DATE,
            cep_destino TEXT,
            distancia_total REAL,
            valor_frete REAL,
            FOREIGN KEY (cliente_id) REFERENCES clientes (id)
        )
    ''')
    
    # Tabela de Configurações (Chave-Valor)
    c.execute('''
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    ''')

    # Tabela de Usuários
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            nome TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            perfil TEXT NOT NULL DEFAULT 'socio',
            ativo INTEGER NOT NULL DEFAULT 1
        )
    ''')
    
    # Aplicar migrações restantes (se versão < 1, aplicar todas)
    if versao_atual < 1:
        # Migrações para Clientes
        c.execute("PRAGMA table_info(clientes)")
        cliente_columns = [column[1] for column in c.fetchall()]
        migrations_clientes = [
            ('cep', "ALTER TABLE clientes ADD COLUMN cep TEXT"),
            ('cidade', "ALTER TABLE clientes ADD COLUMN cidade TEXT"),
            ('endereco', "ALTER TABLE clientes ADD COLUMN endereco TEXT"),
            ('telefone', "ALTER TABLE clientes ADD COLUMN telefone TEXT"),
        ]
        for col_name, sql in migrations_clientes:
            if col_name not in cliente_columns:
                try:
                    c.execute(sql)
                except:
                    pass
        
        # Migrações para Alugueis
        c.execute("PRAGMA table_info(alugueis)")
        aluguel_columns = [column[1] for column in c.fetchall()]
        migrations_alugueis = [
            ('status_pagamento', "ALTER TABLE alugueis ADD COLUMN status_pagamento TEXT DEFAULT 'Pendente'"),
            ('valor_sinal', "ALTER TABLE alugueis ADD COLUMN valor_sinal REAL DEFAULT 0.0"),
            ('taxa_entrega', "ALTER TABLE alugueis ADD COLUMN taxa_entrega REAL DEFAULT 0.0"),
            ('destino', "ALTER TABLE alugueis ADD COLUMN destino TEXT"),
            ('acessorios', "ALTER TABLE alugueis ADD COLUMN acessorios TEXT"),
            ('valor_acessorios', "ALTER TABLE alugueis ADD COLUMN valor_acessorios REAL DEFAULT 0.0"),
            ('observacao', "ALTER TABLE alugueis ADD COLUMN observacao TEXT"),
            ('valor_adicional', "ALTER TABLE alugueis ADD COLUMN valor_adicional REAL DEFAULT 0.0"),
            ('frete_calculado', "ALTER TABLE alugueis ADD COLUMN frete_calculado REAL DEFAULT 0.0"),
        ]
        for col_name, sql in migrations_alugueis:
            if col_name not in aluguel_columns:
                try:
                    c.execute(sql)
                except:
                    pass
        
        # Migrações para Gastos Extras
        c.execute("PRAGMA table_info(gastos_extras)")
        gastos_columns = [column[1] for column in c.fetchall()]
        migrations_gastos = [
            ('gestor_id', "ALTER TABLE gastos_extras ADD COLUMN gestor_id INTEGER"),
            ('fonte_pagamento', "ALTER TABLE gastos_extras ADD COLUMN fonte_pagamento TEXT DEFAULT 'Investimento Próprio'"),
        ]
        for col_name, sql in migrations_gastos:
            if col_name not in gastos_columns:
                try:
                    c.execute(sql)
                except:
                    pass
    
    if versao_atual < 2:
        c.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                nome TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                perfil TEXT NOT NULL DEFAULT 'socio',
                ativo INTEGER NOT NULL DEFAULT 1
            )
        ''')

        c.execute(
            "INSERT OR IGNORE INTO usuarios (username, nome, password_hash, perfil, ativo) VALUES (?, ?, ?, ?, 1)",
            ("admin", "Administrador", hashlib.sha256("admin123".encode("utf-8")).hexdigest(), "admin")
        )
        c.execute(
            "INSERT OR IGNORE INTO usuarios (username, nome, password_hash, perfil, ativo) VALUES (?, ?, ?, ?, 1)",
            ("socio", "Socio", hashlib.sha256("socio123".encode("utf-8")).hexdigest(), "socio")
        )

    # Atualizar versão do schema
    c.execute("INSERT OR REPLACE INTO schema_version (versao, data_atualizacao) VALUES (?, CURRENT_DATE)", (SCHEMA_VERSION,))
    
    conn.commit()
    conn.close()

# --- Funções para Malas ---
def get_proximos_alugueis():
    """Retorna aluguéis que começam hoje ou amanhã para lembrete"""
    conn = sqlite3.connect(DB_NAME)
    hoje = datetime.now().date().strftime('%Y-%m-%d')
    amanha = (datetime.now() + pd.Timedelta(days=1)).date().strftime('%Y-%m-%d')
    
    query = '''
        SELECT a.id, m.codigo as mala_codigo, c.nome as cliente_nome, 
               a.data_saida, a.data_prevista_retorno, m.imagem_path
        FROM alugueis a
        JOIN malas m ON a.mala_id = m.id
        JOIN clientes c ON a.cliente_id = c.id
        WHERE a.status = 'Ativo' 
        AND (a.data_saida = ? OR a.data_saida = ?)
    '''
    # Nota: Status 'Ativo' aqui pode ser confuso se o aluguel ainda não "começou" fisicamente mas já foi registrado.
    # Se o sistema permite registrar aluguel futuro, ele já entra como 'Ativo' e ocupa a mala.
    # Então 'Ativo' + data_saida futura = Reserva Futura.
    
    df = pd.read_sql(query, conn, params=(hoje, amanha))
    conn.close()
    return df

def get_proximo_codigo():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT codigo FROM malas ORDER BY id DESC LIMIT 1")
    ultimo = c.fetchone()
    conn.close()
    
    if ultimo:
        # Extrair número do último código (Ex: M005 -> 5)
        ultimo_codigo = ultimo[0]
        try:
            numero = int(ultimo_codigo[1:])
            novo_numero = numero + 1
        except ValueError:
            # Caso o código não siga o padrão M000
            novo_numero = 1
    else:
        novo_numero = 1
        
    return f"M{novo_numero:03d}"

def add_mala(codigo, tamanho, cor, marca, valor_pago=None, imagem_path=None, gestor_id=None, fonte_pagamento='Investimento Próprio', data_compra=None, forma_pagamento=None, parcelas=1, dimensoes=None):
    try:
        if data_compra is None:
            data_compra = datetime.now().date()
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        data_compra_str = data_compra.isoformat() if hasattr(data_compra, 'isoformat') else str(data_compra)
        c.execute("INSERT INTO malas (codigo, tamanho, cor, marca, valor_pago, imagem_path, gestor_id, fonte_pagamento, data_compra, forma_pagamento, parcelas, dimensoes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  (codigo, tamanho, cor, marca, valor_pago, imagem_path, gestor_id, fonte_pagamento, data_compra_str, forma_pagamento, parcelas, dimensoes))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_malas(status=None):
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT m.*, g.nome as gestor_nome
        FROM malas m
        LEFT JOIN gestores g ON m.gestor_id = g.id
    '''
    if status:
        query += f" WHERE m.status = '{status}'"
    else:
        query += " WHERE m.status != 'Quebrada'"
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def get_malas_para_gastos():
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT m.*, g.nome as gestor_nome
        FROM malas m
        LEFT JOIN gestores g ON m.gestor_id = g.id
        WHERE m.valor_pago IS NOT NULL AND m.valor_pago > 0
    '''
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def get_malas_disponiveis_por_data(data_inicio, data_fim):
    """
    Retorna DataFrame de malas que NÃO têm conflito de aluguel no período solicitado.
    Considera aluguéis 'Ativo' e 'Reservado'.
    """
    conn = sqlite3.connect(DB_NAME)
    
    # Query para encontrar malas ocupadas no período
    # Uma mala está ocupada se existe um aluguel onde:
    # O intervalo solicitado (I_inicio, I_fim) sobrepõe o intervalo do aluguel (A_saida, A_retorno)
    # Lógica de sobreposição: (A_saida <= I_fim) AND (A_retorno >= I_inicio)
    
    query_ocupadas = '''
        SELECT DISTINCT mala_id 
        FROM alugueis 
        WHERE status IN ('Ativo', 'Reservado')
        AND (data_saida <= ? AND data_prevista_retorno >= ?)
    '''
    
    # Busca IDs das malas ocupadas
    cursor = conn.cursor()
    cursor.execute(query_ocupadas, (data_fim, data_inicio))
    malas_ocupadas = [row[0] for row in cursor.fetchall()]
    
    # Busca todas as malas
    df_malas = pd.read_sql("SELECT * FROM malas WHERE status != 'Quebrada'", conn)
    conn.close()
    
    # Filtra malas que NÃO estão na lista de ocupadas
    if malas_ocupadas:
        df_disponiveis = df_malas[~df_malas['id'].isin(malas_ocupadas)]
    else:
        df_disponiveis = df_malas
        
    return df_disponiveis

def get_todos_alugueis():
    """Retorna todos os aluguéis para visualização no calendário"""
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT a.id, m.codigo as mala_codigo, c.nome as cliente_nome, 
               a.data_saida, a.data_prevista_retorno, a.status, m.cor as mala_cor, m.tamanho as mala_tamanho
        FROM alugueis a
        JOIN malas m ON a.mala_id = m.id
        JOIN clientes c ON a.cliente_id = c.id
        WHERE a.status != 'Cancelado'
    '''
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def get_historico_completo():
    """Retorna todos os aluguéis (ativos, finalizados e cancelados) para relatório"""
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT a.id, m.codigo as mala_codigo, c.nome as cliente_nome,
               a.data_saida, a.data_prevista_retorno, a.data_retorno_real,
               a.valor, a.taxa_entrega, a.valor_sinal,
               a.status, a.status_pagamento, a.frete_calculado
        FROM alugueis a
        JOIN malas m ON a.mala_id = m.id
        JOIN clientes c ON a.cliente_id = c.id
        ORDER BY a.data_saida DESC
    '''
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def get_ranking_clientes():
    """Retorna ranking de clientes por quantidade de aluguéis (datas diferentes), total faturado e quantidade de malas."""
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT
            c.id as cliente_id,
            c.nome as cliente_nome,
            c.telefone as cliente_telefone,
            COUNT(DISTINCT DATE(a.data_saida)) as qtd_dias_aluguel,
            COUNT(a.id) as qtd_alugueis,
            SUM(a.valor) as total_faturado,
            SUM(a.frete_calculado) as total_frete_calculado,
            COUNT(DISTINCT a.mala_id) as qtd_malas_diferentes
        FROM clientes c
        JOIN alugueis a ON c.id = a.cliente_id
        WHERE a.status != 'Cancelado'
        GROUP BY c.id, c.nome, c.telefone
        ORDER BY qtd_dias_aluguel DESC, total_faturado DESC
    '''
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def get_historico_devolucoes():
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT 
            a.id,
            a.data_retorno_real,
            m.codigo as mala_codigo,
            c.nome as cliente_nome,
            a.data_saida,
            a.data_prevista_retorno,
            a.status_pagamento,
            COALESCE(a.valor, 0) as valor,
            COALESCE(a.taxa_entrega, 0) as taxa_entrega,
            COALESCE(a.valor_acessorios, 0) as valor_acessorios,
            COALESCE(a.valor_sinal, 0) as valor_sinal,
            (COALESCE(a.valor, 0) + COALESCE(a.taxa_entrega, 0) + COALESCE(a.valor_acessorios, 0)) as total_geral,
            CASE 
                WHEN a.status_pagamento IN ('Pago', 'Permuta') THEN 0
                ELSE max((COALESCE(a.valor, 0) + COALESCE(a.taxa_entrega, 0) + COALESCE(a.valor_acessorios, 0) - COALESCE(a.valor_sinal, 0)), 0)
            END as restante,
            COALESCE(v.valor_avaria, 0) as valor_avaria,
            a.destino,
            a.acessorios
        FROM alugueis a
        JOIN malas m ON a.mala_id = m.id
        JOIN clientes c ON a.cliente_id = c.id
        LEFT JOIN (
            SELECT aluguel_id, SUM(COALESCE(valor, 0)) as valor_avaria
            FROM avarias
            GROUP BY aluguel_id
        ) v ON v.aluguel_id = a.id
        WHERE a.status = 'Finalizado'
        ORDER BY a.data_retorno_real DESC
    '''
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def delete_mala(mala_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Verificar se há aluguéis ativos
    c.execute("SELECT count(*) FROM alugueis WHERE mala_id = ? AND status = 'Ativo'", (mala_id,))
    ativos = c.fetchone()[0]
    
    if ativos > 0:
        conn.close()
        return False, "Esta mala possui aluguéis ativos e não pode ser excluída."
        
    try:
        # Excluir histórico de aluguéis (para permitir exclusão da mala)
        c.execute("DELETE FROM alugueis WHERE mala_id = ?", (mala_id,))
        # Excluir a mala
        c.execute("DELETE FROM malas WHERE id = ?", (mala_id,))
        conn.commit()
        conn.close()
        return True, "Mala excluída com sucesso."
    except Exception as e:
        conn.close()
        return False, f"Erro ao excluir: {e}"

def update_mala_status(mala_id, novo_status):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE malas SET status = ? WHERE id = ?", (novo_status, mala_id))
    conn.commit()
    conn.close()

# --- Funções para Clientes ---
def add_cliente(nome, documento, cep, endereco="", cidade="", telefone=""):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO clientes (nome, documento, cep, endereco, cidade, telefone) VALUES (?, ?, ?, ?, ?, ?)",
                  (nome, documento, cep, endereco, cidade, telefone))
        conn.commit()
        return True, None
    except IntegrityError:
        conn.rollback()
        return False, "Cliente já cadastrado com este documento."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def buscar_cliente_por_documento(documento):
    """Busca cliente pelo documento (CPF/CNPJ). Retorna o cliente ou None."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, nome, documento, telefone FROM clientes WHERE documento = ?", (documento,))
    row = c.fetchone()
    conn.close()
    if row:
        return {'id': row[0], 'nome': row[1], 'documento': row[2], 'telefone': row[3]}
    return None

def delete_cliente(cliente_id):
    """Remove um cliente do banco pelo ID."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))
        conn.commit()
        return True, "Cliente excluído."
    except Exception as e:
        return False, f"Erro: {e}"
    finally:
        conn.close()

def update_cliente(id, nome, documento, cep, endereco="", cidade="", telefone=""):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE clientes SET nome = ?, documento = ?, cep = ?, endereco = ?, cidade = ?, telefone = ? WHERE id = ?",
              (nome, documento, cep, endereco, cidade, telefone, id))
    conn.commit()
    conn.close()

def update_mala(id, tamanho, cor, marca, valor_pago, imagem_path, gestor_id=None, fonte_pagamento='Investimento Próprio', data_compra=None, forma_pagamento=None, parcelas=1, dimensoes=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    query = "UPDATE malas SET tamanho = ?, cor = ?, marca = ?, valor_pago = ?, gestor_id = ?, fonte_pagamento = ?"
    params = [tamanho, cor, marca, valor_pago, gestor_id, fonte_pagamento]
    
    if imagem_path:
        query += ", imagem_path = ?"
        params.append(imagem_path)
        
    if data_compra:
        query += ", data_compra = ?"
        params.append(data_compra)

    if forma_pagamento:
        query += ", forma_pagamento = ?"
        params.append(forma_pagamento)

    if parcelas:
        query += ", parcelas = ?"
        params.append(parcelas)

    if dimensoes is not None:
        query += ", dimensoes = ?"
        params.append(dimensoes)
        
    query += " WHERE id = ?"
    params.append(id)
    
    c.execute(query, tuple(params))
    conn.commit()
    conn.close()

def get_extrato_financeiro():
    conn = sqlite3.connect(DB_NAME)
    
    # Union de Entradas (Aluguéis) e Saídas (Malas e Gastos Extras)
    
    query = '''
        SELECT 
            a.id,
            a.data_saida as data, 
            'Entrada (Aluguel)' as tipo, 
            'Aluguel: ' || m.codigo || ' - ' || c.nome as descricao, 
            a.valor + COALESCE(a.taxa_entrega, 0) + COALESCE(a.valor_acessorios, 0) as valor
        FROM alugueis a
        JOIN malas m ON a.mala_id = m.id
        JOIN clientes c ON a.cliente_id = c.id
        WHERE a.status != 'Cancelado'
        
        UNION ALL
        
        SELECT 
            id,
            data, 
            'Saída (Gasto Extra)' as tipo, 
            descricao || ' (' || categoria || ')' as descricao, 
            -valor as valor
        FROM gastos_extras
        
        UNION ALL
        
        SELECT 
            id,
            COALESCE(data_compra, date('now')) as data, 
            'Saída (Compra Mala)' as tipo, 
            'Mala Nova: ' || codigo || ' - ' || marca as descricao, 
            -valor_pago as valor
        FROM malas 
        WHERE valor_pago > 0
        
        UNION ALL
        
        SELECT 
            av.id,
            COALESCE(av.data, date('now')) as data, 
            'Entrada (Cobranca Avaria)' as tipo, 
            'Cobranca Avaria: ' || m.codigo || ' - Cliente: ' || COALESCE(c.nome, 'N/A') as descricao, 
            av.valor as valor
        FROM avarias av
        JOIN alugueis al ON av.aluguel_id = al.id
        JOIN malas m ON al.mala_id = m.id
        LEFT JOIN clientes c ON al.cliente_id = c.id
        
        ORDER BY data DESC
    '''
    
    try:
        df = pd.read_sql(query, conn)
    except Exception:
        # Fallback se der erro (ex: coluna data_compra ainda não existe)
        df = pd.DataFrame()
        
    conn.close()
    return df

def get_clientes():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql("SELECT * FROM clientes", conn)
    conn.close()
    return df

# --- Funções para Aluguéis ---
def check_disponibilidade(mala_id, data_saida, data_prevista):
    """
    Verifica se a mala está disponível para o período solicitado.
    Retorna True se estiver livre, False se houver conflito.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Verifica se há sobreposição com aluguéis Ativos ou Reservados
    # Lógica de sobreposição: (A_saida <= I_fim) AND (A_retorno >= I_inicio)
    query = '''
        SELECT count(*) FROM alugueis 
        WHERE mala_id = ? 
        AND status IN ('Ativo', 'Reservado')
        AND (data_saida <= ? AND data_prevista_retorno >= ?)
    '''
    c.execute(query, (mala_id, data_prevista, data_saida))
    count = c.fetchone()[0]
    conn.close()
    
    return count == 0

def criar_aluguel(mala_id, cliente_id, data_saida, data_prevista, valor, pago=False, valor_sinal=0.0, taxa_entrega=0.0, status_pagamento_custom=None, destino=None, acessorios=None, valor_acessorios=0.0, observacao=None, frete_calculado=0.0):
    # Verificação extra de segurança
    if not check_disponibilidade(mala_id, data_saida, data_prevista):
        return False, "❌ ERRO: Esta mala já está alugada para este período!"

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    if status_pagamento_custom:
        status_pagamento = status_pagamento_custom
    else:
        status_pagamento = 'Pago' if pago else 'Pendente'
    
    try:
        # Registrar aluguel
        c.execute('''
            INSERT INTO alugueis (mala_id, cliente_id, data_saida, data_prevista_retorno, valor, status, status_pagamento, valor_sinal, taxa_entrega, destino, acessorios, valor_acessorios, observacao, frete_calculado)
            VALUES (?, ?, ?, ?, ?, 'Ativo', ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (mala_id, cliente_id, data_saida, data_prevista, valor, status_pagamento, valor_sinal, taxa_entrega, destino, acessorios, valor_acessorios, observacao, frete_calculado))
        
        # Atualizar status da mala
        c.execute("UPDATE malas SET status = 'Alugada' WHERE id = ?", (mala_id,))
        
        conn.commit()
        return True, "Aluguel registrado com sucesso!"
    except Exception as e:
        conn.rollback()
        return False, f"Erro ao criar aluguel: {e}"
    finally:
        conn.close()

def get_alugueis_ativos():
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT a.id, a.cliente_id, a.mala_id, m.codigo as mala_codigo, c.nome as cliente_nome, c.documento as cliente_doc, c.cep as cliente_cep, c.endereco as cliente_endereco, c.cidade as cliente_cidade, c.telefone as cliente_telefone,
               a.data_saida, a.data_prevista_retorno, a.valor, a.status_pagamento, a.valor_sinal, a.taxa_entrega, a.destino, a.acessorios, a.valor_acessorios, a.observacao, a.valor_adicional,
               m.imagem_path, m.marca, m.tamanho, m.cor as mala_cor, m.dimensoes as mala_dimensoes
        FROM alugueis a
        JOIN malas m ON a.mala_id = m.id
        JOIN clientes c ON a.cliente_id = c.id
        WHERE a.status = 'Ativo'
    '''
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def update_malas_dimensoes(mala_ids, dimensoes):
    if not mala_ids:
        return False, "Nenhuma mala selecionada."
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        placeholders = ",".join(["?"] * len(mala_ids))
        c.execute(f"UPDATE malas SET dimensoes = ? WHERE id IN ({placeholders})", (dimensoes, *mala_ids))
        conn.commit()
        return True, "Dimensões atualizadas."
    except Exception as e:
        conn.rollback()
        return False, f"Erro ao atualizar dimensões: {e}"
    finally:
        conn.close()

def update_aluguel_pagamento(aluguel_id, novo_status):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE alugueis SET status_pagamento = ? WHERE id = ?", (novo_status, aluguel_id))
    conn.commit()
    conn.close()

def prorrogar_aluguel(aluguel_id, nova_data_retorno, valor_adicional=0, observacao_extra=None):
    """Prorroga/estende um aluguel com nova data e valor adicional."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("SELECT data_prevista_retorno, valor, observacao FROM alugueis WHERE id = ?", (aluguel_id,))
        row = c.fetchone()
        if not row:
            return False, "Aluguel não encontrado."

        data_atual, valor_atual, obs_atual = row
        novo_valor = float(valor_atual) + float(valor_adicional)
        nova_observacao = obs_atual or ""
        if observacao_extra:
            nova_observacao += f" | Prorrogado em {date.today()}: {observacao_extra}"

        c.execute("""
            UPDATE alugueis
            SET data_prevista_retorno = ?, valor = ?, valor_adicional = COALESCE(valor_adicional, 0) + ?, observacao = ?
            WHERE id = ?
        """, (nova_data_retorno, novo_valor, valor_adicional, nova_observacao, aluguel_id))
        conn.commit()
        return True, f"Aluguel prorrogado! Novo valor: R$ {novo_valor:.2f}"
    except Exception as e:
        conn.rollback()
        return False, f"Erro ao prorrogar: {e}"
    finally:
        conn.close()

def update_aluguel_observacao(aluguel_id, observacao):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("UPDATE alugueis SET observacao = ? WHERE id = ?", (observacao, aluguel_id))
        conn.commit()
        return True, "Observação atualizada."
    except Exception as e:
        return False, f"Erro: {e}"
    finally:
        conn.close()

def add_avaria(aluguel_id, valor, observacao=None, data=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("SELECT mala_id, cliente_id FROM alugueis WHERE id = ?", (aluguel_id,))
        row = c.fetchone()
        if not row:
            return False, "Aluguel não encontrado."
        mala_id, cliente_id = row
        if data is None:
            data = datetime.now().date()
        c.execute(
            "INSERT INTO avarias (aluguel_id, mala_id, cliente_id, data, valor, observacao) VALUES (?, ?, ?, ?, ?, ?)",
            (aluguel_id, mala_id, cliente_id, data, valor, observacao),
        )
        conn.commit()
        return True, "Avaria registrada."
    except Exception as e:
        conn.rollback()
        return False, f"Erro ao registrar avaria: {e}"
    finally:
        conn.close()

def marcar_mala_quebrada(mala_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("UPDATE malas SET status = 'Quebrada' WHERE id = ?", (mala_id,))
        conn.commit()
        return True, "Mala marcada como quebrada."
    except Exception as e:
        conn.rollback()
        return False, f"Erro ao marcar mala quebrada: {e}"
    finally:
        conn.close()

def restaurar_mala_quebrada(mala_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("UPDATE malas SET status = 'Disponível' WHERE id = ?", (mala_id,))
        conn.commit()
        return True, "Mala restaurada para Disponível."
    except Exception as e:
        conn.rollback()
        return False, f"Erro ao restaurar mala: {e}"
    finally:
        conn.close()

def restaurar_aluguel_finalizado(aluguel_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("UPDATE alugueis SET status = 'Ativo', data_retorno_real = NULL WHERE id = ?", (aluguel_id,))
        conn.commit()
        return True, "Aluguel restaurado para Ativo."
    except Exception as e:
        conn.rollback()
        return False, f"Erro ao restaurar aluguel: {e}"
    finally:
        conn.close()

def get_registros_ate_data(data_ref):
    """Retorna malas e gastos extras cadastrados até a data_ref (para preview antes de restaurar)."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    data_ref_str = data_ref.isoformat() if hasattr(data_ref, 'isoformat') else str(data_ref)

    c.execute("SELECT id, codigo, tamanho, cor, marca, valor_pago, data_compra FROM malas WHERE data_compra <= ?", (data_ref_str,))
    malas = c.fetchall()

    c.execute("SELECT id, descricao, categoria, valor, data FROM gastos_extras WHERE data <= ?", (data_ref_str,))
    gastos = c.fetchall()

    conn.close()
    return {
        'malas': [{'id': r[0], 'codigo': r[1], 'tamanho': r[2], 'cor': r[3], 'marca': r[4], 'valor_pago': r[5], 'data_compra': r[6]} for r in malas],
        'gastos': [{'id': r[0], 'descricao': r[1], 'categoria': r[2], 'valor': r[3], 'data': r[4]} for r in gastos]
    }

def restaurar_tudo_ate_data(data_ref):
    """Remove malas e gastos extras cadastrados até a data_ref."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        data_ref_str = data_ref.isoformat() if hasattr(data_ref, 'isoformat') else str(data_ref)

        c.execute("DELETE FROM malas WHERE data_compra <= ?", (data_ref_str,))
        qtd_malas = c.rowcount

        c.execute("DELETE FROM gastos_extras WHERE data <= ?", (data_ref_str,))
        qtd_gastos = c.rowcount

        conn.commit()
        return True, f"Restaurado {qtd_malas} malas e {qtd_gastos} gastos extras."
    except Exception as e:
        conn.rollback()
        return False, f"Erro ao restaurar: {e}"
    finally:
        conn.close()

def get_registros_entre_datas(data_inicio, data_fim):
    """Retorna malas e gastos extras cadastrados entre data_inicio e data_fim (para preview antes de restaurar)."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    di_str = data_inicio.isoformat() if hasattr(data_inicio, 'isoformat') else str(data_inicio)
    df_str = data_fim.isoformat() if hasattr(data_fim, 'isoformat') else str(data_fim)

    c.execute("SELECT id, codigo, tamanho, cor, marca, valor_pago, data_compra FROM malas WHERE data_compra >= ? AND data_compra <= ?", (di_str, df_str))
    malas = c.fetchall()

    c.execute("SELECT id, descricao, categoria, valor, data FROM gastos_extras WHERE data >= ? AND data <= ?", (di_str, df_str))
    gastos = c.fetchall()

    conn.close()
    return {
        'malas': [{'id': r[0], 'codigo': r[1], 'tamanho': r[2], 'cor': r[3], 'marca': r[4], 'valor_pago': r[5], 'data_compra': r[6]} for r in malas],
        'gastos': [{'id': r[0], 'descricao': r[1], 'categoria': r[2], 'valor': r[3], 'data': r[4]} for r in gastos]
    }

def restaurar_tudo_entre_datas(data_inicio, data_fim):
    """Remove malas e gastos extras cadastrados entre data_inicio e data_fim (faz backup na lixeira primeiro)."""
    import json
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        di_str = data_inicio.isoformat() if hasattr(data_inicio, 'isoformat') else str(data_inicio)
        df_str = data_fim.isoformat() if hasattr(data_fim, 'isoformat') else str(data_fim)

        # Backup das malas na lixeira antes de deletar
        c.execute("SELECT id, codigo, tamanho, cor, marca, valor_pago, imagem_path, gestor_id, fonte_pagamento, data_compra, forma_pagamento, parcelas, dimensoes FROM malas WHERE data_compra >= ? AND data_compra <= ?", (di_str, df_str))
        malas_backup = c.fetchall()
        for m in malas_backup:
            dados = {'id': m[0], 'codigo': m[1], 'tamanho': m[2], 'cor': m[3], 'marca': m[4], 'valor_pago': m[5], 'imagem_path': m[6], 'gestor_id': m[7], 'fonte_pagamento': m[8], 'data_compra': m[9], 'forma_pagamento': m[10], 'parcelas': m[11], 'dimensoes': m[12]}
            dados_json = json.dumps(dados, default=str)
            c.execute("INSERT INTO lixeira (tabela, tipo, dados) VALUES (?, ?, ?)", ('malas', 'Mala', dados_json))

        # Backup dos gastos na lixeira antes de deletar
        c.execute("SELECT id, data, descricao, categoria, valor, gestor_id FROM gastos_extras WHERE data >= ? AND data <= ?", (di_str, df_str))
        gastos_backup = c.fetchall()
        for g in gastos_backup:
            dados = {'id': g[0], 'data': g[1], 'descricao': g[2], 'categoria': g[3], 'valor': g[4], 'gestor_id': g[5]}
            dados_json = json.dumps(dados, default=str)
            c.execute("INSERT INTO lixeira (tabela, tipo, dados) VALUES (?, ?, ?)", ('gastos_extras', 'Gasto Extra', dados_json))

        c.execute("DELETE FROM malas WHERE data_compra >= ? AND data_compra <= ?", (di_str, df_str))
        qtd_malas = c.rowcount

        c.execute("DELETE FROM gastos_extras WHERE data >= ? AND data <= ?", (di_str, df_str))
        qtd_gastos = c.rowcount

        conn.commit()
        return True, f"Removidas {qtd_malas} malas e {qtd_gastos} gastos extras. (Fazem backup na lixeira)"
    except Exception as e:
        conn.rollback()
        return False, f"Erro ao restaurar: {e}"
    finally:
        conn.close()

def add_lixeira(tabela, tipo, dados):
    """Salva registro na lixeira antes de deletar."""
    import json
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        dados_json = json.dumps(dados, default=str)
        c.execute("INSERT INTO lixeira (tabela, tipo, dados) VALUES (?, ?, ?)", (tabela, tipo, dados_json))
        conn.commit()
        return True
    except Exception as e:
        return False
    finally:
        conn.close()

def get_lixeira():
    """Retorna todos os itens da lixeira."""
    import json
    conn = sqlite3.connect(DB_NAME)
    query = "SELECT id, tabela, tipo, dados, data_exclusao FROM lixeira ORDER BY data_exclusao DESC"
    df = pd.read_sql(query, conn)
    conn.close()
    if not df.empty:
        df['dados_parsed'] = df['dados'].apply(lambda x: json.loads(x) if x else {})
    return df

def restaurar_da_lixeira(lixeira_id):
    """Restaura um item da lixeira para sua tabela original."""
    import json
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("SELECT tabela, tipo, dados FROM lixeira WHERE id = ?", (lixeira_id,))
        row = c.fetchone()
        if not row:
            return False, "Item não encontrado na lixeira."

        tabela, tipo, dados_json = row
        dados = json.loads(dados_json)

        if tabela == 'malas':
            c.execute("INSERT INTO malas (codigo, tamanho, cor, marca, valor_pago, imagem_path, gestor_id, fonte_pagamento, data_compra, forma_pagamento, parcelas, dimensoes, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (dados.get('codigo'), dados.get('tamanho'), dados.get('cor'), dados.get('marca'), dados.get('valor_pago'), dados.get('imagem_path'), dados.get('gestor_id'), dados.get('fonte_pagamento'), dados.get('data_compra'), dados.get('forma_pagamento'), dados.get('parcelas'), dados.get('dimensoes'), 'Disponível'))
        elif tabela == 'gastos_extras':
            c.execute("INSERT INTO gastos_extras (data, descricao, categoria, valor, gestor_id) VALUES (?, ?, ?, ?, ?)",
                (dados.get('data'), dados.get('descricao'), dados.get('categoria'), dados.get('valor'), dados.get('gestor_id')))

        c.execute("DELETE FROM lixeira WHERE id = ?", (lixeira_id,))
        conn.commit()
        return True, f"Item restaurado com sucesso."
    except Exception as e:
        conn.rollback()
        return False, f"Erro ao restaurar: {e}"
    finally:
        conn.close()

def deletar_da_lixeira(lixeira_id):
    """Remove definitivamente um item da lixeira."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM lixeira WHERE id = ?", (lixeira_id,))
        conn.commit()
        return True, "Item removido da lixeira."
    except Exception as e:
        return False, f"Erro: {e}"
    finally:
        conn.close()

def get_alugueis_futuros_por_mala(mala_id, data_ref):
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT a.id, a.data_saida, a.data_prevista_retorno, a.status, c.nome as cliente_nome
        FROM alugueis a
        JOIN clientes c ON a.cliente_id = c.id
        WHERE a.mala_id = ?
        AND a.status IN ('Ativo', 'Reservado')
        AND a.data_saida >= ?
        ORDER BY a.data_saida ASC
    '''
    df = pd.read_sql(query, conn, params=(mala_id, data_ref))
    conn.close()
    return df

def auto_trocar_alugueis_futuros_mala_quebrada(mala_id_quebrada, data_ref):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("SELECT tamanho FROM malas WHERE id = ?", (mala_id_quebrada,))
        row = c.fetchone()
        if not row:
            return False, "Mala não encontrada.", []
        tamanho_ref = row[0]

        df_alugueis = pd.read_sql(
            '''
            SELECT id, data_saida, data_prevista_retorno, status
            FROM alugueis
            WHERE mala_id = ?
            AND status IN ('Ativo', 'Reservado')
            AND data_saida >= ?
            ORDER BY data_saida ASC
            ''',
            conn,
            params=(mala_id_quebrada, data_ref),
        )

        resultados = []
        for _, a in df_alugueis.iterrows():
            aluguel_id = int(a['id'])
            data_saida = a['data_saida']
            data_retorno = a['data_prevista_retorno']

            df_cand = get_malas_disponiveis_por_data(data_saida, data_retorno)
            if df_cand.empty:
                resultados.append({"aluguel_id": aluguel_id, "status": "falha", "motivo": "Sem malas disponíveis"})
                continue

            df_cand = df_cand[(df_cand['id'] != mala_id_quebrada)]
            if 'status' in df_cand.columns:
                df_cand = df_cand[df_cand['status'] != 'Quebrada']
            if 'tamanho' in df_cand.columns:
                df_cand = df_cand[df_cand['tamanho'] == tamanho_ref]

            if df_cand.empty:
                resultados.append({"aluguel_id": aluguel_id, "status": "falha", "motivo": f"Sem malas livres no tamanho {tamanho_ref}"})
                continue

            df_cand = df_cand.sort_values('codigo')
            nova_mala_id = int(df_cand.iloc[0]['id'])

            c.execute("UPDATE alugueis SET mala_id = ? WHERE id = ?", (nova_mala_id, aluguel_id))
            resultados.append({"aluguel_id": aluguel_id, "status": "ok", "nova_mala_id": nova_mala_id})

        conn.commit()
        return True, "Processo concluído.", resultados
    except Exception as e:
        conn.rollback()
        return False, f"Erro ao trocar malas futuras: {e}", []
    finally:
        conn.close()

def update_aluguel_valor(aluguel_id, novo_valor, novo_sinal=0.0, nova_taxa_entrega=0.0, novo_valor_acessorios=0.0, novo_destino=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if novo_destino is not None:
        c.execute("UPDATE alugueis SET valor = ?, valor_sinal = ?, taxa_entrega = ?, valor_acessorios = ?, destino = ? WHERE id = ?", (novo_valor, novo_sinal, nova_taxa_entrega, novo_valor_acessorios, novo_destino, aluguel_id))
    else:
        c.execute("UPDATE alugueis SET valor = ?, valor_sinal = ?, taxa_entrega = ?, valor_acessorios = ? WHERE id = ?", (novo_valor, novo_sinal, nova_taxa_entrega, novo_valor_acessorios, aluguel_id))
    conn.commit()
    conn.close()

def update_aluguel_datas(aluguel_id, nova_data_saida, nova_data_prevista):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        # Obter ID da mala para verificar disponibilidade
        c.execute("SELECT mala_id FROM alugueis WHERE id = ?", (aluguel_id,))
        result = c.fetchone()
        if not result:
            return False, "Aluguel não encontrado."
        mala_id = result[0]
        
        # Verificar disponibilidade (excluindo o próprio aluguel da checagem)
        # Query adaptada de check_disponibilidade
        query_check = '''
            SELECT count(*) FROM alugueis 
            WHERE mala_id = ? 
            AND id != ?
            AND status IN ('Ativo', 'Reservado')
            AND (data_saida <= ? AND data_prevista_retorno >= ?)
        '''
        c.execute(query_check, (mala_id, aluguel_id, nova_data_prevista, nova_data_saida))
        if c.fetchone()[0] > 0:
            return False, "❌ Conflito! Essa mala já está alugada nesse novo período por outro contrato."

        c.execute("UPDATE alugueis SET data_saida = ?, data_prevista_retorno = ? WHERE id = ?", (nova_data_saida, nova_data_prevista, aluguel_id))
        conn.commit()
        return True, "Datas atualizadas com sucesso."
    except Exception as e:
        return False, f"Erro ao atualizar datas: {e}"
    finally:
        conn.close()

def trocar_mala_aluguel(aluguel_id, mala_antiga_id, mala_nova_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    try:
        # Obter datas do aluguel atual
        c.execute("SELECT data_saida, data_prevista_retorno FROM alugueis WHERE id = ?", (aluguel_id,))
        result = c.fetchone()
        if not result:
            return False, "Aluguel não encontrado."
        data_saida, data_prevista = result
        
        # Verificar disponibilidade da NOVA mala para essas datas
        # Não precisa excluir o aluguel atual da checagem pois ele está vinculado à mala ANTIGA ainda
        query_check = '''
            SELECT count(*) FROM alugueis 
            WHERE mala_id = ? 
            AND status IN ('Ativo', 'Reservado')
            AND (data_saida <= ? AND data_prevista_retorno >= ?)
        '''
        c.execute(query_check, (mala_nova_id, data_prevista, data_saida))
        if c.fetchone()[0] > 0:
            return False, "❌ A nova mala selecionada já está ocupada neste período!"

        # 1. Atualizar o aluguel com a nova mala
        c.execute("UPDATE alugueis SET mala_id = ? WHERE id = ?", (mala_nova_id, aluguel_id))
        
        # 2. Liberar a mala antiga
        c.execute("UPDATE malas SET status = 'Disponível' WHERE id = ?", (mala_antiga_id,))
        
        # 3. Ocupar a mala nova
        c.execute("UPDATE malas SET status = 'Alugada' WHERE id = ?", (mala_nova_id,))
        
        conn.commit()
        return True, "Mala trocada com sucesso!"
    except Exception as e:
        conn.rollback()
        return False, f"Erro ao trocar mala: {e}"
    finally:
        conn.close()

def get_disponibilidade_periodo(data_inicio, data_fim):
    """
    Retorna DataFrame com status de todas as malas para o período informado.
    Status pode ser 'Livre' ou 'Ocupada'.
    """
    conn = sqlite3.connect(DB_NAME)
    
    # 1. Pegar todas as malas
    df_malas = pd.read_sql("SELECT id, codigo, marca, tamanho, cor FROM malas WHERE status != 'Quebrada'", conn)
    
    if df_malas.empty:
        conn.close()
        return df_malas
    
    # 2. Pegar malas ocupadas no período
    query_ocupadas = '''
        SELECT DISTINCT mala_id 
        FROM alugueis 
        WHERE status IN ('Ativo', 'Reservado')
        AND (data_saida <= ? AND data_prevista_retorno >= ?)
    '''
    df_ocupadas = pd.read_sql(query_ocupadas, conn, params=(data_fim, data_inicio))
    ids_ocupados = df_ocupadas['mala_id'].tolist() if not df_ocupadas.empty else []
    
    # 3. Adicionar coluna de status
    df_malas['status_periodo'] = df_malas['id'].apply(lambda x: 'Ocupada' if x in ids_ocupados else 'Livre')
    
    # 4. Se ocupada, tentar trazer o nome do cliente e datas (extra)
    if not df_ocupadas.empty:
        query_detalhes = '''
            SELECT a.mala_id, c.nome as cliente_nome, a.data_saida, a.data_prevista_retorno
            FROM alugueis a
            JOIN clientes c ON a.cliente_id = c.id
            WHERE a.status IN ('Ativo', 'Reservado')
            AND (a.data_saida <= ? AND a.data_prevista_retorno >= ?)
        '''
        df_detalhes = pd.read_sql(query_detalhes, conn, params=(data_fim, data_inicio))
        
        # Merge para ter detalhes na mala
        df_malas = pd.merge(df_malas, df_detalhes, left_on='id', right_on='mala_id', how='left')
    else:
        df_malas['cliente_nome'] = None
        df_malas['data_saida'] = None
        df_malas['data_prevista_retorno'] = None

    conn.close()
    return df_malas

def get_acessorios_periodo(data_inicio, data_fim):
    """
    Retorna uma lista de strings com todos os acessórios reservados no período.
    Como não há cadastro estruturado, retorna a lista bruta para contagem.
    """
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT acessorios 
        FROM alugueis 
        WHERE status IN ('Ativo', 'Reservado')
        AND (data_saida <= ? AND data_prevista_retorno >= ?)
        AND acessorios IS NOT NULL AND acessorios != ''
    '''
    df = pd.read_sql(query, conn, params=(data_fim, data_inicio))
    conn.close()
    
    lista_acessorios = []
    if not df.empty:
        # Separar por vírgula se houver múltiplos itens no mesmo campo
        for texto in df['acessorios']:
            itens = [item.strip() for item in texto.replace(',', ';').split(';')] # Aceita , ou ; como separador
            lista_acessorios.extend(itens)
            
    return lista_acessorios

def get_analise_financeira():
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT
            m.codigo,
            m.tamanho,
            m.marca,
            m.cor,
            m.valor_pago as custo_aquisicao,
            g.nome as gestor_nome,
            COUNT(CASE WHEN a.status != 'Cancelado' THEN a.id END) as qtd_alugueis,
            COALESCE(SUM(
                CASE
                    WHEN a.status_pagamento = 'Pago' THEN a.valor + COALESCE(a.taxa_entrega, 0) + COALESCE(a.valor_acessorios, 0)
                    ELSE COALESCE(a.valor_sinal, 0)
                END
            ), 0) + COALESCE((
                SELECT SUM(av.valor)
                FROM avarias av
                JOIN alugueis al ON av.aluguel_id = al.id
                WHERE al.mala_id = m.id
            ), 0) as total_faturado
        FROM malas m
        LEFT JOIN alugueis a ON m.id = a.mala_id AND a.status != 'Cancelado'
        LEFT JOIN gestores g ON m.gestor_id = g.id
        GROUP BY m.id
    '''
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def get_status_estoque():
    """Retorna contagem de malas totais e disponíveis"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute("SELECT count(*) FROM malas WHERE status != 'Quebrada'")
    total = c.fetchone()[0]
    
    c.execute("SELECT count(*) FROM malas WHERE status = 'Disponível'")
    disponiveis = c.fetchone()[0]
    
    conn.close()
    return total, disponiveis

def finalizar_aluguel(aluguel_id, data_retorno):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    try:
        # Obter ID da mala associada e status atual de pagamento
        c.execute("SELECT mala_id, status_pagamento FROM alugueis WHERE id = ?", (aluguel_id,))
        result = c.fetchone()
        if not result:
            return False, "Aluguel não encontrado."
            
        mala_id, status_pagamento_atual = result
        
        # 1. Marcar aluguel como Finalizado e salvar data real
        c.execute("UPDATE alugueis SET status = 'Finalizado', data_retorno_real = ? WHERE id = ?", (data_retorno, aluguel_id))
        
        # 2. Se o pagamento ainda estiver Pendente, sugerir Pago? 
        # Melhor não automatizar isso, pois pode ter calote ou atraso. Manter como está.
        # Mas podemos garantir que se estava pendente e foi devolvido, talvez cobrar o resto?
        # Por enquanto, só muda o status do aluguel.
        
        # 3. Liberar a mala
        c.execute("UPDATE malas SET status = 'Disponível' WHERE id = ?", (mala_id,))
        
        conn.commit()
        return True, "Devolução registrada com sucesso."
    except Exception as e:
        return False, f"Erro ao finalizar: {e}"
    finally:
        conn.close()

def cancelar_aluguel(aluguel_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Obter ID da mala associada
    c.execute("SELECT mala_id FROM alugueis WHERE id = ?", (aluguel_id,))
    resultado = c.fetchone()
    if not resultado:
        conn.close()
        return False, "Aluguel não encontrado."
        
    mala_id = resultado[0]
    
    try:
        # Atualizar aluguel para Cancelado
        c.execute('''
            UPDATE alugueis 
            SET status = 'Cancelado', status_pagamento = 'Cancelado' 
            WHERE id = ?
        ''', (aluguel_id,))
        
        # Liberar a mala
        c.execute("UPDATE malas SET status = 'Disponível' WHERE id = ?", (mala_id,))
        
        conn.commit()
        return True, "Aluguel cancelado com sucesso."
    except Exception as e:
        conn.rollback()
        return False, f"Erro ao cancelar: {e}"
    finally:
        conn.close()

# --- Funções para Gestores ---
def add_gestor(nome):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO gestores (nome) VALUES (?)", (nome,))
        conn.commit()
        return True, "Gestor cadastrado com sucesso!"
    except sqlite3.IntegrityError:
        return False, "Gestor já existe."
    except Exception as e:
        return False, f"Erro ao cadastrar gestor: {e}"
    finally:
        conn.close()

def get_gestores():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql("SELECT * FROM gestores", conn)
    conn.close()
    return df

def delete_gestor(gestor_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        # Verificar se tem gastos vinculados
        c.execute("SELECT count(*) FROM gastos_extras WHERE gestor_id = ?", (gestor_id,))
        count = c.fetchone()[0]
        if count > 0:
            return False, "Não é possível excluir: Existem gastos vinculados a este gestor."
            
        c.execute("DELETE FROM gestores WHERE id = ?", (gestor_id,))
        conn.commit()
        return True, "Gestor excluído com sucesso."
    except Exception as e:
        return False, f"Erro ao excluir: {e}"
    finally:
        conn.close()

# --- Funções para Gastos Extras ---
def add_gasto_extra(data, descricao, categoria, valor, gestor_id=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO gastos_extras (data, descricao, categoria, valor, gestor_id) VALUES (?, ?, ?, ?, ?)",
                  (data, descricao, categoria, valor, gestor_id))
        conn.commit()
        return True, "Gasto registrado com sucesso!"
    except Exception as e:
        return False, f"Erro ao registrar gasto: {e}"
    finally:
        conn.close()

def get_faturamento_mensal():
    """Retorna faturamento agrupado por mês/ano"""
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT
            mes_ano,
            SUM(faturamento) AS faturamento
        FROM (
            SELECT 
                strftime('%Y-%m', data_saida) as mes_ano,
                SUM(
                    CASE 
                        WHEN status_pagamento = 'Pago' THEN valor + COALESCE(taxa_entrega, 0) + COALESCE(valor_acessorios, 0)
                        ELSE COALESCE(valor_sinal, 0) 
                    END
                ) as faturamento
            FROM alugueis
            WHERE status != 'Cancelado'
              AND data_saida IS NOT NULL
            GROUP BY mes_ano
            
            UNION ALL
            
            SELECT 
                strftime('%Y-%m', av.data) as mes_ano,
                SUM(av.valor) as faturamento
            FROM avarias av
            WHERE av.data IS NOT NULL
            GROUP BY mes_ano
        )
        GROUP BY mes_ano
        ORDER BY mes_ano ASC
    '''
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def update_gasto_extra(id, data, descricao, categoria, valor, gestor_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("UPDATE gastos_extras SET data = ?, descricao = ?, categoria = ?, valor = ?, gestor_id = ? WHERE id = ?",
                  (data, descricao, categoria, valor, gestor_id, id))
        conn.commit()
        return True, "Gasto atualizado com sucesso!"
    except Exception as e:
        return False, f"Erro ao atualizar gasto: {e}"
    finally:
        conn.close()

def get_gastos_extras():
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT g.id, g.data, g.descricao, g.categoria, g.valor, g.gestor_id, ges.nome as gestor_nome
        FROM gastos_extras g
        LEFT JOIN gestores ges ON g.gestor_id = ges.id
        ORDER BY g.data DESC
    '''
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def delete_gasto_extra(id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM gastos_extras WHERE id = ?", (id,))
        conn.commit()
        return True, "Gasto excluído com sucesso."
    except Exception as e:
        return False, f"Erro ao excluir gasto: {e}"
    finally:
        conn.close()

# --- Funções para Fretes ---
def add_frete(cliente_id, data_calculo, cep_destino, distancia_total, valor_frete):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO fretes (cliente_id, data_calculo, cep_destino, distancia_total, valor_frete) VALUES (?, ?, ?, ?, ?)",
                  (cliente_id, data_calculo, cep_destino, distancia_total, valor_frete))
        conn.commit()
        return True, "Frete salvo no histórico com sucesso!"
    except Exception as e:
        return False, f"Erro ao salvar frete: {e}"
    finally:
        conn.close()

def get_historico_fretes():
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT f.id, f.data_calculo, c.nome as cliente_nome, f.cep_destino, f.distancia_total, f.valor_frete
        FROM fretes f
        LEFT JOIN clientes c ON f.cliente_id = c.id
        ORDER BY f.data_calculo DESC
    '''
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def delete_frete(id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM fretes WHERE id = ?", (id,))
        conn.commit()
        return True, "Frete excluído com sucesso."
    except Exception as e:
        return False, f"Erro ao excluir frete: {e}"
    finally:
        conn.close()

# --- Funções de Configuração ---
def get_config(chave, default=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT valor FROM configuracoes WHERE chave = ?", (chave,))
    result = c.fetchone()
    conn.close()
    if result:
        return result[0]
    return default

def set_config(chave, valor):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)", (chave, str(valor)))
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def autenticar_usuario(username, password):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "SELECT id, username, nome, perfil, ativo, password_hash FROM usuarios WHERE username = ?",
        (username.strip(),)
    )
    row = c.fetchone()
    conn.close()

    if not row:
        return False, "Usuário não encontrado.", None

    user_id, user_name, nome, perfil, ativo, password_hash = row

    if int(ativo) != 1:
        return False, "Usuário inativo.", None

    if hash_password(password) != password_hash:
        return False, "Senha incorreta.", None

    return True, "Login realizado com sucesso.", {
        "id": user_id,
        "username": user_name,
        "nome": nome,
        "perfil": perfil,
    }

def cliente_tem_frete_calculado(cliente_id):
    """Verifica se o cliente já tem algum frete calculado em aluguéis ativos."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        SELECT COUNT(*) FROM alugueis 
        WHERE cliente_id = ? 
        AND status != 'Cancelado' 
        AND COALESCE(frete_calculado, 0) > 0
    ''', (cliente_id,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0

def get_total_fretes_acumulados():
    """Retorna o total acumulado de fretes únicos por cliente (cada cliente paga frete apenas uma vez)."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Soma fretes únicos por cliente (cada cliente paga frete apenas uma vez)
    c.execute('''
        SELECT COALESCE(SUM(frete_calculado), 0) 
        FROM (
            SELECT MIN(id) as id, cliente_id, COALESCE(frete_calculado, 0) as frete_calculado
            FROM alugueis 
            WHERE status != 'Cancelado' 
            AND COALESCE(frete_calculado, 0) > 0
            GROUP BY cliente_id
        )
    ''')
    total = c.fetchone()[0]
    conn.close()
    return total

def get_fretes_por_periodo(data_inicio=None, data_fim=None):
    """Retorna fretes únicos por cliente agrupados por período para análise."""
    conn = sqlite3.connect(DB_NAME)
    
    if data_inicio and data_fim:
        query = '''
            SELECT 
                strftime('%Y-%m', a.data_saida) as mes_ano,
                COUNT(DISTINCT a.cliente_id) as qtd_clientes,
                SUM(a.frete_calculado) as total_frete
            FROM (
                SELECT MIN(id) as id, cliente_id, data_saida, COALESCE(frete_calculado, 0) as frete_calculado
                FROM alugueis 
                WHERE status != 'Cancelado' 
                AND COALESCE(frete_calculado, 0) > 0
                AND data_saida >= ? AND data_saida <= ?
                GROUP BY cliente_id
            ) a
            GROUP BY mes_ano
            ORDER BY mes_ano DESC
        '''
        df = pd.read_sql(query, conn, params=(data_inicio, data_fim))
    else:
        query = '''
            SELECT 
                strftime('%Y-%m', a.data_saida) as mes_ano,
                COUNT(DISTINCT a.cliente_id) as qtd_clientes,
                SUM(a.frete_calculado) as total_frete
            FROM (
                SELECT MIN(id) as id, cliente_id, data_saida, COALESCE(frete_calculado, 0) as frete_calculado
                FROM alugueis 
                WHERE status != 'Cancelado' 
                AND COALESCE(frete_calculado, 0) > 0
                GROUP BY cliente_id
            ) a
            GROUP BY mes_ano
            ORDER BY mes_ano DESC
        '''
        df = pd.read_sql(query, conn)
    
    conn.close()
    return df

def backup_db(max_backup=10):
    """Cria backup do banco de dados com timestamp. Mantém os últimos max_backup backups."""
    if not os.path.exists(DB_NAME):
        return False, "Banco de dados não encontrado."
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = BACKUP_DIR
        os.makedirs(backup_dir, exist_ok=True)
        backup_name = f"mala_express_{ts}.db"
        backup_path = os.path.join(backup_dir, backup_name)
        shutil.copy2(DB_NAME, backup_path)
        existing = sorted([f for f in os.listdir(backup_dir) if f.startswith("mala_express_") and f.endswith(".db")])
        while len(existing) > max_backup:
            oldest = os.path.join(backup_dir, existing.pop(0))
            os.remove(oldest)
        return True, f"Backup criado: {backup_name} ({len(existing)+1} backups, mantendo os {max_backup} mais recentes)"
    except Exception as e:
        return False, f"Erro ao criar backup: {e}"
