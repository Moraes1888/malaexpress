import database as db
import pandas as pd
from datetime import timedelta

# Simular a lógica do app.py
df_reservas = db.get_todos_alugueis()

# Converter colunas de data para datetime
df_reservas['data_saida'] = pd.to_datetime(df_reservas['data_saida'])
df_reservas['data_prevista_retorno'] = pd.to_datetime(df_reservas['data_prevista_retorno'])

events = []

for _, row in df_reservas.iterrows():
    if "Alessandra" in row['cliente_nome']:
        titulo_evento = f"{row['mala_codigo']} | {row['cliente_nome']}"
        
        # Evento de Retirada (Vermelho)
        events.append({
            "title": f"📍 Retirada: {row['mala_codigo']}",
            "start": row['data_saida'].strftime('%Y-%m-%d'),
            "end": row['data_saida'].strftime('%Y-%m-%d'),
            "color": "#FF4B4B"
        })
        
        # Evento de Devolução (Azul)
        events.append({
            "title": f"🏁 Devolução: {row['mala_codigo']}",
            "start": row['data_prevista_retorno'].strftime('%Y-%m-%d'),
            "end": row['data_prevista_retorno'].strftime('%Y-%m-%d'),
            "color": "#1E90FF"
        })
        
        # Evento de Aluguel (Barra contínua)
        data_fim_cal = (row['data_prevista_retorno'] + timedelta(days=1)).strftime('%Y-%m-%d')
        
        events.append({
            "title": titulo_evento,
            "start": row['data_saida'].strftime('%Y-%m-%d'),
            "end": data_fim_cal,
            "color": "#28a745",
            "allDay": True
        })

print(f"Total de eventos da Alessandra: {len(events)}")
for e in events:
    print(e)
