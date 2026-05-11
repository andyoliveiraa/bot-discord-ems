import aiosqlite
import json

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
            await conn.commit()

    async def add_funcionario(self, user_id: int, patente_id: str, callsign: str, nome: str):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('INSERT OR REPLACE INTO funcionarios (user_id, patente_id, callsign, nome) VALUES (?, ?, ?, ?)',
                                     (user_id, patente_id, callsign, nome))
            await conn.commit()

    async def remove_funcionario(self, user_id: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('DELETE FROM funcionarios WHERE user_id = ?', (user_id,))
            await conn.commit()

    async def get_funcionario(self, user_id: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('SELECT patente_id, callsign, nome FROM funcionarios WHERE user_id = ?', (user_id,))
                return await cursor.fetchone()

    async def get_all_funcionarios(self):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('SELECT user_id, patente_id, callsign, nome FROM funcionarios')
                return await cursor.fetchall()

    async def get_next_callsign(self, letra: str) -> str:
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('SELECT callsign FROM funcionarios WHERE callsign LIKE ? ORDER BY callsign ASC', (f'{letra}-%',))
                rows = await cursor.fetchall()
                
                # Encontrar o primeiro número disponível
                numeros_existentes = []
                for row in rows:
                    try:
                        num = int(row[0].split('-')[1])
                        numeros_existentes.append(num)
                    except:
                        pass
                
                numeros_existentes.sort()
                proximo = 1
                for num in numeros_existentes:
                    if num == proximo:
                        proximo += 1
                    elif num > proximo:
                        break
                
                return f"{letra}-{str(proximo).zfill(2)}"

    async def get_user_time(self, user_id: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('SELECT * FROM tempo_semanal WHERE user_id = ?', (user_id, ))
                return await cursor.fetchone()

    async def get_ranking(self, amount: int = 10):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('SELECT * FROM tempo_semanal ORDER BY tempo_total DESC LIMIT ?', (amount, ))
                return await cursor.fetchall()

    async def add_time(self, user_id: int, seconds: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('INSERT OR IGNORE INTO tempo_semanal(user_id) VALUES (?)', (user_id, ))  # Cria a conta caso não exista
                await cursor.execute('UPDATE tempo_semanal SET tempo_total = tempo_total + :seconds WHERE user_id = :user',
                    {'seconds': seconds, 'user': user_id})
                await conn.commit()
                return True

    async def set_time(self, user_id: int, seconds: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('INSERT OR IGNORE INTO tempo_semanal(user_id) VALUES (?)', (user_id, ))  # Cria a conta caso não exista
                await cursor.execute('UPDATE tempo_semanal SET tempo_total = :seconds WHERE user_id = :user',
                    {'seconds': seconds, 'user': user_id})
                await conn.commit()
                return True

    async def del_time(self, user_id: int, seconds: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('UPDATE tempo_semanal SET tempo_total = tempo_total - :seconds WHERE user_id = :user',
                    {'seconds': seconds, 'user': user_id})
                await conn.commit()
                return True

    async def reset_all_times(self):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('UPDATE tempo_semanal SET tempo_total = 0')
                await conn.commit()

    async def create_registry(self, user_id: int, started: int, finished: int, staff_finished: int = 0, duration: int = 0, pauses: str = "[]"):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('INSERT INTO pontos(user_id, started, finished, staff_finished, duration, pauses) VALUES (?, ?, ?, ?, ?, ?)',
                    (user_id, started, finished, staff_finished, duration, pauses))
                await conn.commit()

    async def get_all_user_registries(self, user_id: int):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('SELECT started, finished, staff_finished, duration, pauses FROM pontos WHERE user_id = ? ORDER BY started ASC', (user_id, ))
                return await cursor.fetchall()

    async def reset_all_registries(self):
        async with aiosqlite.connect(self.connector) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('DELETE FROM pontos')
                await cursor.execute('UPDATE sqlite_sequence set seq = 0 WHERE name = "pontos"')
                await conn.commit()

def get_configs():
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    return config