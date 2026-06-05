import sqlite3
conn = sqlite3.connect('mala_express.db')
c = conn.cursor()

# Buscar cliente Adriel
c.execute("SELECT id, nome, telefone FROM clientes WHERE nome LIKE '%Adriel%'")
clientes = c.fetchall()
print(f"Clientes encontrados com 'Adriel': {len(clientes)}")
for cli in clientes:
    print(f"  ID {cli[0]}: {cli[1]} - Tel: {cli[2]}")

    # Buscar aluguéis desse cliente
    c.execute('''
        SELECT a.id, a.data_saida, a.data_prevista_retorno, a.valor, a.status, m.codigo
        FROM alugueis a
        JOIN malas m ON a.mala_id = m.id
        WHERE a.cliente_id = ?
        ORDER BY a.data_saida DESC
    ''', (cli[0],))
    alugueis = c.fetchall()
    print(f"  Aluguéis ({len(alugueis)}):")
    for a in alugueis:
        print(f"    ID {a[0]}: {a[1]} a {a[2]} - R$ {a[3]} - Status: {a[4]} - Mala: {a[5]}")

conn.close()
