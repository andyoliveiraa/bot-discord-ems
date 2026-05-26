import aiosqlite
import json
import os
import time as _time

class Database:
    def __init__(self, db_connection):
        self.connector = db_connection

    async def setup_db(self):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS funcionarios (
                        user_id INTEGER PRIMARY KEY,
                        patente_id TEXT,
                        callsign TEXT,
                        nome TEXT
                    )
                ''')
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS tempo_semanal (
                        user_id INTEGER PRIMARY KEY,
                        tempo_total INTEGER DEFAULT 0
                    )
                ''')
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS pontos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        started INTEGER,
                        finished INTEGER,
                        staff_finished INTEGER DEFAULT 0,
                        duration INTEGER DEFAULT 0,
                        pauses TEXT DEFAULT "[]"
                    )
                ''')
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS semanas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        inicio INTEGER NOT NULL,
                        fim INTEGER,
                        encerrada INTEGER DEFAULT 0
                    )
                ''')
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS pagamentos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        semana_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        valor_calculado REAL DEFAULT 0,
                        pago INTEGER DEFAULT 0,
                        pago_em INTEGER,
                        pago_por INTEGER,
                        UNIQUE(semana_id, user_id)
                    )
                ''')

                # Schema migrations seguras
                for table, col_def in [
                    ('funcionarios', 'password_hash TEXT'),
                    ('funcionarios', 'reset_token TEXT'),
                    ('pontos', 'semana_id INTEGER'),
                ]:
                    try:
                        await cursor.execute(f'ALTER TABLE {table} ADD COLUMN {col_def}')
                    except Exception:
                        pass

                # Nova tabela de configurações dinâmicas
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS configuracoes (
                        chave TEXT PRIMARY KEY,
                        valor TEXT
                    )
                ''')

                # Nova tabela de Logs
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp INTEGER,
                        categoria TEXT,
                        user_id INTEGER,
                        mensagem TEXT,
                        detalhes TEXT,
                        cor TEXT
                    )
                ''')

            await conn.commit()

    # =========================================================
    # SISTEMA DE LOGS
    # =========================================================

    async def add_log(self, categoria: str, user_id: int, mensagem: str, detalhes=None, cor: str = 'info'):
        """
        Adiciona um log ao sistema.
        Categorias: 'geral', 'erro', 'comando', 'dashboard'
        """
        agora = int(_time.time())
        detalhes_str = json.dumps(detalhes, ensure_ascii=False) if detalhes else None
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('''
                    INSERT INTO logs (timestamp, categoria, user_id, mensagem, detalhes, cor)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (agora, categoria, user_id, mensagem, detalhes_str, cor))
            await conn.commit()

    async def get_logs(self, categoria: str = None, limit: int = 100):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                if categoria:
                    await cursor.execute(
                        'SELECT id, timestamp, categoria, user_id, mensagem, detalhes, cor '
                        'FROM logs WHERE categoria = ? ORDER BY id DESC LIMIT ?', (categoria, limit))
                else:
                    await cursor.execute(
                        'SELECT id, timestamp, categoria, user_id, mensagem, detalhes, cor '
                        'FROM logs ORDER BY id DESC LIMIT ?', (limit,))
                return await cursor.fetchall()

    # =========================================================
    # CONFIGURAÇÕES DINÂMICAS
    # =========================================================

    async def get_config(self, chave: str, default=None):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('SELECT valor FROM configuracoes WHERE chave = ?', (chave,))
                row = await cursor.fetchone()
                if row:
                    try:
                        return json.loads(row[0])
                    except:
                        return row[0]
                return default

    async def set_config(self, chave: str, valor):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                val_str = json.dumps(valor, ensure_ascii=False)
                await cursor.execute('''
                    INSERT INTO configuracoes (chave, valor) VALUES (?, ?)
                    ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor
                ''', (chave, val_str))
            await conn.commit()

    async def get_all_configs(self):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('SELECT chave, valor FROM configuracoes')
                rows = await cursor.fetchall()
                configs = {}
                for row in rows:
                    try:
                        configs[row[0]] = json.loads(row[1])
                    except:
                        configs[row[0]] = row[1]
                return configs

    async def migrate_from_json(self):
        """Migra as configurações do config.json para a BD se a BD estiver vazia."""
        configs = await self.get_all_configs()
        if not configs and os.path.exists('config.json'):
            try:
                with open('config.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for k, v in data.items():
                    await self.set_config(k, v)
                print("[DATABASE] Configurações migradas do config.json com sucesso.")
                return True
            except Exception as e:
                print(f"[DATABASE] Erro na migração: {e}")
        return False

    # =========================================================
    # FUNCIONÁRIOS
    # =========================================================

    async def add_funcionario(self, user_id: int, patente_id: str, callsign: str, nome: str):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('''
                    INSERT INTO funcionarios (user_id, patente_id, callsign, nome)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        patente_id=excluded.patente_id,
                        callsign=excluded.callsign,
                        nome=excluded.nome
                ''', (user_id, patente_id, callsign, nome))
            await conn.commit()

    async def remove_funcionario(self, user_id: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('DELETE FROM funcionarios WHERE user_id = ?', (user_id,))
            await conn.commit()

    async def get_funcionario(self, user_id: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'SELECT patente_id, callsign, nome, password_hash, reset_token FROM funcionarios WHERE user_id = ?',
                    (user_id,))
                return await cursor.fetchone()

    async def get_funcionario_by_callsign(self, callsign: str):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'SELECT user_id, patente_id, callsign, nome, password_hash FROM funcionarios WHERE callsign = ?',
                    (callsign,))
                return await cursor.fetchone()

    async def update_password(self, user_id: int, password_hash: str):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('UPDATE funcionarios SET password_hash = ? WHERE user_id = ?', (password_hash, user_id))
            await conn.commit()

    async def set_reset_token(self, user_id: int, token: str):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('UPDATE funcionarios SET reset_token = ? WHERE user_id = ?', (token, user_id))
            await conn.commit()

    async def get_funcionario_by_reset_token(self, token: str):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'SELECT user_id, patente_id, callsign, nome FROM funcionarios WHERE reset_token = ?', (token,))
                return await cursor.fetchone()

    async def get_all_funcionarios(self):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('SELECT user_id, patente_id, callsign, nome FROM funcionarios ORDER BY callsign ASC')
                return await cursor.fetchall()

    async def get_next_callsign(self, letra: str = None) -> str:
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('SELECT callsign FROM funcionarios')
                rows = await cursor.fetchall()
                numeros_existentes = []
                for row in rows:
                    try:
                        num = int(row[0])
                        numeros_existentes.append(num)
                    except Exception:
                        pass
                if not numeros_existentes:
                    return "1001"
                numeros_existentes.sort()
                proximo = 1001
                for num in numeros_existentes:
                    if num < 1001:
                        continue
                    if num == proximo:
                        proximo += 1
                    elif num > proximo:
                        break
                return str(proximo)

    async def shift_callsigns_down(self, letra: str, removido_num: int):
        if not letra:
            return []
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'SELECT user_id, callsign, nome FROM funcionarios WHERE callsign LIKE ? ORDER BY callsign ASC',
                    (f'{letra}-%',))
                rows = await cursor.fetchall()
                shifted = []
                for row in rows:
                    user_id, callsign, nome = row
                    try:
                        num = int(callsign.split('-')[1])
                        if num > removido_num:
                            novo_callsign = f"{letra}-{str(num - 1).zfill(2)}"
                            await cursor.execute(
                                'UPDATE funcionarios SET callsign = ? WHERE user_id = ?', (novo_callsign, user_id))
                            shifted.append((user_id, novo_callsign, nome))
                    except Exception:
                        pass
                await conn.commit()
                return shifted

    # =========================================================
    # TEMPO SEMANAL (semana activa)
    # =========================================================

    async def get_user_time(self, user_id: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('SELECT * FROM tempo_semanal WHERE user_id = ?', (user_id,))
                return await cursor.fetchone()

    async def get_ranking(self, amount: int = 10):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'SELECT * FROM tempo_semanal ORDER BY tempo_total DESC LIMIT ?', (amount,))
                return await cursor.fetchall()

    async def add_time(self, user_id: int, seconds: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('INSERT OR IGNORE INTO tempo_semanal(user_id) VALUES (?)', (user_id,))
                await cursor.execute(
                    'UPDATE tempo_semanal SET tempo_total = tempo_total + :s WHERE user_id = :u',
                    {'s': seconds, 'u': user_id})
                await conn.commit()
                return True

    async def set_time(self, user_id: int, seconds: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('INSERT OR IGNORE INTO tempo_semanal(user_id) VALUES (?)', (user_id,))
                await cursor.execute(
                    'UPDATE tempo_semanal SET tempo_total = :s WHERE user_id = :u',
                    {'s': seconds, 'u': user_id})
                await conn.commit()
                return True

    async def del_time(self, user_id: int, seconds: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'UPDATE tempo_semanal SET tempo_total = MAX(0, tempo_total - :s) WHERE user_id = :u',
                    {'s': seconds, 'u': user_id})
                await conn.commit()
                return True

    async def reset_all_times(self):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('UPDATE tempo_semanal SET tempo_total = 0')
                await conn.commit()

    # =========================================================
    # PONTOS (registros)
    # =========================================================

    async def create_registry(self, user_id: int, started: int, finished: int,
                               staff_finished: int = 0, duration: int = 0, pauses: str = "[]"):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'INSERT INTO pontos(user_id, started, finished, staff_finished, duration, pauses) VALUES (?,?,?,?,?,?)',
                    (user_id, started, finished, staff_finished, duration, pauses))
                await conn.commit()

    async def get_all_user_registries(self, user_id: int):
        """Pontos da semana activa (semana_id IS NULL) — para comandos Discord."""
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'SELECT started, finished, staff_finished, duration, pauses FROM pontos '
                    'WHERE user_id = ? AND semana_id IS NULL ORDER BY started ASC',
                    (user_id,))
                return await cursor.fetchall()

    async def get_all_user_registries_with_id(self, user_id: int):
        """Pontos da semana activa com ID — para edição no dashboard."""
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'SELECT id, started, finished, staff_finished, duration, pauses FROM pontos '
                    'WHERE user_id = ? AND semana_id IS NULL ORDER BY started ASC',
                    (user_id,))
                return await cursor.fetchall()

    async def get_pontos_semana_arquivo(self, semana_id: int, user_id: int):
        """Pontos de uma semana arquivada específica."""
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'SELECT id, started, finished, staff_finished, duration, pauses FROM pontos '
                    'WHERE user_id = ? AND semana_id = ? ORDER BY started ASC',
                    (user_id, semana_id))
                return await cursor.fetchall()

    async def get_ponto_by_id(self, ponto_id: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'SELECT id, user_id, started, finished, staff_finished, duration, pauses, semana_id '
                    'FROM pontos WHERE id = ?', (ponto_id,))
                return await cursor.fetchone()

    async def update_ponto_duration(self, ponto_id: int, new_duration: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('UPDATE pontos SET duration = ? WHERE id = ?', (new_duration, ponto_id))
            await conn.commit()

    async def update_ponto_times(self, ponto_id: int, started: int, finished: int, duration: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'UPDATE pontos SET started = ?, finished = ?, duration = ? WHERE id = ?',
                    (started, finished, duration, ponto_id)
                )
            await conn.commit()

    async def cancel_ponto(self, ponto_id: int, staff_id: int):
        """Cancela um ponto: duration=0, staff_finished=staff_id (não contabilizado)."""
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'UPDATE pontos SET duration = 0, staff_finished = ? WHERE id = ?', (staff_id, ponto_id))
            await conn.commit()

    async def reset_all_registries(self):
        """Apaga pontos da semana activa (legacy — usar encerrar_semana preferencialmente)."""
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('DELETE FROM pontos WHERE semana_id IS NULL')
                await conn.commit()

    # =========================================================
    # SEMANAS
    # =========================================================

    async def get_semana_activa(self):
        """Retorna (id, inicio, fim, encerrada) da semana activa ou None."""
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'SELECT id, inicio, fim, encerrada FROM semanas WHERE encerrada = 0 ORDER BY id DESC LIMIT 1')
                return await cursor.fetchone()

    async def get_or_criar_semana_activa(self):
        semana = await self.get_semana_activa()
        if semana:
            return semana
        inicio = int(_time.time())
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('INSERT INTO semanas (inicio) VALUES (?)', (inicio,))
                await conn.commit()
                return (cursor.lastrowid, inicio, None, 0)

    async def get_todas_semanas(self):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('SELECT id, inicio, fim, encerrada FROM semanas ORDER BY id DESC')
                return await cursor.fetchall()

    async def encerrar_semana(self, config_cargos: dict):
        """
        Encerra a semana activa:
        - Associa todos os pontos activos ao semana_id
        - Grava pagamentos calculados para cada funcionário
        - Retorna dict com semana_id e lista de pagamentos
        """
        agora = int(_time.time())

        # Garante que existe uma semana activa
        semana = await self.get_semana_activa()
        if not semana:
            async with aiosqlite.connect(self.connector) as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute('INSERT INTO semanas (inicio) VALUES (?)', (agora,))
                    await conn.commit()
                    semana_id = cursor.lastrowid
        else:
            semana_id = semana[0]

        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                # Encerra a semana
                await cursor.execute(
                    'UPDATE semanas SET fim = ?, encerrada = 1 WHERE id = ?', (agora, semana_id))

                # Associa todos os pontos activos à semana
                await cursor.execute(
                    'UPDATE pontos SET semana_id = ? WHERE semana_id IS NULL', (semana_id,))

                # Busca tempos para calcular pagamentos
                await cursor.execute('SELECT user_id, tempo_total FROM tempo_semanal WHERE tempo_total > 0')
                tempos = await cursor.fetchall()

                # Busca patentes dos funcionários
                await cursor.execute('SELECT user_id, patente_id FROM funcionarios')
                patentes_map = {row[0]: row[1] for row in await cursor.fetchall()}

                pagamentos_inseridos = []
                for user_id, tempo_total in tempos:
                    patente_id = patentes_map.get(user_id)
                    valor_hora = 0
                    if patente_id and patente_id in config_cargos:
                        valor_hora = config_cargos[patente_id].get('valor_hora', 0)
                    horas = int(tempo_total // 3600)
                    minutos = int((tempo_total % 3600) // 60)
                    mins_pagar = horas * 60 + minutos
                    valor = (mins_pagar / 60) * valor_hora

                    await cursor.execute('''
                        INSERT INTO pagamentos (semana_id, user_id, valor_calculado, pago)
                        VALUES (?, ?, ?, 0)
                        ON CONFLICT(semana_id, user_id) DO UPDATE SET valor_calculado = excluded.valor_calculado
                    ''', (semana_id, user_id, valor))
                    pagamentos_inseridos.append({'user_id': user_id, 'valor': valor})

                await conn.commit()

        return {'semana_id': semana_id, 'pagamentos': pagamentos_inseridos}

    # =========================================================
    # PAGAMENTOS
    # =========================================================

    async def get_pagamento(self, semana_id: int, user_id: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'SELECT id, semana_id, user_id, valor_calculado, pago, pago_em, pago_por '
                    'FROM pagamentos WHERE semana_id = ? AND user_id = ?',
                    (semana_id, user_id))
                return await cursor.fetchone()

    async def get_pagamentos_semana(self, semana_id: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'SELECT id, semana_id, user_id, valor_calculado, pago, pago_em, pago_por '
                    'FROM pagamentos WHERE semana_id = ? ORDER BY user_id',
                    (semana_id,))
                return await cursor.fetchall()

    async def get_pagamentos_user(self, user_id: int):
        """Todas as semanas arquivadas de um utilizador com estado de pagamento."""
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('''
                    SELECT p.id, p.semana_id, p.valor_calculado, p.pago, p.pago_em, p.pago_por,
                           s.inicio, s.fim
                    FROM pagamentos p
                    JOIN semanas s ON s.id = p.semana_id
                    WHERE p.user_id = ?
                    ORDER BY p.semana_id DESC
                ''', (user_id,))
                return await cursor.fetchall()

    async def marcar_pago(self, semana_id: int, user_id: int, pago_por: int):
        agora = int(_time.time())
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'UPDATE pagamentos SET pago = 1, pago_em = ?, pago_por = ? '
                    'WHERE semana_id = ? AND user_id = ?',
                    (agora, pago_por, semana_id, user_id))
            await conn.commit()

    async def get_semanas_com_impagos(self):
        """Retorna lista de (semana_id, user_id, valor_calculado) com pago=0."""
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('''
                    SELECT p.semana_id, p.user_id, p.valor_calculado, s.inicio, s.fim
                    FROM pagamentos p
                    JOIN semanas s ON s.id = p.semana_id
                    WHERE p.pago = 0 AND s.encerrada = 1
                    ORDER BY p.semana_id DESC
                ''')
                return await cursor.fetchall()

    async def get_config_db(self, chave: str):
        """Lê uma config extra guardada na BD."""
        return await self.get_config(chave)


def get_configs():
    """
    Tenta ler as configurações. 
    Nota: Como o bot usa async em quase tudo, o ideal é usar Database.get_all_configs().
    Este método síncrono é mantido para compatibilidade inicial mas deve ser evitado.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    configs = {}
    
    # 1. Tentar ler do config.json
    if os.path.exists('config.json'):
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                configs = json.load(f)
        except Exception as e:
            print(f"[GET_CONFIGS] Erro ao ler config.json: {e}")
            
    # 2. Se estiver vazio ou sem timezone, tentar ler da BD sqlite3 de forma síncrona
    if (not configs or "timezone" not in configs) and os.path.exists('db.sqlite3'):
        try:
            import sqlite3
            conn = sqlite3.connect('db.sqlite3')
            cursor = conn.cursor()
            # Verificar se a tabela configuracoes existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='configuracoes'")
            if cursor.fetchone():
                cursor.execute("SELECT chave, valor FROM configuracoes")
                rows = cursor.fetchall()
                for row in rows:
                    key, val = row[0], row[1]
                    try:
                        # Tentar fazer parse do JSON se aplicável
                        configs[key] = json.loads(val)
                    except Exception:
                        configs[key] = val
            conn.close()
        except Exception as e:
            print(f"[GET_CONFIGS] Erro ao ler db.sqlite3 de forma síncrona: {e}")
            
    # 3. Garantir valores padrão para evitar erros de importação/inicialização
    default_configs = {
        "timezone": "Europe/Lisbon",
        "staff_role_id": 0,
        "ponto_role_id": 0,
        "owner_id": 0,
        "log_channel_id": 0,
        "nome_corp": "EMS",
        "server_name": "EMS",
        "cargos_patentes": {}
    }
    
    for k, v in default_configs.items():
        if k not in configs or configs[k] is None:
            configs[k] = v
            
    # 4. Sobrescrever/complementar qualquer chave se a respectiva variável de ambiente estiver definida
    env_mappings = {
        "SERVER_NAME": ("server_name", str),
        "BOT_TOKEN": ("token", str),
        "TOKEN": ("token", str),
        "DISCORD_TOKEN": ("token", str),
        "token": ("token", str),
        "bot_token": ("token", str),
        "OWNER_ID": ("owner_id", int),
        "LOG_CHANNEL_ID": ("log_channel_id", int),
        "LOG_CONTRATACOES_ID": ("log_contratacoes_id", int),
        "STAFF_ROLE_ID": ("staff_role_id", int),
        "PONTO_ROLE_ID": ("ponto_role_id", int),
        "NOME_CORP": ("nome_corp", str),
        "TIMEZONE": ("timezone", str),
        "CARGO_EQUIPA_ID": ("cargo_equipa_id", int),
    }
    
    for env_key, (config_key, cast_type) in env_mappings.items():
        val = os.getenv(env_key)
        if val is not None and val.strip() != "":
            try:
                if cast_type == int:
                    configs[config_key] = int(val.strip())
                else:
                    configs[config_key] = val.strip()
            except Exception as e:
                print(f"[GET_CONFIGS] Erro ao converter {env_key} para {cast_type}: {e}")
                
    cargos_env = os.getenv("CARGOS_PATENTES")
    if cargos_env is not None and cargos_env.strip() != "":
        try:
            val_clean = cargos_env.strip()
            if (val_clean.startswith("'") and val_clean.endswith("'")) or (val_clean.startswith('"') and val_clean.endswith('"')):
                val_clean = val_clean[1:-1].strip()
            parsed = json.loads(val_clean)
            if isinstance(parsed, dict):
                configs["cargos_patentes"] = parsed
                print("[GET_CONFIGS] Configuração cargos_patentes carregada com sucesso do .env")
        except Exception as e:
            print(f"[GET_CONFIGS] Erro ao analisar CARGOS_PATENTES como JSON do .env: {e}")
            
    return configs



def save_configs(config: dict):
    """Guarda o config.json (obsoleto, mantido para evitar quebras imediatas)."""
    if os.path.exists('config.json'):
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)