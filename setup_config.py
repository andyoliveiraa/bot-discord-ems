import os
import json
import sqlite3

def setup():
    print("=== CONFIGURATION SETUP SCRIPT ===")
    
    # 1. Carregar variáveis do .env manualmente para ser extremamente robusto
    env_vars = {}
    if os.path.exists('.env'):
        with open('.env', 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        current_key = None
        current_val = []
        in_multiline = False
        
        for line in lines:
            line_str = line.strip()
            if not line_str or line_str.startswith('#'):
                continue
                
            # Se já estivermos lendo uma variável multilinha
            if in_multiline:
                current_val.append(line)
                if line_str.endswith("'") or line_str.endswith('"'):
                    in_multiline = False
                    val_str = "".join(current_val).strip()
                    # Remover aspas externas se existirem
                    if (val_str.startswith("'") and val_str.endswith("'")) or (val_str.startswith('"') and val_str.endswith('"')):
                        val_str = val_str[1:-1].strip()
                    env_vars[current_key] = val_str
                continue
            
            if '=' in line:
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip()
                
                # Detectar início de valor multilinha (se começar com aspa simples/dupla e não fechar na mesma linha)
                if (val.startswith("'") and not val.endswith("'")) or (val.startswith('"') and not val.endswith('"')):
                    in_multiline = True
                    current_key = key
                    current_val = [val]
                else:
                    # Remover aspas externas de valores de linha única
                    if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
                        val = val[1:-1].strip()
                    env_vars[key] = val
                    
        print(f"Lidas {len(env_vars)} variáveis do .env")
    else:
        print("Erro: Arquivo .env não encontrado!")
        return

    # Mapeamento e conversão de tipos
    configs_to_save = {}
    
    # Mapear chaves do .env para as chaves internas
    mappings = {
        "SERVER_NAME": "server_name",
        "NOME_CORP": "nome_corp",
        "TIMEZONE": "timezone",
        "OWNER_ID": "owner_id",
        "LOG_CHANNEL_ID": "log_channel_id",
        "LOG_CONTRATACOES_ID": "log_contratacoes_id",
        "STAFF_ROLE_ID": "staff_role_id",
        "PONTO_ROLE_ID": "ponto_role_id",
        "CARGO_EQUIPA_ID": "cargo_equipa_id",
        "BOT_TOKEN": "token",
        "TOKEN": "token"
    }
    
    for env_key, config_key in mappings.items():
        if env_key in env_vars:
            val = env_vars[env_key]
            # Tentar converter para int se for ID numérico
            if '_id' in config_key or 'role' in config_key or config_key == 'owner_id':
                try:
                    configs_to_save[config_key] = int(val)
                except ValueError:
                    configs_to_save[config_key] = val
            else:
                configs_to_save[config_key] = val

    # Tratar cargos_patentes
    if "CARGOS_PATENTES" in env_vars:
        cargos_raw = env_vars["CARGOS_PATENTES"]
        try:
            parsed = json.loads(cargos_raw)
            if isinstance(parsed, dict):
                # Garantir que todos os IDs dentro de cargos_patentes são inteiros
                for k, v in parsed.items():
                    if isinstance(v, dict) and "id" in v:
                        try:
                            v["id"] = int(v["id"])
                        except:
                            pass
                configs_to_save["cargos_patentes"] = parsed
                print("Configuração cargos_patentes carregada e validada com sucesso.")
        except Exception as e:
            print(f"Aviso: Erro ao decodificar CARGOS_PATENTES do .env: {e}")

    if not configs_to_save:
        print("Nenhuma configuração válida para guardar.")
        return

    # 2. Gravar no ficheiro config.json
    try:
        # Se config.json existir, mesclar os dados para manter outras chaves
        existing_json = {}
        if os.path.exists('config.json'):
            try:
                with open('config.json', 'r', encoding='utf-8') as f:
                    existing_json = json.load(f)
            except:
                pass
        
        existing_json.update(configs_to_save)
        
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(existing_json, f, ensure_ascii=False, indent=4)
        print("Gravado config.json com sucesso!")
    except Exception as e:
        print(f"Erro ao gravar config.json: {e}")

    # 3. Gravar no db.sqlite3
    if os.path.exists('db.sqlite3'):
        try:
            conn = sqlite3.connect('db.sqlite3')
            cursor = conn.cursor()
            
            # Garantir que a tabela existe
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS configuracoes (
                    chave TEXT PRIMARY KEY,
                    valor TEXT
                )
            ''')
            
            for k, v in configs_to_save.items():
                val_str = json.dumps(v, ensure_ascii=False)
                cursor.execute('''
                    INSERT INTO configuracoes (chave, valor) VALUES (?, ?)
                    ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor
                ''', (k, val_str))
                
            conn.commit()
            conn.close()
            print("Configurações importadas para a base de dados db.sqlite3 com sucesso!")
        except Exception as e:
            print(f"Erro ao gravar na base de dados db.sqlite3: {e}")
    else:
        print("Aviso: db.sqlite3 não encontrado na pasta atual (será criado na inicialização).")

    print("\nConcluído! A sua configuração foi limpa, validada e aplicada com sucesso a todas as fontes.")

if __name__ == "__main__":
    setup()
