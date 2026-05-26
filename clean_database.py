import os
import sqlite3
import json

def clean():
    print("=== DATABASE CLEANUP SCRIPT ===")
    
    # 1. Limpar active_pontos.json
    try:
        with open("active_pontos.json", "w", encoding="utf-8") as f:
            f.write("{}")
        print("Ficheiro active_pontos.json limpo com sucesso!")
    except Exception as e:
        print(f"Erro ao limpar active_pontos.json: {e}")

    # 2. Limpar tabelas da base de dados db.sqlite3 (mantendo configuracoes)
    db_files = ["db.sqlite3", "bate_ponto.db"]
    for db_file in db_files:
        if os.path.exists(db_file):
            try:
                conn = sqlite3.connect(db_file)
                cursor = conn.cursor()
                
                # Listar todas as tabelas
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                
                print(f"\nLimpando base de dados: {db_file}")
                for table in tables:
                    if table == "configuracoes" or table == "sqlite_sequence":
                        # Preservar a tabela de configurações e tabelas internas do SQLite
                        print(f"-> Preservando tabela: {table}")
                        continue
                    
                    try:
                        cursor.execute(f"DELETE FROM {table}")
                        print(f"-> Limpa tabela: {table}")
                    except Exception as e:
                        print(f"-> Erro ao limpar tabela {table}: {e}")
                
                conn.commit()
                conn.close()
                
                # Executar VACUUM fora de transação
                conn = sqlite3.connect(db_file, isolation_level=None)
                conn.execute("VACUUM")
                conn.close()
                print(f"Base de dados {db_file} limpa e otimizada (VACUUM) com sucesso!")
            except Exception as e:
                print(f"Erro ao limpar base de dados {db_file}: {e}")
        else:
            print(f"Base de dados {db_file} não encontrada (ignorando).")
            
    print("\nConcluído! O bot está limpo e pronto para o novo servidor!")

if __name__ == "__main__":
    clean()
