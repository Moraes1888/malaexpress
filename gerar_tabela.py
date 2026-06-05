from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm

def criar_pdf():
    doc = SimpleDocTemplate("tabela_precos.pdf", pagesize=A4)
    elements = []

    # Estilos
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=12,
        textColor=colors.black
    )

    # Título
    # Removido emoji para evitar problemas de renderização com fontes padrão
    title = Paragraph("Tabela de Preços Comparativa", title_style)
    elements.append(title)
    elements.append(Spacer(1, 12))

    # Estilo para a célula selecionada
    # Usando HTML tags para colorir parte do texto
    cell_style = ParagraphStyle(
        'CellStyle',
        parent=styles['Normal'],
        fontSize=10,
        leading=12,
        alignment=1 # Center
    )
    
    # Texto "15 dias" e "<- Selecionado" (em azul)
    # Nota: A fonte Helvetica não suporta emojis, então usamos texto simples ou representação visual
    texto_selecionado = Paragraph('<b>15 dias</b> <font color="blue">&lt;- Selecionado</font>', styles['Normal'])

    # Dados da tabela
    data = [
        ['Dias', 'Tamanho P', 'Tamanho M', 'Tamanho G'],
        ['1 dia', 'R$ 18.00', 'R$ 25.00', 'R$ 28.00'],
        ['2 dias', 'R$ 36.00', 'R$ 50.00', 'R$ 56.00'],
        ['3 dias', 'R$ 54.00', 'R$ 75.00', 'R$ 84.00'],
        ['4 dias', 'R$ 65.00', 'R$ 90.00', 'R$ 100.00'],
        ['5 dias', 'R$ 68.33', 'R$ 93.33', 'R$ 106.67'],
        ['6 dias', 'R$ 71.67', 'R$ 96.67', 'R$ 113.33'],
        ['7 dias', 'R$ 75.00', 'R$ 100.00', 'R$ 120.00'],
        ['8 dias', 'R$ 77.61', 'R$ 103.09', 'R$ 123.52'],
        ['9 dias', 'R$ 80.22', 'R$ 106.17', 'R$ 127.04'],
        ['10 dias', 'R$ 82.83', 'R$ 109.26', 'R$ 130.57'],
        ['11 dias', 'R$ 85.43', 'R$ 112.35', 'R$ 134.09'],
        ['12 dias', 'R$ 88.04', 'R$ 115.43', 'R$ 137.61'],
        ['13 dias', 'R$ 90.65', 'R$ 118.52', 'R$ 141.13'],
        ['14 dias', 'R$ 93.26', 'R$ 121.61', 'R$ 144.65'],
        [texto_selecionado, 'R$ 95.87', 'R$ 124.70', 'R$ 148.17']
    ]

    # Criação da tabela
    t = Table(data, colWidths=[4.5*cm, 3.5*cm, 3.5*cm, 3.5*cm])

    # Definição das cores
    header_blue = colors.HexColor('#3F51B5')  # Azul similar ao header "Dias"
    p_blue = colors.HexColor('#1976D2')       # Azul "Tamanho P"
    m_purple = colors.HexColor('#9C27B0')     # Roxo "Tamanho M"
    g_red = colors.HexColor('#D32F2F')        # Vermelho "Tamanho G"
    
    text_p_blue = colors.HexColor('#1976D2')
    text_m_purple = colors.HexColor('#7B1FA2')
    text_g_red = colors.HexColor('#C62828')
    
    bg_selected = colors.HexColor('#FFF9C4') # Amarelo claro para linha selecionada

    # Estilização da tabela
    style = TableStyle([
        # Cabeçalho
        ('BACKGROUND', (0, 0), (0, 0), header_blue),
        ('BACKGROUND', (1, 0), (1, 0), p_blue),
        ('BACKGROUND', (2, 0), (2, 0), m_purple),
        ('BACKGROUND', (3, 0), (3, 0), g_red),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),

        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.lightgrey),

        # Corpo da tabela
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'), # Dias em negrito
        ('FONTNAME', (1, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 8),

        # Cores dos textos das colunas de preços
        ('TEXTCOLOR', (1, 1), (1, -1), text_p_blue),
        ('TEXTCOLOR', (2, 1), (2, -1), text_m_purple),
        ('TEXTCOLOR', (3, 1), (3, -1), text_g_red),

        # Linha selecionada (15 dias)
        ('BACKGROUND', (0, -1), (-1, -1), bg_selected),
        # A cor do texto da primeira célula da última linha é controlada pelo Paragraph
        # As outras células mantêm a cor definida acima
    ])

    t.setStyle(style)
    elements.append(t)

    # Gerar PDF
    doc.build(elements)
    print("PDF gerado com sucesso: tabela_precos.pdf")

if __name__ == "__main__":
    criar_pdf()
