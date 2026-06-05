import sqlite3

# Verificar backup restaurado
conn = sqlite3.connect('mala_express_restored.db')
c = conn.cursor()

# Listar tabelas
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print("Tabelas no backup:", tables)

# Verificar alugueis
c.execute("SELECT COUNT(*) FROM alugueis")
count_alugueis = c.fetchone()[0]
print(f"\nTotal de alugueis: {count_alugueis}")

# Verificar total de fretes
c.execute("SELECT COALESCE(SUM(COALESCE(frete_calculado, 0)), 0) FROM alugueis WHERE status != 'Cancelado'")
total_fretes = c.fetchone()[0]
print(f"Total fretes (soma simples): R$ {total_fretes:.2f}")

# Verificar fretes únicos por cliente
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
total_fretes_unico = c.fetchone()[0]
print(f"Total fretes (únicos por cliente): R$ {total_fretes_unico:.2f}")

conn.close()
