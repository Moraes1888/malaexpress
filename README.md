# MalaExpress - Sistema de Gestão de Aluguel de Malas

Este é um sistema completo desenvolvido em Python com Streamlit para gerenciar o negócio de aluguel de malas de viagem.

## 🚀 Funcionalidades Principais

### 1. Dashboard
- Visão geral do estoque (Total de Malas, Disponíveis Hoje).
- Taxa de ocupação visual.
- Aluguéis ativos no momento.
- Galeria visual das malas disponíveis.

### 2. Cadastro
- **Malas:** Cadastro completo com código automático, marca, cor, tamanho (P, M, G ou Personalizado), valor de compra e foto. Suporta upload de imagens `.jpg`, `.png`, `.heic` (iPhone).
- **Clientes:** Cadastro simplificado com Nome, CPF e CEP.
- **Gerenciamento:** Abas para Editar ou Excluir malas e clientes já cadastrados.

### 3. Novo Aluguel
- Seleção visual da mala e do cliente.
- Definição de datas de retirada e devolução.
- **Segurança:** O sistema impede automaticamente alugar uma mala que já está reservada para o período escolhido.
- **Financeiro:** Registro do Valor Total e do Valor de Sinal (Reserva). Opção de marcar como pago total ou parcial.

### 4. Devoluções e Gestão
- Visualização em Cards (Cartões) de todos os aluguéis ativos.
- **Ações Rápidas:**
    - `✅ Registrar Devolução`: Finaliza o aluguel, libera a mala para estoque e gera comprovante PDF.
    - `💰 Financeiro`: Permite ajustar valores e mudar status de pagamento (Pendente -> Pago).
    - `🔄 Trocar Mala`: Corrige se a mala foi selecionada errada, trocando por outra disponível.
    - `❌ Cancelar`: Cancela o aluguel em caso de desistência (remove do financeiro).

### 5. Calendário de Reservas
- Visualização mensal estilo agenda.
- **Legenda de Cores:**
    - 🔴 Bolinha Vermelha: Dia da Retirada.
    - 🔵 Bolinha Azul: Dia da Devolução.
    - 🟩 Barra Verde: Período alugado.
- Filtro por mês e opção de baixar **PDF do Cronograma** mensal.

### 6. Análise Financeira
- **Relatório Geral:** Total Recebido (Caixa), Aluguéis Concluídos e Lucro Líquido Total.
- **Gráficos:**
    - 🍕 Pizza: Quais malas faturam mais (participação).
    - 📊 Barras: Comparativo de Investimento x Faturamento por tamanho (P/M/G).
- Tabela detalhada com ROI (Retorno sobre Investimento) de cada mala.

## 🛠️ Tecnologias Utilizadas
- **Python**: Linguagem principal.
- **Streamlit**: Interface web interativa.
- **SQLite**: Banco de dados local (não precisa de servidor).
- **Pandas**: Análise de dados e tabelas.
- **Plotly**: Gráficos interativos.
- **FPDF**: Geração de relatórios em PDF.
- **Pillow / Pillow-Heif**: Processamento de imagens.

## 📂 Como Iniciar
O sistema está configurado para iniciar automaticamente com o Windows. Caso precise abrir manualmente:
1. Clique no atalho **"MalaExpress"** na Área de Trabalho.
   OU
2. Abra a pasta do projeto e execute o arquivo `INICIAR_SISTEMA.bat`.

## ⚠️ Notas Importantes
- **Backup:** O banco de dados é o arquivo `mala_express.db`. Faça cópias dele regularmente para segurança.
- **Imagens:** As fotos das malas ficam na pasta `imagens_malas`. Não apague essa pasta manualmente.
