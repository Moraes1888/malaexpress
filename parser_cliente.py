# -*- coding: utf-8 -*-
"""
Parser de mensagens de WhatsApp para preenchimento automático do cadastro
de clientes do MalaExpress.

Mensagem suportada (exemplo real):

    Mala Express
    Me envia por favor esses dados
    Nome Completo : Hellen Almeida
    CPF: 361.310.648-57
    Endereço: Rua Esperança 373 - Bloco A - Apto 104 - Condomínio Paris -
    Sorocaba
    Destino:
    Data de ida: 21/12
    Data de volta : 03/01
    Telefone: 15998456069

Retorno (dicionário):
    nome, documento, endereco, cep, cidade, uf, telefone
    destino, data_ida, data_volta   (apenas identificados, NÃO são gravados
                                     no cadastro do cliente)
"""

import re
import unicodedata

# --------------------------------------------------------------------------
# Rótulos reconhecidos: (rótulo normalizado, campo, exige dois-pontos?)
# --------------------------------------------------------------------------
ROTULOS = [
    ("nome completo", "nome", False),
    ("nome do cliente", "nome", False),
    ("nome", "nome", True),
    ("cpf/cnpj", "documento", False),
    ("cpf", "documento", False),
    ("cnpj", "documento", False),
    ("documento", "documento", False),
    ("doc", "documento", True),
    ("endereco completo", "endereco", False),
    ("endereco", "endereco", False),
    ("logradouro", "endereco", True),
    ("cep", "cep", False),
    ("cidade/uf", "cidade", False),
    ("cidade", "cidade", False),
    ("municipio", "cidade", True),
    ("telefone", "telefone", False),
    ("celular", "telefone", False),
    ("whatsapp", "telefone", False),
    ("fone", "telefone", True),
    ("contato", "telefone", True),
    ("tel", "telefone", True),
    # Dados da viagem: apenas identificados, nunca gravados no cadastro
    ("data de ida", "data_ida", False),
    ("data da ida", "data_ida", False),
    ("data de volta", "data_volta", False),
    ("data da volta", "data_volta", False),
    ("ida", "data_ida", True),
    ("volta", "data_volta", True),
    ("destino", "destino", False),
    ("retirada", "retirada", False),
    ("devolucao", "devolucao", False),
    ("periodo", "periodo", False),
    ("observacao", "observacao", False),
    ("obs", "observacao", True),
]

# Campos que pertencem ao cadastro do cliente
CAMPOS_CLIENTE = ("nome", "documento", "endereco", "cep", "cidade", "telefone")

# Campos que aceitam linhas de continuação (ex.: endereço quebrado em 2 linhas).
# Telefone/documento/CEP NÃO aceitam continuação para não absorver o horário
# do WhatsApp (ex.: "17:52") ou linhas soltas.
CAMPOS_COM_CONTINUACAO = (
    "endereco", "nome", "cidade", "destino", "observacao",
    "periodo", "retirada", "devolucao",
)

# Cidades (principalmente região de Sorocaba/Votorantim) -> UF
CIDADES_UF = {
    "sorocaba": "SP", "votorantim": "SP", "sao paulo": "SP",
    "aracoiaba da serra": "SP", "sao roque": "SP", "salto de pirapora": "SP",
    "porto feliz": "SP", "piedade": "SP", "capeo bonito": "SP", "itu": "SP",
    "tatu": "SP", "salto": "SP", "biritiba": "SP", "ibirapuera": "SP",
    "laranjal paulista": "SP", "sarapui": "SP", "barrinha": "SP",
    "aparecida": "SP", "pereira barreto": "SP", "guapiara": "SP",
    "campo limpo de votorantim": "SP", "votorantim": "SP", "budemann": "SP",
    "campinas": "SP", "indaiatuba": "SP", "avare": "SP", "barretos": "SP",
    "bebedouro": "SP", "guariba": "SP", "jaboticabal": "SP",
    "ribeirao preto": "SP", "mogi das cruzes": "SP", "osasco": "SP",
    "guarulhos": "SP", "santo andre": "SP", "sao caetano do sul": "SP",
    "sao bernardo do campo": "SP", "diadema": "SP", "maua": "SP",
    "santo antonio de poco": "SP", "vinhedo": "SP", "valinhos": "SP",
    "jundiai": "SP", "limeira": "SP", "rio claro": "SP", "corupa": "SP",
    "curitiba": "PR", "ponta grossa": "PR", "campina grande": "PB",
    "joao pessoa": "PB", "recife": "PE", "olinda": "PE", "caruaru": "PE",
    "natal": "RN", "fortaleza": "CE", "salvador": "BA", "feira de santana": "BA",
    "vitoria": "ES", "serra": "ES", "rio de janeiro": "RJ",
    "sao goncalo": "RJ", "belo horizonte": "MG", "uberlandia": "MG",
    "contagem": "MG", "juiz de fora": "MG", "brasilia": "DF",
    "goiania": "GO", "ananindeua": "PA", "belem": "PA", "manaus": "AM",
    "florianopolis": "SC", "joinville": "SC", "blumenau": "SC",
    "porto alegre": "RS", "caxias do sul": "RS", "fortaleza": "CE",
}

# Palavras que normalmente NÃO são cidade (evita cortar "Bloco A" etc.)
NAO_E_CIDADE = {
    "bloco", "apto", "apt", "apartamento", "casa", "sala", "kitnet",
    "complemento", "cond", "condominio", "bairro", "rua", "avenida", "av",
    "travessa", "praca", "rodovia", "estrada", "vila", "edificio", "andar",
    "conjunto", "fazenda", "sitio", "galpao", "loja", "jardim", "parque",
    "recanto", "residencial", "sitio", "lote", "quadra", "lote", "numero",
}

UF_SINTAXE = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "bahia": "BA",
    "ceara": "CE", "distrito federal": "DF", "espirito santo": "ES",
    "goias": "GO", "maranhao": "MA", "mato grosso": "MT",
    "mato grosso do sul": "MS", "minas gerais": "MG", "para": "PA",
    "paraiba": "PB", "parana": "PR", "pernambuco": "PE", "piaui": "PI",
    "rio de janeiro": "RJ", "rio grande do norte": "RN",
    "rio grande do sul": "RS", "rondonia": "RO", "roraima": "RR",
    "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE",
    "tocantins": "TO",
}


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def _sem_acento(texto):
    """Remove acentos mantendo o texto legível."""
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def _normalizado_1para1(texto):
    """
    Versão sem acento e em minúsculas, preservando o tamanho da string
    (1 caractere original = 1 caractere retornado), para que seja possível
    recortar o valor usando as mesmas posições do texto original.
    """
    saida = []
    for ch in texto:
        n = unicodedata.normalize("NFKD", ch)
        n = "".join(c for c in n if not unicodedata.combining(c))
        saida.append((n[:1] if n else ch).lower())
    return "".join(saida)


def _chave(texto):
    """Chave de comparação: sem acento, minúsculas, espaços normalizados."""
    return re.sub(r"\s+", " ", _sem_acento(texto).lower()).strip()


def _padrao_rotulo(alias):
    """Monta regex do rótulo aceitando espaços variáveis entre palavras."""
    return r"\s+".join(re.escape(p) for p in alias.split())


# Rótulos ordenados do mais longo para o mais curto (evita "nome" casar com
# "nome completo", "data" casar com "data de ida", etc.)
_ROTULOS_ORDENADOS = sorted(ROTULOS, key=lambda item: len(item[0]), reverse=True)


def _identificar_rotulo(linha):
    """
    Retorna (campo, valor) se a linha começar com um rótulo conhecido,
    caso contrário None.
    """
    norm = _normalizado_1para1(linha)
    for alias, campo, exige_colon in _ROTULOS_ORDENADOS:
        m = re.match(
            r"^\s*" + _padrao_rotulo(alias) + r"\s*(:)?\s*(.*)$", norm, re.DOTALL
        )
        if not m:
            continue
        if exige_colon and not m.group(1):
            continue
        # Mesmas posições no texto normalizado -> recorte seguro no original
        valor = linha[m.start(2):m.end(2)].strip()
        return campo, valor
    return None


def _separar_cidade(endereco):
    """
    Separa a cidade do final do endereço.

    Retorna (endereco_sem_cidade, cidade, uf).
    """
    if not endereco:
        return "", "", ""

    # Divide o endereço em partes mantendo a posição original de cada parte
    partes = []
    inicio = 0
    for sep in re.finditer(r"\s*[-–—]\s*|,\s*", endereco):
        trecho = endereco[inicio:sep.start()].strip()
        if trecho:
            partes.append((trecho, inicio, sep.start()))
        inicio = sep.end()
    trecho = endereco[inicio:].strip()
    if trecho:
        partes.append((trecho, inicio, len(endereco)))

    if not partes:
        return endereco, "", ""

    # Caso "Cidade - SP" (UF isolada no final)
    if len(partes) >= 2 and len(partes[-1][0]) == 2 and partes[-1][0].isalpha():
        uf = UF_SINTAXE.get(_chave(partes[-1][0]), partes[-1][0].upper())
        nome, uf2 = _cidade_e_uf(partes[-2][0])
        if nome:
            return endereco[:partes[-2][1]].strip(" ,;-"), nome, (uf2 or uf)

    for i in range(len(partes) - 1, -1, -1):
        texto, pos_inicio, _ = partes[i]
        p = texto.strip(" ,;")
        if not p:
            continue
        if re.search(r"\d", p):
            break  # a parte tem número -> não é cidade

        nome, uf = _cidade_e_uf(p)
        if nome:
            return endereco[:pos_inicio].strip(" ,;-"), nome, uf

        if _parece_cidade(p):
            return endereco[:pos_inicio].strip(" ,;-"), p, ""

        break  # última parte não é cidade -> mantém o endereço como está

    return endereco, "", ""


def _cidade_e_uf(texto):
    """Retorna (cidade, uf) a partir de textos como 'Sorocaba/SP' ou 'Sorocaba'."""
    t = texto.strip()
    uf = ""
    m = re.match(r"^(.*?)\s*[/,]\s*([A-Za-z]{2})\s*$", t)
    if m:
        t = m.group(1).strip()
        uf = m.group(2).upper()
    chave = _chave(t)
    uf = uf or CIDADES_UF.get(chave, "")
    if not uf:
        uf = UF_SINTAXE.get(chave, "")
    return t, uf


def _parece_cidade(texto):
    """Heurística: palavra sem número e que não é parte de endereço."""
    if re.search(r"\d", texto):
        return False
    palavras = _chave(texto).split()
    if not palavras or len(palavras[0]) < 4:
        return False
    if palavras[0] in NAO_E_CIDADE:
        return False
    return len(_chave(texto).replace(" ", "")) >= 4


def _limpar_documento(valor):
    """Extrai CPF/CNPJ preservando a formatação original."""
    if not valor:
        return ""
    texto = valor.strip()
    digitos = re.sub(r"\D", "", texto)
    if digitos and len(digitos) in (11, 14):
        return texto
    m = re.search(r"\d{3}\.?\d{3}\.?\d{3}[-/]?\d{2}|\d{2}\.?\d{3}\.?\d{3}[-/]?\d{4}[-/]?\d{2}", texto)
    if m:
        return m.group(0)
    return ""


def _limpar_telefone(valor):
    """Retorna somente os dígitos do telefone."""
    if not valor:
        return ""
    digitos = re.sub(r"\D", "", valor)
    if len(digitos) == 11 and digitos.startswith("0"):
        digitos = digitos[1:]
    if len(digitos) > 11:
        digitos = digitos[-11:]
    return digitos


def _limpar_cep(valor):
    """Retorna o CEP com 8 dígitos."""
    if not valor:
        return ""
    digitos = re.sub(r"\D", "", valor)
    return digitos if len(digitos) == 8 else ""


# --------------------------------------------------------------------------
# Função principal
# --------------------------------------------------------------------------
def extrair_dados_cliente(texto):
    """
    Extrai os dados do cliente a partir de uma mensagem de WhatsApp.

    Retorna um dicionário com as chaves:
        nome, documento, endereco, cep, cidade, uf, telefone,
        destino, data_ida, data_volta
    """
    resultado = {
        "nome": "",
        "documento": "",
        "endereco": "",
        "cep": "",
        "cidade": "",
        "uf": "",
        "telefone": "",
        "destino": "",
        "data_ida": "",
        "data_volta": "",
    }
    if not texto:
        return resultado

    grupos = []          # [(campo, [linhas])]
    campo_atual = None

    for linha_bruta in str(texto).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        linha = linha_bruta.strip()
        if not linha:
            continue

        achado = _identificar_rotulo(linha)
        if achado:
            campo, valor = achado
            grupos.append((campo, [valor] if valor else []))
            campo_atual = campo
        elif campo_atual in CAMPOS_COM_CONTINUACAO and grupos:
            # Linha de continuação (endereço quebrado em várias linhas)
            grupos[-1][1].append(linha)

    def primeiro(campo):
        for c, partes in grupos:
            if c == campo:
                return " ".join(p for p in partes if p).strip()
        return ""

    nome = primeiro("nome")
    if nome:
        # Corta eventual continuação colada (ex.: nome + endereço)
        nome = nome.split(" - ")[0].strip()
        nome = re.sub(r"\s+", " ", nome)

    endereco = primeiro("endereco")
    endereco = re.sub(r"\s+", " ", endereco).strip(" ,;-")

    cidade_explicita = primeiro("cidade")
    cidade, uf = ("", "")
    if cidade_explicita:
        cidade, uf = _cidade_e_uf(cidade_explicita)

    endereco_sem_cidade, cidade_endereco, uf_endereco = _separar_cidade(endereco)
    if not cidade:
        cidade, uf = cidade_endereco, uf_endereco
    endereco = endereco_sem_cidade.strip(" ,;-")

    documento = _limpar_documento(primeiro("documento"))
    telefone = _limpar_telefone(primeiro("telefone"))
    cep = _limpar_cep(primeiro("cep"))

    resultado.update({
        "nome": nome,
        "documento": documento,
        "endereco": endereco,
        "cep": cep,
        "cidade": cidade,
        "uf": uf,
        "telefone": telefone,
        "destino": primeiro("destino"),
        "data_ida": primeiro("data_ida"),
        "data_volta": primeiro("data_volta"),
    })
    return resultado


def resumo_para_usuario(dados):
    """Monta um resumo curto do que foi identificado (para exibir na tela)."""
    partes = []
    if dados.get("destino") or dados.get("data_ida") or dados.get("data_volta"):
        partes.append(
            "Destino/datas são dados da viagem: informe na tela 'Novo Aluguel'."
        )
    return " ".join(partes)
