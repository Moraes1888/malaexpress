import sqlite3
import pandas as pd

conn = sqlite3.connect("mala_express.db")
query = "SELECT a.id, c.nome, a.status, a.data_saida, a.data_prevista_retorno FROM alugueis a JOIN clientes c ON a.cliente_id = c.id WHERE c.nome LIKE '%Alessandra%'"
df = pd.read_sql(query, conn)
if df.empty:
    print("Nenhuma reserva encontrada para Alessandra.")
else:
    print(df)
conn.close()