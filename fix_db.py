import sqlite3

def fix_database():
    conn = sqlite3.connect('mala_express.db')
    c = conn.cursor()
    
    # Atualizar todos os aluguéis pendentes para 'Pago'
    # Isso restaura os valores antigos que sumiram
    c.execute("UPDATE alugueis SET status_pagamento = 'Pago' WHERE status_pagamento = 'Pendente'")
    
    conn.commit()
    conn.close()
    print("Banco de dados atualizado com sucesso!")

if __name__ == "__main__":
    fix_database()
