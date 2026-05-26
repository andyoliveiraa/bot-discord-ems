import datetime
import asyncio
import discord
from discord.commands import Option
from discord.ext import commands, tasks
from discord.ui import View, InputText, Modal
from pytz import timezone
import json
import re
import secrets
import string
from werkzeug.security import generate_password_hash
from db import Database, get_configs

db = Database('db.sqlite3')
config = get_configs()

active_pontos = {}
active_pontos_version = 0
ACTIVE_PONTOS_FILE = "active_pontos.json"

def formatar_moeda(valor: float) -> str:
    return f"{valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') + " €"

def formatar_moeda_pdf(valor: float) -> str:
    return f"{valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') + " EUR"

async def gerar_pdf_semanal(top_todos, guild):
    try:
        from fpdf import FPDF
    except ImportError:
        return None
        
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=15)
    pdf.cell(200, 10, txt="Relatorio Semanal de Horas e Pagamentos", ln=1, align='C')
    pdf.set_font("Arial", size=11)
    
    total_semana_geral = 0
    total_pagamento_geral = 0
    
    for user_data in top_todos:
        user_id = user_data[0]
        total_seg = user_data[1]
        
        func_db = await db.get_funcionario(user_id)
        valor_hora = 0
        nome_func = f"ID: {user_id}"
        if func_db:
            patente_info = config.get("cargos_patentes", {}).get(func_db[0])
            if patente_info:
                valor_hora = patente_info.get("valor_hora", 0)
            nome_func = f"[{func_db[1]}] {func_db[2]}"
        else:
            membro = guild.get_member(user_id)
            if membro:
                nome_func = membro.display_name
                
        horas_total = int(total_seg // 3600)
        minutos_total = int((total_seg % 3600) // 60)
        
        mins_pagar = horas_total * 60 + minutos_total
        pagamento_semana = (mins_pagar / 60) * valor_hora
        total_semana_geral += (mins_pagar * 60)
        total_pagamento_geral += pagamento_semana
        
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 10, txt=f"Funcionario: {nome_func}", ln=1, align='L')
        pdf.set_font("Arial", size=11)
        pdf.cell(200, 8, txt=f"Total Semana: {horas_total}h {minutos_total}m - A receber: {formatar_moeda_pdf(pagamento_semana)}", ln=1, align='L')
        
        registros = await db.get_all_user_registries(user_id)
        por_dia = {}
        nao_contabilizados = []
        for reg in registros:
            data_str = datetime.datetime.fromtimestamp(reg[0], obter_timezone()).strftime("%d/%m/%Y")
            por_dia[data_str] = por_dia.get(data_str, 0) + (reg[3] or 0)
            
            if reg[3] == 0 and reg[2] and reg[2] > 10000:
                nao_contabilizados.append((data_str, reg[2]))
            
        for dia, seg_dia in sorted(por_dia.items()):
            if seg_dia == 0: continue
            sign = "-" if seg_dia < 0 else ""
            abs_seg = abs(seg_dia)
            h_dia = int(abs_seg // 3600)
            m_dia = int((abs_seg % 3600) // 60)
            mins_dia_pagar = h_dia * 60 + m_dia
            pagamento_dia = (mins_dia_pagar / 60) * valor_hora * (-1 if seg_dia < 0 else 1)
            pdf.cell(200, 6, txt=f"  - {dia}: {sign}{h_dia}h {m_dia}m | A receber: {formatar_moeda_pdf(pagamento_dia)}", ln=1, align='L')
            
        for nc in nao_contabilizados:
            data_str, staff_id = nc
            membro = guild.get_member(staff_id)
            nome_staff = membro.display_name if membro else f"ID: {staff_id}"
            pdf.cell(200, 6, txt=f"  - {data_str}: 0h 0m | Fechado (Nao Contabilizado) por {nome_staff}", ln=1, align='L')
            
        pdf.cell(200, 5, txt="", ln=1)
        
    pdf.set_font("Arial", 'B', 13)
    pdf.cell(200, 10, txt="RESUMO DA SEMANA", ln=1, align='C')
    h_geral = int(total_semana_geral // 3600)
    m_geral = int((total_semana_geral % 3600) // 60)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Total de Horas Trabalhadas: {h_geral}h {m_geral}m", ln=1, align='L')
    pdf.cell(200, 10, txt=f"Total a Pagar: {formatar_moeda_pdf(total_pagamento_geral)}", ln=1, align='L')
    
    file_path = "relatorio_semanal.pdf"
    await asyncio.to_thread(pdf.output, file_path)
    return file_path

def save_active_pontos():
    global active_pontos_version
    active_pontos_version += 1
    import json
    with open(ACTIVE_PONTOS_FILE, "w") as f:
        json.dump(active_pontos, f)

def obter_timezone():
    tz_str = config.get("timezone", "Europe/Lisbon") if isinstance(config, dict) else "Europe/Lisbon"
    if not tz_str:
        tz_str = "Europe/Lisbon"
    try:
        return timezone(tz_str)
    except Exception:
        return timezone("Europe/Lisbon")

def has_staff_role():
    async def predicate(ctx):
        owner_id = config.get('owner_id')
        if owner_id and ctx.author.id == int(owner_id):
            return True
            
        staff_role_id = config.get('staff_role_id')
        if not staff_role_id:
            raise commands.MissingAnyRole([0])
            
        role = ctx.guild.get_role(int(staff_role_id)) if ctx.guild else None
        if role and role in ctx.author.roles:
            return True
            
        raise commands.MissingAnyRole([int(staff_role_id)])
    return commands.check(predicate)

class PicaPonto(commands.Cog):
    def __init__(self, client):
        self.client = client

    def cog_unload(self):
        self.auto_close_task.cancel()
        self.auto_backup_task.cancel()
        self.auto_register_task.cancel()

    @tasks.loop(minutes=5)
    async def auto_close_task(self):
        agora = int(datetime.datetime.now(obter_timezone()).timestamp())
        for user_id, estado in list(active_pontos.items()):
            if agora - estado["inicio"] >= 86400: # 24 horas inativo
                horario_inicio = estado["inicio"]
                user = self.client.get_user(user_id)
                if user is None:
                    for guild in self.client.guilds:
                        user = guild.get_member(user_id)
                        if user: break
                
                if estado["status"] == "pausado":
                    estado["pausas"].append([estado["inicio_pausa"], agora])
                active_pontos.pop(user_id)
                save_active_pontos()
                
                await db.create_registry(int(user_id), horario_inicio, agora, True, 0, json.dumps(estado["pausas"]))
                
                canal_log = self.client.get_channel(config["log_channel_id"])
                if canal_log and user:
                    data_abertura = datetime.datetime.fromtimestamp(horario_inicio, obter_timezone()).strftime("%d/%m/%Y, %H:%M:%S")
                    embed_log = discord.Embed(description=f'**→ `Status Pica-Ponto`: Fechado Automatically (24h Inactivity)** *(horas não contabilizadas)*\n**→ `Funcionário`: {user.mention}**\n'
                        f'**→ `Horário de Abertura`: {data_abertura}**\n'
                        f'**→ `Horário de Fechamento`: {datetime.datetime.now(obter_timezone()).strftime("%d/%m/%Y, %H:%M:%S")}**\n**→ `Tempo total de serviço`: 00 horas e 00 minutos**', colour=discord.Colour.dark_gray())
                    embed_log.set_author(name='LOG: Inatividade Detectada', icon_url=self.client.user.display_avatar)
                    await canal_log.send(embed=embed_log)
                    try:
                        await user.send(f'**<:aviso:1269036173381206132> AVISO:** Seu pica-ponto foi finalizado automaticamente por exceder 24 horas de inatividade!\n<:sirene:1269032464374829087> Suas horas não foram contabilizadas.')
                    except: pass

    @auto_close_task.before_loop
    async def before_auto_close_task(self):
        await self.client.wait_until_ready()

    @tasks.loop(time=datetime.time(hour=7, minute=0, tzinfo=obter_timezone()))
    async def auto_backup_task(self):
        canal_log = self.client.get_channel(config["log_channel_id"])
        if canal_log:
            try:
                await canal_log.send(
                    content='**💽 Backup Automático Diário (07:00)**',
                    file=discord.File('db.sqlite3')
                )
            except Exception as e:
                print(f"Erro ao enviar backup automático no log: {e}")

        dono_id = config.get("owner_id")
        if dono_id:
            dono = self.client.get_user(dono_id)
            if not dono:
                try:
                    dono = await self.client.fetch_user(dono_id)
                except:
                    pass
            
            if dono:
                try:
                    await dono.send(
                        content='**💽 Backup Automático Diário (07:00)**',
                        file=discord.File('db.sqlite3')
                    )
                except Exception as e:
                    print(f"Erro ao enviar backup automático para o dono: {e}")

    @auto_backup_task.before_loop
    async def before_auto_backup_task(self):
        await self.client.wait_until_ready()

    @tasks.loop(minutes=10)
    async def auto_register_task(self):
        for guild in self.client.guilds:
            funcionarios_db = await db.get_all_funcionarios()
            ids_registrados = [f[0] for f in funcionarios_db]

            for member in guild.members:
                if member.bot:
                    continue

                # Obter patente correspondente ao cargo atual
                patente_atual_key = None
                patente_atual_info = None
                for p_key, p_info in config.get("cargos_patentes", {}).items():
                    if p_info.get("id") and any(r.id == int(p_info["id"]) for r in member.roles):
                        patente_atual_key = p_key
                        patente_atual_info = p_info
                        break

                if not patente_atual_key:
                    continue # Não tem patente

                func_db = next((f for f in funcionarios_db if f[0] == member.id), None)
                
                if not func_db:
                    # Tenta extrair callsign e nome do nick: [Callsign] Nome
                    nick_atual = member.display_name
                    match = re.match(r'^\[(.*?)\]\s+(.*)', nick_atual)
                    
                    if match:
                        callsign = match.group(1)
                        nome = match.group(2)
                    else:
                        continue

                    letra_correta = patente_atual_info["letra"]
                    try:
                        ext_letra = callsign.split('-')[0]
                    except:
                        ext_letra = ""
                        
                    callsign_is_taken = any(f[2] == callsign for f in funcionarios_db)
                    
                    if ext_letra != letra_correta or callsign_is_taken:
                        novo_callsign = await db.get_next_callsign(letra_correta)
                        await db.add_funcionario(member.id, patente_atual_key, novo_callsign, nome)
                        
                        try:
                            await member.edit(nick=f"[{novo_callsign}] {nome}")
                        except:
                            pass
                            
                        log_canal_id = config.get("log_contratacoes_id")
                        if log_canal_id:
                            log_canal = guild.get_channel(log_canal_id)
                            if log_canal:
                                embed_log = discord.Embed(
                                    title='LOG: Auto-Correção e Registro',
                                    description=f'**→ `Sistema`: Auto-Correção (Novo Registro)**\n**→ `Funcionário`: {member.mention}**\n**→ `Callsign Extraído`: {callsign} (Incorreto/Ocupado)**\n**→ `Novo Callsign`: {novo_callsign}**\n**→ `Nova Patente`: {patente_atual_info["nome"]}**',
                                    colour=discord.Colour.blue()
                                )
                                await log_canal.send(embed=embed_log)
                    else:
                        await db.add_funcionario(member.id, patente_atual_key, callsign, nome)
                        
                        log_canal_id = config.get("log_contratacoes_id")
                        if log_canal_id:
                            log_canal = guild.get_channel(log_canal_id)
                            if log_canal:
                                embed_log = discord.Embed(
                                    title='LOG: Auto-Registro Efetuado',
                                    description=f'**→ `Sistema`: Auto-Registro**\n**→ `Funcionário`: {member.mention}**\n**→ `Patente Detectada`: {patente_atual_info["nome"]}**\n**→ `Callsign`: {callsign}**',
                                    colour=discord.Colour.green()
                                )
                                await log_canal.send(embed=embed_log)
                else:
                    velho_callsign = func_db[2]
                    try:
                        velha_letra, velho_num_str = velho_callsign.split('-')
                        velho_num = int(velho_num_str)
                    except:
                        continue
                        
                    letra_correta = patente_atual_info["letra"]
                    
                    if velha_letra != letra_correta:
                        novo_callsign = await db.get_next_callsign(letra_correta)
                        nome_func = func_db[3]
                        
                        await db.add_funcionario(member.id, patente_atual_key, novo_callsign, nome_func)
                        
                        shifted_users = await db.shift_callsigns_down(velha_letra, velho_num)
                        for s_user_id, s_novo_callsign, s_nome in shifted_users:
                            try:
                                s_member = guild.get_member(s_user_id) or await guild.fetch_member(s_user_id)
                                await s_member.edit(nick=f"[{s_novo_callsign}] {s_nome}")
                            except:
                                pass
                        
                        try:
                            await member.edit(nick=f"[{novo_callsign}] {nome_func}")
                        except:
                            pass
                            
                        log_canal_id = config.get("log_contratacoes_id")
                        if log_canal_id:
                            log_canal = guild.get_channel(log_canal_id)
                            if log_canal:
                                embed_log = discord.Embed(
                                    title='LOG: Auto-Correção de Callsign',
                                    description=f'**→ `Sistema`: Auto-Correção**\n**→ `Funcionário`: {member.mention}**\n**→ `Callsign Antigo`: {velho_callsign}**\n**→ `Novo Callsign`: {novo_callsign}**\n**→ `Nova Patente`: {patente_atual_info["nome"]}**',
                                    colour=discord.Colour.blue()
                                )
                                await log_canal.send(embed=embed_log)
                    else:
                        nick_esperado = f"[{velho_callsign}] {func_db[3]}"
                        if member.display_name != nick_esperado:
                            try:
                                await member.edit(nick=nick_esperado)
                            except:
                                pass

    @auto_register_task.before_loop
    async def before_auto_register_task(self):
        await self.client.wait_until_ready()

    @tasks.loop(time=datetime.time(hour=9, minute=0, tzinfo=obter_timezone()))
    async def auto_lembrete_pagamentos_task(self):
        """Envia lembrete diário no canal de log sobre funcionários por pagar."""
        impagos = await db.get_semanas_com_impagos()
        if not impagos:
            return

        canal_log = self.client.get_channel(config["log_channel_id"])
        if not canal_log:
            return

        # Agrupa por semana
        semanas_dict = {}
        for semana_id, user_id, valor, inicio, fim in impagos:
            if semana_id not in semanas_dict:
                semanas_dict[semana_id] = {'inicio': inicio, 'fim': fim, 'funcionarios': []}
            semanas_dict[semana_id]['funcionarios'].append((user_id, valor))

        def formatar_moeda_local(v):
            return f"{v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') + " €"

        for semana_id, dados in semanas_dict.items():
            inicio_str = datetime.datetime.fromtimestamp(
                dados['inicio'], obter_timezone()).strftime('%d/%m/%Y')
            fim_str = datetime.datetime.fromtimestamp(
                dados['fim'], obter_timezone()).strftime('%d/%m/%Y') if dados['fim'] else 'N/A'

            desc = f'**⚠️ Semana `{inicio_str}` → `{fim_str}` tem funcionários por pagar:**\n\n'
            total_em_divida = 0
            for user_id, valor in dados['funcionarios']:
                func = await db.get_funcionario(user_id)
                if func:
                    nome_exib = f"[{func[1]}] {func[2]}"
                else:
                    membro = self.client.get_user(user_id)
                    nome_exib = membro.display_name if membro else f"ID: {user_id}"
                    
                desc += f'**→** **{nome_exib}** — `{formatar_moeda_local(valor)}`\n'
                total_em_divida += valor
            desc += f'\n**💰 Total em dívida:** `{formatar_moeda_local(total_em_divida)}`'
            desc += f'\n\n*Marque como pago no painel: `https://ems.discloud.app/admin/definicoes`*'

            embed = discord.Embed(
                title='💳 Lembrete de Pagamentos em Falta',
                description=desc,
                colour=discord.Colour.red()
            )
            embed.set_author(name='Sistema de Pagamentos', icon_url=self.client.user.display_avatar)
            try:
                await canal_log.send(embed=embed)
            except Exception as e:
                print(f"Erro ao enviar lembrete de pagamentos: {e}")

    @auto_lembrete_pagamentos_task.before_loop
    async def before_auto_lembrete_pagamentos_task(self):
        await self.client.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        print('Pica-Ponto carregado com sucesso!')
        await db.setup_db()
        self.client.add_view(view=finalizarPonto())
        await self.carregar_pontos_pendentes()
        
        if not self.auto_close_task.is_running():
            self.auto_close_task.start()
        if not self.auto_backup_task.is_running():
            self.auto_backup_task.start()
        if not self.auto_register_task.is_running():
            self.auto_register_task.start()
        if not self.auto_lembrete_pagamentos_task.is_running():
            self.auto_lembrete_pagamentos_task.start()

    async def carregar_pontos_pendentes(self):
        import os
        if not os.path.exists(ACTIVE_PONTOS_FILE):
            return
            
        try:
            with open(ACTIVE_PONTOS_FILE, "r") as f:
                pontos_pendentes = json.load(f)
        except Exception as e:
            print(f"[ERROR] Falha ao carregar {ACTIVE_PONTOS_FILE}: {e}")
            return
            
        if not pontos_pendentes:
            return
            
        # Carrega os pontos de volta para a memória
        count = 0
        for user_id_str, estado in pontos_pendentes.items():
            try:
                user_id = int(user_id_str)
                active_pontos[user_id] = estado
                count += 1
            except Exception:
                continue
        
        if count > 0:
            print(f"[SISTEMA] {count} pica-pontos restaurados com sucesso.")

    @commands.slash_command(description='[ADM] Adiciona horas/minutos para uma pessoa no pica-ponto', contexts={discord.InteractionContextType.guild})
    @has_staff_role()
    async def addtempo(self, ctx: discord.ApplicationContext, usuario: Option(discord.Member, 'Selecione o usuário', required=True),
                    horas: Option(int, "Digite a quantidade de horas", required=True, min_value=0),
                    minutos: Option(int, "Digite a quantidade de minutos", required=True, min_value=0, max_value=59),
                    motivo: Option(str, "Digite o motivo da adição de horas (Ficará em exibição no log)", required=True)):

        func = await db.get_funcionario(usuario.id)
        if not func:
            return await ctx.respond('❌ Este usuário não é um funcionário registrado no sistema.', ephemeral=True)

        total = (int(horas) * 3600) + (int(minutos) * 60)
        await db.add_time(usuario.id, total)
        
        agora = int(datetime.datetime.now(obter_timezone()).timestamp())
        await db.create_registry(usuario.id, agora, agora, 2, total, "[]")

        await ctx.respond(f'<a:check:1269034091882221710> Sucesso! Você adicionou `{horas}` horas e `{minutos}` minutos para {usuario.mention}.')
        try:
            await usuario.send(f'**<:aviso:1269036173381206132> AVISO!** Você sofreu uma alteração nas horas trabalhadas!\n**→ Staff:** {ctx.author.mention}\n**→ Adicionou:** {horas} hora(s) e {minutos} minuto(s)\n**→ Motivo:** {motivo}\n\n`Em caso de problemas ou dúvidas, questione o staff mencionado acima.`')
        except (discord.HTTPException, discord.Forbidden):
            pass
        canal_log = ctx.guild.get_channel(config['log_channel_id'])
        embed_log = discord.Embed(description=f'**→ `Staff`: {ctx.author.mention}**\n**→ `Funcionário`: {usuario.mention}**\n'
            f'**→ `Horas adicionadas`: {horas} horas e {minutos} minutos**\n**→ `Motivo inserido`: {motivo}**', colour=discord.Colour.purple())

        embed_log.set_author(name='LOG: Adição de Horas', icon_url=self.client.user.display_avatar)
        await canal_log.send(embed=embed_log)


    @commands.slash_command(description='[ADM] Remove horas/minutos de uma pessoa no pica-ponto', contexts={discord.InteractionContextType.guild})
    @has_staff_role()
    async def deltempo(self, ctx: discord.ApplicationContext, usuario: Option(discord.Member, 'Selecione o usuário', required=True),
                    horas: Option(int, "Digite a quantidade de horas", required=True, min_value=0),
                    minutos: Option(int, "Digite a quantidade de minutos", required=True, min_value=0, max_value=59),
                    motivo: Option(str, "Digite o motivo da remoção de horas (Ficará em exibição no log)", required=True)):

        func = await db.get_funcionario(usuario.id)
        if not func:
            return await ctx.respond('❌ Este usuário não é um funcionário registrado no sistema.', ephemeral=True)

        total = (int(horas) * 3600) + (int(minutos) * 60)
        await db.del_time(usuario.id, total)
        
        agora = int(datetime.datetime.now(obter_timezone()).timestamp())
        await db.create_registry(usuario.id, agora, agora, 3, -total, "[]")

        await ctx.respond(f'<a:check:1269034091882221710> Sucesso! Você removeu `{horas}` horas e `{minutos}` minutos de {usuario.mention}.')
        try:
            await usuario.send(f'**<:aviso:1269036173381206132> AVISO!** Você sofreu uma alteração nas horas trabalhadas!\n**→ Staff:** {ctx.author.mention}\n**→ Removeu:** {horas} hora(s) e {minutos} minuto(s)\n**→ Motivo:** {motivo}\n\n`Em caso de problemas ou dúvidas, questione o staff mencionado acima.`')
        except (discord.HTTPException, discord.Forbidden):
            pass
            
        canal_log = ctx.guild.get_channel(config['log_channel_id'])
        embed_log = discord.Embed(description=f'**→ `Staff`: {ctx.author.mention}**\n**→ `Funcionário`: {usuario.mention}**\n'
            f'**→ `Horas removidas`: {horas} horas e {minutos} minutos**\n**→ `Motivo inserido`: {motivo}**', colour=discord.Colour.purple())

        embed_log.set_author(name='LOG: Remoção de Horas', icon_url=self.client.user.display_avatar)
        await canal_log.send(embed=embed_log)

    @commands.slash_command(name="contratar", description='[ADM] Registra um novo funcionário', contexts={discord.InteractionContextType.guild})
    @has_staff_role()
    async def contratar(self, ctx: discord.ApplicationContext,
                       usuario: Option(discord.Member, 'Selecione o usuário', required=True),
                       patente: Option(str, 'Selecione a patente', choices=[discord.OptionChoice(name=v.get('nome', k.replace('_', ' ').title()), value=k) for k, v in config.get("cargos_patentes", {}).items()], required=True),
                       nome: Option(str, 'Nome do funcionário', required=True),
                       motivo: Option(str, 'Motivo da contratação', required=True)):
        
        await ctx.defer()
        
        patente_info = config["cargos_patentes"][patente]
        letra = patente_info["letra"]
        cargo_patente_id = int(patente_info["id"])
        cargo_equipa_id = config.get("cargo_equipa_id")
        
        callsign = await db.get_next_callsign(letra)
        
        cargos_para_adicionar = []
        cargo_patente = ctx.guild.get_role(cargo_patente_id)
        if cargo_patente:
            cargos_para_adicionar.append(cargo_patente)
            
        if cargo_equipa_id:
            cargo_equipa = ctx.guild.get_role(cargo_equipa_id)
            if cargo_equipa:
                cargos_para_adicionar.append(cargo_equipa)
                
        if cargos_para_adicionar:
            try:
                await usuario.add_roles(*cargos_para_adicionar)
            except discord.Forbidden:
                return await ctx.followup.send("❌ Não tenho permissão para adicionar os cargos. O meu cargo precisa estar acima dos cargos que estou tentando adicionar.")
                
        novo_nick = f"[{callsign}] {nome}"
        try:
            await usuario.edit(nick=novo_nick)
        except discord.Forbidden:
            pass
            
        await db.add_funcionario(usuario.id, patente, callsign, nome)
        
        # Gerar credenciais para a Dashboard
        alphabet = string.ascii_letters + string.digits
        senha_temp = ''.join(secrets.choice(alphabet) for i in range(8))
        # Executar em thread para não bloquear o event loop do bot
        senha_hash = await asyncio.to_thread(generate_password_hash, senha_temp)
        await db.update_password(usuario.id, senha_hash)
        
        reset_token = secrets.token_urlsafe(32)
        await db.set_reset_token(usuario.id, reset_token)
        
        try:
            msg_dm = (
                f'**<:aviso:1269036173381206132> AVISO!** Você foi contratado(a) e registrado(a) no sistema!\n'
                f'**→ Staff:** {ctx.author.mention}\n**→ Patente:** {patente_info["nome"]}\n'
                f'**→ Callsign:** `{callsign}`\n**→ Motivo:** {motivo}\n\n'
                f'**🌐 Dashboard Online:**\n'
                f'O seu acesso ao painel já está disponível!\n'
                f'**Painel:** `https://ems.discloud.app`\n'
                f'**Username:** `{callsign}`\n'
                f'**Senha Provisória:** `{senha_temp}`\n'
                f'*(Recomendamos que você altere sua senha no primeiro acesso através de "Esqueci a Palavra-Passe" ou do link abaixo:)*\n'
                f'`https://ems.discloud.app/reset_password/{reset_token}`'
            )
            await usuario.send(msg_dm)
        except (discord.HTTPException, discord.Forbidden):
            pass
            
        log_canal_id = config.get("log_contratacoes_id")
        if log_canal_id:
            log_canal = ctx.guild.get_channel(log_canal_id)
            if log_canal:
                embed_log = discord.Embed(title='LOG: Contratação', description=f'**→ `Staff`: {ctx.author.mention}**\n**→ `Funcionário`: {usuario.mention}**\n**→ `Nova Patente`: {patente_info["nome"]}**\n**→ `Callsign`: {callsign}**\n**→ `Motivo`: {motivo}**', colour=discord.Colour.green())
                embed_log.set_author(name='Contratação efetuada', icon_url=self.client.user.display_avatar)
                await log_canal.send(embed=embed_log)
        
        embed = discord.Embed(title="✅ Funcionário Registrado", description=f"O funcionário {usuario.mention} foi registrado com sucesso!\n\n**Patente:** {patente_info['nome']}\n**Callsign:** `{callsign}`\n**Nome:** {nome}\n**Motivo:** {motivo}", color=discord.Colour.green())
        await ctx.followup.send(embed=embed)

    @commands.slash_command(description='[ADM] Despede/Remove um funcionário', contexts={discord.InteractionContextType.guild})
    @has_staff_role()
    async def despedir(self, ctx: discord.ApplicationContext,
                          usuario: Option(discord.Member, 'Selecione o usuário', required=True),
                          motivo: Option(str, 'Motivo do despedimento', required=True)):
        
        await ctx.defer()
        
        func = await db.get_funcionario(usuario.id)
        if not func:
            return await ctx.followup.send("❌ Este usuário não está registrado como funcionário.")
            
        patente_info = config["cargos_patentes"].get(func[0])
        
        cargos_para_remover = []
        if patente_info:
            cargo_patente = ctx.guild.get_role(int(patente_info["id"]))
            if cargo_patente:
                cargos_para_remover.append(cargo_patente)
                
        cargo_equipa_id = config.get("cargo_equipa_id")
        if cargo_equipa_id:
            cargo_equipa = ctx.guild.get_role(cargo_equipa_id)
            if cargo_equipa:
                cargos_para_remover.append(cargo_equipa)
                
        if cargos_para_remover:
            try:
                await usuario.remove_roles(*cargos_para_remover)
            except discord.Forbidden:
                pass
                
        try:
            await usuario.edit(nick=None)
        except discord.Forbidden:
            pass
            
        velha_letra, velho_num = func[1].split('-')
        velho_num = int(velho_num)
        await db.remove_funcionario(usuario.id)
        
        shifted_users = await db.shift_callsigns_down(velha_letra, velho_num)
        for s_user_id, s_novo_callsign, s_nome in shifted_users:
            try:
                s_member = ctx.guild.get_member(s_user_id) or await ctx.guild.fetch_member(s_user_id)
                await s_member.edit(nick=f"[{s_novo_callsign}] {s_nome}")
            except:
                pass
        
        try:
            await usuario.send(f'**<:aviso:1269036173381206132> AVISO!** Você foi despedido(a) e removido(a) do sistema!\n**→ Staff:** {ctx.author.mention}\n**→ Motivo:** {motivo}')
        except (discord.HTTPException, discord.Forbidden):
            pass
            
        log_canal_id = config.get("log_contratacoes_id")
        if log_canal_id:
            log_canal = ctx.guild.get_channel(log_canal_id)
            if log_canal:
                embed_log = discord.Embed(title='LOG: Despedimento', description=f'**→ `Staff`: {ctx.author.mention}**\n**→ `Funcionário`: {usuario.mention}**\n**→ `Motivo`: {motivo}**', colour=discord.Colour.red())
                embed_log.set_author(name='Despedimento efetuado', icon_url=self.client.user.display_avatar)
                await log_canal.send(embed=embed_log)
        
        embed = discord.Embed(title="✅ Funcionário Removido", description=f"O funcionário {usuario.mention} foi removido com sucesso!\n\n**Motivo:** {motivo}", color=discord.Colour.red())
        await ctx.followup.send(embed=embed)

    @commands.slash_command(description='[ADM] Promove/Altera a patente de um funcionário', contexts={discord.InteractionContextType.guild})
    @has_staff_role()
    async def promover(self, ctx: discord.ApplicationContext,
                       usuario: Option(discord.Member, 'Selecione o usuário', required=True),
                       nova_patente: Option(str, 'Selecione a nova patente', choices=[discord.OptionChoice(name=v.get('nome', k.replace('_', ' ').title()), value=k) for k, v in config.get("cargos_patentes", {}).items()], required=True),
                       motivo: Option(str, 'Motivo da promoção/alteração', required=True)):
        
        await ctx.defer()
        
        func = await db.get_funcionario(usuario.id)
        if not func:
            return await ctx.followup.send("❌ Este usuário não está registrado como funcionário.")
            
        patente_antiga_key = func[0]
        nome_func = func[2]
        
        if patente_antiga_key == nova_patente:
            return await ctx.followup.send("❌ Este usuário já possui essa patente.")
            
        patente_antiga_info = config["cargos_patentes"].get(patente_antiga_key)
        nova_patente_info = config["cargos_patentes"][nova_patente]
        
        cargos_para_remover = []
        if patente_antiga_info:
            cargo_antigo = ctx.guild.get_role(int(patente_antiga_info["id"]))
            if cargo_antigo:
                cargos_para_remover.append(cargo_antigo)
                
        cargos_para_adicionar = []
        cargo_novo = ctx.guild.get_role(int(nova_patente_info["id"]))
        if cargo_novo:
            cargos_para_adicionar.append(cargo_novo)
            
        try:
            if cargos_para_remover:
                await usuario.remove_roles(*cargos_para_remover)
            if cargos_para_adicionar:
                await usuario.add_roles(*cargos_para_adicionar)
        except discord.Forbidden:
            pass
            
        novo_callsign = await db.get_next_callsign(nova_patente_info["letra"])
        
        novo_nick = f"[{novo_callsign}] {nome_func}"
        try:
            await usuario.edit(nick=novo_nick)
        except discord.Forbidden:
            pass
        if func[1] and '-' in func[1]:
            velha_letra, velho_num = func[1].split('-')
            try:
                velho_num = int(velho_num)
            except ValueError:
                velho_num = 0
        else:
            velha_letra, velho_num = "", 0
        await db.add_funcionario(usuario.id, nova_patente, novo_callsign, nome_func)
        
        shifted_users = await db.shift_callsigns_down(velha_letra, velho_num)
        for s_user_id, s_novo_callsign, s_nome in shifted_users:
            try:
                s_member = ctx.guild.get_member(s_user_id) or await ctx.guild.fetch_member(s_user_id)
                await s_member.edit(nick=f"[{s_novo_callsign}] {s_nome}")
            except:
                pass
        
        try:
            await usuario.send(f'**<:aviso:1269036173381206132> AVISO!** Você teve a sua patente alterada!\n**→ Staff:** {ctx.author.mention}\n**→ Nova Patente:** {nova_patente_info["nome"]}\n**→ Novo Callsign:** `{novo_callsign}`\n**→ Motivo:** {motivo}')
        except (discord.HTTPException, discord.Forbidden):
            pass
            
        log_canal_id = config.get("log_contratacoes_id")
        if log_canal_id:
            log_canal = ctx.guild.get_channel(log_canal_id)
            if log_canal:
                embed_log = discord.Embed(title='LOG: Promoção/Alteração de Patente', description=f'**→ `Staff`: {ctx.author.mention}**\n**→ `Funcionário`: {usuario.mention}**\n**→ `Patente Antiga`: {patente_antiga_info["nome"] if patente_antiga_info else "Desconhecida"}**\n**→ `Nova Patente`: {nova_patente_info["nome"]}**\n**→ `Novo Callsign`: {novo_callsign}**\n**→ `Motivo`: {motivo}**', colour=discord.Colour.blue())
                embed_log.set_author(name='Promoção efetuada', icon_url=self.client.user.display_avatar)
                await log_canal.send(embed=embed_log)
        
        embed = discord.Embed(title="✅ Funcionário Promovido", description=f"O funcionário {usuario.mention} teve a sua patente alterada!\n\n**Patente Antiga:** {patente_antiga_info['nome'] if patente_antiga_info else 'Desconhecida'}\n**Nova Patente:** {nova_patente_info['nome']}\n**Novo Callsign:** `{novo_callsign}`\n**Motivo:** {motivo}", color=discord.Colour.green())
        await ctx.followup.send(embed=embed)

    @commands.slash_command(name="editar_funcionario", description='[ADM] Edita manualmente o callsign, nome e/ou cargo de um funcionário', contexts={discord.InteractionContextType.guild})
    @has_staff_role()
    async def editar_funcionario(self, ctx: discord.ApplicationContext,
                       usuario: Option(discord.Member, 'Selecione o funcionário', required=True),
                       motivo: Option(str, 'Motivo da alteração manual', required=True),
                       novo_callsign: Option(str, 'Digite o novo callsign (ex: W-01) - Deixe em branco para não alterar', required=False, default=None),
                       novo_nome: Option(str, 'Digite o novo nome - Deixe em branco para não alterar', required=False, default=None),
                       novo_cargo: Option(str, 'Selecione o novo cargo - Deixe em branco para não alterar', choices=[discord.OptionChoice(name=v.get('nome', k.replace('_', ' ').title()), value=k) for k, v in config.get("cargos_patentes", {}).items()], required=False, default=None)):
        
        await ctx.defer()
        
        func = await db.get_funcionario(usuario.id)
        if not func:
            return await ctx.followup.send("❌ Este usuário não está registrado como funcionário.")
            
        patente_antiga_key = func[0]
        callsign_antigo = func[1]
        nome_antigo = func[2]
        
        if not novo_callsign and not novo_nome and not novo_cargo:
            return await ctx.followup.send("❌ Tens de fornecer pelo menos um campo para alterar (Callsign, Nome ou Cargo).")
            
        if novo_callsign:
            # Verificar se o novo callsign já está em uso por outro funcionário
            funcionarios_db = await db.get_all_funcionarios()
            taken = any(f[2] and f[2].upper() == novo_callsign.upper() and f[0] != usuario.id for f in funcionarios_db)
            if taken:
                return await ctx.followup.send(f"❌ O Callsign `{novo_callsign}` já está em uso por outro funcionário.")
                
        patente_antiga_info = config["cargos_patentes"].get(patente_antiga_key)
        nova_patente_info = config["cargos_patentes"].get(novo_cargo) if novo_cargo else None
        
        cargos_para_remover = []
        cargos_para_adicionar = []
        
        if novo_cargo and patente_antiga_key != novo_cargo:
            if patente_antiga_info:
                cargo_antigo = ctx.guild.get_role(int(patente_antiga_info["id"]))
                if cargo_antigo:
                    cargos_para_remover.append(cargo_antigo)
            
            if nova_patente_info:
                cargo_novo = ctx.guild.get_role(int(nova_patente_info["id"]))
                if cargo_novo:
                    cargos_para_adicionar.append(cargo_novo)
                    
        if cargos_para_remover or cargos_para_adicionar:
            try:
                if cargos_para_remover:
                    await usuario.remove_roles(*cargos_para_remover)
                if cargos_para_adicionar:
                    await usuario.add_roles(*cargos_para_adicionar)
            except discord.Forbidden:
                pass
                
        final_patente = novo_cargo if novo_cargo else patente_antiga_key
        final_callsign = novo_callsign if novo_callsign else callsign_antigo
        final_nome = novo_nome if novo_nome else nome_antigo
        
        await db.add_funcionario(usuario.id, final_patente, final_callsign, final_nome)
        
        novo_nick = f"[{final_callsign}] {final_nome}"
        try:
            await usuario.edit(nick=novo_nick)
        except discord.Forbidden:
            pass
            
        desc_alteracoes = []
        if novo_callsign:
            desc_alteracoes.append(f"**Callsign:** `{callsign_antigo}` ➔ `{final_callsign}`")
        if novo_nome:
            desc_alteracoes.append(f"**Nome:** `{nome_antigo}` ➔ `{final_nome}`")
        if novo_cargo:
            cargo_antigo_nome = patente_antiga_info["nome"] if patente_antiga_info else "Desconhecido"
            cargo_novo_nome = nova_patente_info["nome"] if nova_patente_info else "Desconhecido"
            desc_alteracoes.append(f"**Cargo:** `{cargo_antigo_nome}` ➔ `{cargo_novo_nome}`")
            
        desc_alteracoes_str = "\n".join(desc_alteracoes)
        
        try:
            msg_dm = (
                f'**<:aviso:1269036173381206132> AVISO: Dados Alterados Manualmente!**\n'
                f'**→ Staff:** {ctx.author.mention}\n'
                f'**→ Alterações:**\n'
                f'{desc_alteracoes_str}\n'
                f'**→ Motivo:** {motivo}\n\n'
                f'*Nota: Se o seu Callsign foi alterado, utilize o seu novo Callsign `{final_callsign}` para aceder ao Painel Web (a sua palavra-passe permanece inalterada).*'
            )
            await usuario.send(msg_dm)
        except (discord.HTTPException, discord.Forbidden):
            pass
            
        log_canal_id = config.get("log_contratacoes_id")
        if log_canal_id:
            log_canal = ctx.guild.get_channel(log_canal_id)
            if log_canal:
                embed_log = discord.Embed(
                    title='LOG: Edição Manual de Funcionário',
                    description=f'**→ `Staff`: {ctx.author.mention}**\n**→ `Funcionário`: {usuario.mention}**\n{desc_alteracoes_str}\n**→ `Motivo`: {motivo}**',
                    colour=discord.Colour.orange()
                )
                embed_log.set_author(name='Edição manual efetuada', icon_url=self.client.user.display_avatar)
                await log_canal.send(embed=embed_log)
                
        embed = discord.Embed(
            title="✅ Funcionário Editado com Sucesso",
            description=f"Os dados de {usuario.mention} foram atualizados com sucesso!\n\n{desc_alteracoes_str}\n\n**Motivo:** {motivo}",
            color=discord.Colour.green()
        )
        await ctx.followup.send(embed=embed)

    @commands.slash_command(description='[ADM] Reseta as horas do pica-ponto de um determinado usuário', contexts={discord.InteractionContextType.guild})
    @has_staff_role()
    async def resetar_usuario(self, ctx: discord.ApplicationContext, usuario: Option(discord.Member, 'Selecione o usuário', required=True)):

        func = await db.get_funcionario(usuario.id)
        if not func:
            return await ctx.respond('❌ Este usuário não é um funcionário registrado no sistema.', ephemeral=True)

        await db.set_time(usuario.id, 0)
        await ctx.respond(f'<a:check:1269034091882221710> Sucesso! Você resetou as horas de {usuario.mention}.')
        
        canal_log = ctx.guild.get_channel(config['log_channel_id'])
        embed_log = discord.Embed(description=f'**→ `Staff`: {ctx.author.mention}**\n**→ `Funcionário`: {usuario.mention}**\n'
            f'**→ O(A) funcionário(a) acima teve todas as suas horas de pica-ponto resetadas.**', colour=discord.Colour.red())

        embed_log.set_author(name='LOG: Reset de Horas', icon_url=self.client.user.display_avatar)
        await canal_log.send(embed=embed_log)

    @commands.slash_command(name="resetarsenha", description='[ADM] Reseta a senha do painel web de um funcionário', contexts={discord.InteractionContextType.guild})
    @has_staff_role()
    async def resetarsenha(self, ctx: discord.ApplicationContext, usuario: Option(discord.Member, 'Selecione o usuário', required=True)):
        await ctx.defer(ephemeral=True)

        func = await db.get_funcionario(usuario.id)
        if not func:
            return await ctx.followup.send('❌ Este usuário não é um funcionário registrado no sistema.', ephemeral=True)

        reset_token = secrets.token_urlsafe(32)
        await db.set_reset_token(usuario.id, reset_token)

        try:
            msg_dm = (
                f'**<:aviso:1269036173381206132> AVISO!** A sua senha do painel web foi resetada pela Staff!\n'
                f'**→ Staff:** {ctx.author.mention}\n\n'
                f'**🌐 Dashboard Online:**\n'
                f'Para definir uma nova senha, acesse o link abaixo:\n'
                f'`https://ems.discloud.app/reset_password/{reset_token}`'
            )
            await usuario.send(msg_dm)
            await ctx.followup.send(f'<a:check:1269034091882221710> Sucesso! O link de redefinição de senha foi enviado na DM de {usuario.mention}.', ephemeral=True)
        except (discord.HTTPException, discord.Forbidden):
            await ctx.followup.send(f'⚠️ Não foi possível enviar a DM para {usuario.mention}. O link de reset é: `https://ems.discloud.app/reset_password/{reset_token}`', ephemeral=True)

        canal_log = ctx.guild.get_channel(config['log_channel_id'])
        if canal_log:
            embed_log = discord.Embed(description=f'**→ `Staff`: {ctx.author.mention}**\n**→ `Funcionário`: {usuario.mention}**\n'
                f'**→ O(A) funcionário(a) acima teve a sua senha do painel web resetada pela Staff.**', colour=discord.Colour.orange())
            embed_log.set_author(name='LOG: Reset de Senha Web', icon_url=self.client.user.display_avatar)
            try:
                await canal_log.send(embed=embed_log)
            except:
                pass


    @commands.slash_command(description='[ADM] Configura para 0 horas e apaga os dados de todos os usuários registrados.', contexts={discord.InteractionContextType.guild})
    @has_staff_role()
    async def resetar_todos(self, ctx: discord.ApplicationContext):

        await ctx.respond(view=BotoesReset())

    @commands.slash_command(name="autocorrecao", description='[ADM] Força a auto-correção e auto-registro de todos os funcionários', contexts={discord.InteractionContextType.guild})
    @has_staff_role()
    async def force_autocorrecao(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        
        guild = ctx.guild
        funcionarios_db = await db.get_all_funcionarios()
        ids_registrados = [f[0] for f in funcionarios_db]

        registrados = 0
        corrigidos = 0

        for member in guild.members:
            if member.bot:
                continue

            # Obter patente correspondente ao cargo atual
            patente_atual_key = None
            patente_atual_info = None
            for p_key, p_info in config.get("cargos_patentes", {}).items():
                if p_info.get("id") and any(r.id == int(p_info["id"]) for r in member.roles):
                    patente_atual_key = p_key
                    patente_atual_info = p_info
                    break

            if not patente_atual_key:
                continue # Não tem patente

            func_db = next((f for f in funcionarios_db if f[0] == member.id), None)
            
            if not func_db:
                # Tenta extrair callsign e nome do nick: [Callsign] Nome
                nick_atual = member.display_name
                match = re.match(r'^\[(.*?)\]\s+(.*)', nick_atual)
                
                if match:
                    callsign = match.group(1)
                    nome = match.group(2)
                else:
                    continue

                letra_correta = patente_atual_info["letra"]
                try:
                    ext_letra = callsign.split('-')[0]
                except:
                    ext_letra = ""
                    
                callsign_is_taken = any(f[2] == callsign for f in funcionarios_db)
                
                if ext_letra != letra_correta or callsign_is_taken:
                    novo_callsign = await db.get_next_callsign(letra_correta)
                    await db.add_funcionario(member.id, patente_atual_key, novo_callsign, nome)
                    registrados += 1
                    corrigidos += 1
                    
                    try:
                        await member.edit(nick=f"[{novo_callsign}] {nome}")
                    except:
                        pass
                        
                    log_canal_id = config.get("log_contratacoes_id")
                    if log_canal_id:
                        log_canal = guild.get_channel(log_canal_id)
                        if log_canal:
                            embed_log = discord.Embed(
                                title='LOG: Auto-Correção e Registro',
                                description=f'**→ `Sistema`: Auto-Correção (Novo Registro)**\n**→ `Staff`: {ctx.author.mention}**\n**→ `Funcionário`: {member.mention}**\n**→ `Callsign Extraído`: {callsign} (Incorreto/Ocupado)**\n**→ `Novo Callsign`: {novo_callsign}**\n**→ `Nova Patente`: {patente_atual_info["nome"]}**',
                                colour=discord.Colour.blue()
                            )
                            await log_canal.send(embed=embed_log)
                else:
                    await db.add_funcionario(member.id, patente_atual_key, callsign, nome)
                    registrados += 1
                    
                    log_canal_id = config.get("log_contratacoes_id")
                    if log_canal_id:
                        log_canal = guild.get_channel(log_canal_id)
                        if log_canal:
                            embed_log = discord.Embed(
                                title='LOG: Auto-Registro Efetuado',
                                description=f'**→ `Sistema`: Auto-Registro (Manual)**\n**→ `Staff`: {ctx.author.mention}**\n**→ `Funcionário`: {member.mention}**\n**→ `Patente Detectada`: {patente_atual_info["nome"]}**\n**→ `Callsign Extraído`: {callsign}**',
                                colour=discord.Colour.green()
                            )
                            await log_canal.send(embed=embed_log)
            else:
                velho_callsign = func_db[2]
                try:
                    velha_letra, velho_num_str = velho_callsign.split('-')
                    velho_num = int(velho_num_str)
                except:
                    continue
                    
                letra_correta = patente_atual_info["letra"]
                
                if velha_letra != letra_correta:
                    novo_callsign = await db.get_next_callsign(letra_correta)
                    nome_func = func_db[3]
                    
                    await db.add_funcionario(member.id, patente_atual_key, novo_callsign, nome_func)
                    
                    shifted_users = await db.shift_callsigns_down(velha_letra, velho_num)
                    for s_user_id, s_novo_callsign, s_nome in shifted_users:
                        try:
                            s_member = guild.get_member(s_user_id) or await guild.fetch_member(s_user_id)
                            await s_member.edit(nick=f"[{s_novo_callsign}] {s_nome}")
                        except:
                            pass
                    
                    try:
                        await member.edit(nick=f"[{novo_callsign}] {nome_func}")
                    except:
                        pass
                        
                    corrigidos += 1
                        
                    log_canal_id = config.get("log_contratacoes_id")
                    if log_canal_id:
                        log_canal = guild.get_channel(log_canal_id)
                        if log_canal:
                            embed_log = discord.Embed(
                                title='LOG: Auto-Correção de Callsign',
                                description=f'**→ `Sistema`: Auto-Correção (Manual)**\n**→ `Staff`: {ctx.author.mention}**\n**→ `Funcionário`: {member.mention}**\n**→ `Callsign Antigo`: {velho_callsign}**\n**→ `Novo Callsign`: {novo_callsign}**\n**→ `Nova Patente`: {patente_atual_info["nome"]}**',
                                colour=discord.Colour.blue()
                            )
                            await log_canal.send(embed=embed_log)
                else:
                    nick_esperado = f"[{velho_callsign}] {func_db[3]}"
                    if member.display_name != nick_esperado:
                        try:
                            await member.edit(nick=nick_esperado)
                        except:
                            pass

        embed = discord.Embed(
            title="✅ Verificação Concluída", 
            description=f"A verificação manual de auto-correção e auto-registro foi finalizada com sucesso!\n\n**Novos Registros:** `{registrados}`\n**Callsigns Corrigidos:** `{corrigidos}`", 
            color=discord.Colour.green()
        )
        await ctx.followup.send(embed=embed)


    @commands.slash_command(description='Retorna o ranking das top 10 pessoas com mais horas na semana.', contexts={discord.InteractionContextType.guild})
    async def ranking(self, ctx: discord.ApplicationContext):

        top10 = await db.get_ranking()
        
        embed = discord.Embed(title='🏆 Ranking Semanal (TOP 10)', color=discord.Colour.gold())
        for index, user in enumerate(top10):
            horas, minutos = int(user[1] // 3600), int((user[1] % 3600) // 60)
            
            func_db = await db.get_funcionario(user[0])
            pagamento_str = ""
            if func_db:
                nome_exib = f"[{func_db[1]}] {func_db[2]}"
                patente_info = config.get("cargos_patentes", {}).get(func_db[0])
                if patente_info:
                    valor_hora = patente_info.get("valor_hora", 0)
                    pagamento = ((horas * 60 + minutos) / 60) * valor_hora
                    pagamento_str = f' - 💰 `{formatar_moeda(pagamento)}`'
            else:
                membro = ctx.guild.get_member(user[0])
                nome_exib = membro.display_name if membro else f"ID: {user[0]}"
            
            embed.add_field(name=f'{index+1}º Lugar', value=f'**{nome_exib}** - `{horas}h:{minutos}m`{pagamento_str}', inline=False)
            
        await ctx.respond(embed=embed)

    @commands.slash_command(name='semana', description='[ADM] Mostra o relatório semanal de horas e envia backup.', contexts={discord.InteractionContextType.guild})
    @has_staff_role()
    async def semana(self, ctx: discord.ApplicationContext):
        top_todos = await db.get_ranking(amount=100)
        # Filtrar apenas quem tem o cargo ponto_role_id
        cargo_ponto = ctx.guild.get_role(config['ponto_role_id'])
        top_filtrado = [u for u in top_todos if cargo_ponto and ctx.guild.get_member(u[0]) and cargo_ponto in ctx.guild.get_member(u[0]).roles]
        agora_str = datetime.datetime.now(obter_timezone()).strftime('%d/%m/%Y \u00e0s %H:%M')

        embed_confirmar = discord.Embed(
            title='\U0001f4ca Relatório Semanal',
            description=(
                f'**Staff:** {ctx.author.mention}\n'
                f'**Data/Hora:** `{agora_str}`\n\n'
                '**As seguintes acções serão executadas após confirmar:**\n\n'
                '\U0001f4ca **1.** Relatório com as horas de **todos os funcionários com cargo de ponto** será exibido no canal\n'
                '\U0001f4be **2.** Um backup do ficheiro `db.sqlite3` será enviado no canal\n\n'
                '> ℹ️ Os dados **não serão apagados** — usa `/resetarsemana` para isso.'
            ),
            color=discord.Colour.blue()
        )
        embed_confirmar.set_footer(text='Tens 30 segundos para confirmar.')
        await ctx.respond(embed=embed_confirmar, view=BotoesSemana(top_filtrado, reset=False), ephemeral=True)

    @commands.slash_command(name='resetarsemana', description='[ADM] Encerra a semana: mostra relatório, backup e reseta tudo.', contexts={discord.InteractionContextType.guild})
    @has_staff_role()
    async def resetarsemana(self, ctx: discord.ApplicationContext):
        top_todos = await db.get_ranking(amount=100)
        cargo_ponto = ctx.guild.get_role(config['ponto_role_id'])
        top_filtrado = [u for u in top_todos if cargo_ponto and ctx.guild.get_member(u[0]) and cargo_ponto in ctx.guild.get_member(u[0]).roles]
        agora_str = datetime.datetime.now(obter_timezone()).strftime('%d/%m/%Y \u00e0s %H:%M')

        embed_confirmar = discord.Embed(
            title='\u26a0\ufe0f Encerramento Semanal',
            description=(
                f'**Staff:** {ctx.author.mention}\n'
                f'**Data/Hora:** `{agora_str}`\n\n'
                '**As seguintes acções serão executadas após confirmar:**\n\n'
                '\U0001f4ca **1.** Relatório com as horas de **todos os funcionários com cargo de ponto** será exibido no canal\n'
                '\U0001f4be **2.** Um backup do ficheiro `db.sqlite3` será enviado no canal\n'
                '\U0001f504 **3.** Todos os tempos e registos serão **resetados para zero**\n\n'
                '> \u274c Esta acção **não pode ser desfeita!**'
            ),
            color=discord.Colour.orange()
        )
        embed_confirmar.set_footer(text='Tens 30 segundos para confirmar.')
        await ctx.respond(embed=embed_confirmar, view=BotoesSemana(top_filtrado, reset=True), ephemeral=True)


    @commands.slash_command(name="pontosreg", description='Verifica todo os pica-pontos salvos na base de dados de uma pessoa.', contexts={discord.InteractionContextType.guild}, default_member_permissions=None)
    async def consultar_ponto(self, ctx: discord.ApplicationContext, usuario: Option(discord.Member, 'Selecione o usuário', required=False)):
        cargo_ponto = ctx.guild.get_role(config['ponto_role_id'])
        if cargo_ponto not in ctx.author.roles:
            return await ctx.respond('❌ Não tens permissão para usar este comando.', ephemeral=True)
        if usuario is None:
            usuario = ctx.author
            
        dados = await db.get_all_user_registries(usuario.id)
        if not dados:
            return await ctx.respond('❌ Este usuário ainda não possui nenhum registro salvo.', ephemeral=True)

        func_db = await db.get_funcionario(usuario.id)
        valor_hora = 0
        if func_db:
            patente_info = config.get("cargos_patentes", {}).get(func_db[0])
            if patente_info:
                valor_hora = patente_info.get("valor_hora", 0)

        registros_por_dia = {}
        total_dia_segundos = {}
        total_semana_segundos = 0

        for k in dados:
            hr_inicio = datetime.datetime.fromtimestamp(k[0], obter_timezone()).strftime("%H:%M")
            hr_fim = datetime.datetime.fromtimestamp(k[1], obter_timezone()).strftime("%H:%M")
            data_str = datetime.datetime.fromtimestamp(k[0], obter_timezone()).strftime("%d/%m/%Y")
            
            total_semana_segundos += k[3]
            total_dia_segundos[data_str] = total_dia_segundos.get(data_str, 0) + k[3]

            if data_str not in registros_por_dia:
                registros_por_dia[data_str] = []

            if k[2] == 2:
                hr = str(k[3] // 3600).zfill(2)
                mins = str((k[3] % 3600) // 60).zfill(2)
                registros_por_dia[data_str].append(f'➕ **Horas Adicionadas (Staff):** `{hr}h {mins}m`')
                continue
            elif k[2] == 3:
                duracao_abs = abs(k[3])
                hr = str(duracao_abs // 3600).zfill(2)
                mins = str((duracao_abs % 3600) // 60).zfill(2)
                registros_por_dia[data_str].append(f'➖ **Horas Removidas (Staff):** `{hr}h {mins}m`')
                continue

            staff = True if k[2] == 1 else False
            duracao = k[3]
            pausas_str = k[4] if len(k) > 4 else '[]'
            try:
                pausas = json.loads(pausas_str)
            except:
                pausas = []

            hr = str(duracao // 3600).zfill(2)
            mins = str((duracao % 3600) // 60).zfill(2)
            
            registros_por_dia[data_str].append(f'🟢 `{hr_inicio}` → `{hr_fim}`  **({hr}h {mins}m)**{"  🟡" if staff else ""}')
            for p in pausas:
                p_in = datetime.datetime.fromtimestamp(p[0], obter_timezone()).strftime("%H:%M")
                p_out = datetime.datetime.fromtimestamp(p[1], obter_timezone()).strftime("%H:%M")
                registros_por_dia[data_str].append(f'  ╰ ⏸️ Pausa: `{p_in}` → Volta: `{p_out}`')

        sign_total = "-" if total_semana_segundos < 0 else ""
        abs_total = abs(total_semana_segundos)
        hr_total = str(abs_total // 3600).zfill(2)
        mins_total = str((abs_total % 3600) // 60).zfill(2)
        
        desc = f'Funcionário: {usuario.mention}\n⏱️ **Tempo Total na Semana: `{sign_total}{hr_total}h {mins_total}m`**'
        if valor_hora > 0:
            mins_pagar = (abs_total // 3600) * 60 + ((abs_total % 3600) // 60)
            pagamento_total = (mins_pagar / 60) * valor_hora * (-1 if total_semana_segundos < 0 else 1)
            desc += f'\n💰 **Pagamento Semanal: `{formatar_moeda(pagamento_total)}`**'
            
        embed = discord.Embed(
            title='📋 Registros de Pica-Ponto',
            description=desc,
            color=discord.Colour.yellow()
        )
        embed.set_thumbnail(url=usuario.display_avatar)
        
        for dia, regs in registros_por_dia.items():
            campo_valor = ''
            for r in regs:
                campo_valor += r + '\n'
            if len(campo_valor) > 1024:
                campo_valor = campo_valor[:1020] + '...'
            seg_dia = total_dia_segundos.get(dia, 0)
            sign_dia = "-" if seg_dia < 0 else ""
            abs_seg = abs(seg_dia)
            hr_dia = str(abs_seg // 3600).zfill(2)
            min_dia = str((abs_seg % 3600) // 60).zfill(2)
            
            titulo_campo = f'📅 {dia}  —  ⏱️ `{sign_dia}{hr_dia}h {min_dia}m`'
            if valor_hora > 0:
                mins_pagar = (abs_seg // 3600) * 60 + ((abs_seg % 3600) // 60)
                pagamento_dia = (mins_pagar / 60) * valor_hora * (-1 if seg_dia < 0 else 1)
                titulo_campo += f'  —  💰 `{formatar_moeda(pagamento_dia)}`'
                
            embed.add_field(name=titulo_campo, value=campo_valor.strip(), inline=False)
        
        embed.set_footer(text='🟡 = Fechado por staff  |  Horários no fuso configurado')
        await ctx.respond(embed=embed, ephemeral=True)


    @commands.slash_command(description='[DEV] Faz um backup local na máquina do dev.', contexts={discord.InteractionContextType.guild})
    async def backup(self, ctx: discord.ApplicationContext):
        if ctx.user.id == config["owner_id"]:
            await ctx.reply(content='Backup atual:', file=discord.File('db.sqlite3'))
        else:
            await ctx.reply('❌ ERRO! Comando disponível apenas para desenvolvedores.')

    @commands.slash_command(name="ponto", description='Inicia o seu pica-ponto', contexts={discord.InteractionContextType.guild}, default_member_permissions=None)
    async def bateponto(self, ctx: discord.ApplicationContext):
        cargo_ponto = ctx.guild.get_role(config['ponto_role_id'])
        if cargo_ponto not in ctx.author.roles:
            return await ctx.respond('❌ Não tens permissão para usar o pica-ponto.', ephemeral=True)
        if ctx.user.id in active_pontos:
            estado = active_pontos[ctx.user.id]
            try:
                old_msg = await ctx.channel.fetch_message(estado["msg_id"])
                await old_msg.delete()
            except: pass
            
            horario_inicio = estado["inicio"]
            display_horario = horario_inicio + estado["total_pausa"]
            desc = f'**→ <:busts_in_silhouette:1269035235463397397> Funcionário:** {ctx.user.mention}\n\n'
            
            if estado["status"] == "pausado":
                trabalhado = estado["inicio_pausa"] - horario_inicio - estado["total_pausa"]
                h, m = int(trabalhado // 3600), int((trabalhado % 3600) // 60)
                desc += f'**→ <:alarm_clock:1269034530388574309> Tempo Trabalhado:** `{h}h:{m}m` (Pausado)\n\n'
            else:
                desc += f'**→ <:alarm_clock:1269034530388574309> Iniciado em:** <t:{horario_inicio}> (<t:{display_horario}:R>)\n\n'
                
            desc += '**❗ Quando encerrar o seu serviço, encerre o pica-ponto no botão abaixo**\n'
            
            for p in estado["pausas"]:
                p_in = datetime.datetime.fromtimestamp(p[0], obter_timezone()).strftime("%H:%M")
                p_out = datetime.datetime.fromtimestamp(p[1], obter_timezone()).strftime("%H:%M")
                desc += f'\n**⏸️ Pausa:** `{p_in}` **▶️ Volta:** `{p_out}`'
                
            if estado["status"] == "pausado":
                p_in = datetime.datetime.fromtimestamp(estado["inicio_pausa"], obter_timezone()).strftime("%H:%M")
                desc += f'\n**⏸️ Pausa:** `{p_in}` *(Em andamento...)*'
                
            embed = discord.Embed(description=desc, color=discord.Colour.yellow() if estado["status"] == "pausado" else discord.Colour.green())
            embed.set_author(name=f'Pica-Ponto de {ctx.user}', icon_url=ctx.user.display_avatar)
            embed.set_footer(text=f'{config["server_name"]} • 2026')
            
            msg = await ctx.channel.send(embed=embed, view=finalizarPonto())
            estado["msg_id"] = msg.id
            save_active_pontos()
            return await ctx.respond("✅ Seu painel de pica-ponto foi atualizado neste canal!", ephemeral=True)
            
        horario = int(datetime.datetime.now(obter_timezone()).timestamp())
        active_pontos[ctx.user.id] = {
            "inicio": horario,
            "msg_id": None,
            "status": "ativo",
            "inicio_pausa": 0,
            "total_pausa": 0,
            "pausas": []
        }

        embed = discord.Embed(description=f'**→ <:busts_in_silhouette:1269035235463397397> Funcionário:** {ctx.user.mention}\n\n'
                              f'**→ <:alarm_clock:1269034530388574309> Iniciado em:** <t:{horario}> (<t:{horario}:R>)\n\n'
                              '**❗ Quando encerrar o seu serviço, encerre o pica-ponto no botão abaixo**',
                              color=discord.Colour.green())
        embed.set_author(name=f'Pica-Ponto de {ctx.user}', icon_url=ctx.user.display_avatar)
        embed.set_footer(text=f'{config["server_name"]} • 2026')
        
        await ctx.respond("✅ Pica-Ponto iniciado com sucesso!", ephemeral=True)
        msg = await ctx.channel.send(embed=embed, view=finalizarPonto())
        active_pontos[ctx.user.id]["msg_id"] = msg.id
        save_active_pontos()


class OpcoesFechamentoStaff(View):
    def __init__(self, target_user_id: int, original_message: discord.Message):
        super().__init__(timeout=120.0)
        self.target_user_id = target_user_id
        self.original_message = original_message

    async def fechar_ponto(self, inter: discord.Interaction, contabiliza: bool):
        user_id = self.target_user_id
        if user_id not in active_pontos or active_pontos[user_id]["msg_id"] != self.original_message.id:
            return await inter.response.send_message("❌ O ponto já foi encerrado ou expirou.", ephemeral=True)
            
        await inter.response.defer()
        estado = active_pontos[user_id]
        try:
            horario_atual = int(datetime.datetime.now(obter_timezone()).timestamp())
            if estado["status"] == "pausado":
                duracao_pausa = horario_atual - estado["inicio_pausa"]
                estado["total_pausa"] += duracao_pausa
                estado["pausas"].append([estado["inicio_pausa"], horario_atual])
                
            horario_inicio = estado["inicio"]
            segundos_totais = horario_atual - horario_inicio - estado["total_pausa"]
            if segundos_totais < 0: segundos_totais = 0
            horas, minutos = int(segundos_totais // 3600), int((segundos_totais % 3600) // 60)
            active_pontos.pop(user_id)
            save_active_pontos()
            
            user = inter.guild.get_member(int(user_id))
            
            if contabiliza:
                await db.add_time(int(user_id), segundos_totais)
            
            import json
            pauses_json = json.dumps(estado["pausas"])
            await db.create_registry(int(user_id), horario_inicio, horario_atual, inter.user.id, segundos_totais if contabiliza else 0, pauses_json)
            
            canal_log = inter.guild.get_channel(config["log_channel_id"])
            data_abertura = datetime.datetime.fromtimestamp(horario_inicio, obter_timezone()).strftime("%d/%m/%Y, %H:%M:%S")
            pausas_desc = ''
            for p in estado["pausas"]:
                p_in = datetime.datetime.fromtimestamp(p[0], obter_timezone()).strftime("%d/%m/%Y %H:%M")
                p_out = datetime.datetime.fromtimestamp(p[1], obter_timezone()).strftime("%H:%M")
                pausas_desc += f'\n**→ `Pausa`: {p_in} \u2192 Volta: {p_out}**'
            
            if contabiliza:
                log_desc = f'**→ `Status Pica-Ponto`: Fechado por {inter.user.mention}** *(horas contabilizadas)*'
                log_color = discord.Colour.green()
                aviso_obs = 'Suas horas foram contabilizadas.'
            else:
                log_desc = f'**→ `Status Pica-Ponto`: Fechado por {inter.user.mention}** *(horas não contabilizadas)*'
                log_color = discord.Colour.yellow()
                aviso_obs = 'Suas horas não foram contabilizadas.'
                
            embed_log = discord.Embed(description=f'{log_desc}\n**→ `Funcionário`: {user.mention}**\n'
                f'**→ `Horário de Abertura`: {data_abertura}**\n'
                f'**→ `Horário de Fechamento`: {datetime.datetime.now(obter_timezone()).strftime("%d/%m/%Y, %H:%M:%S")}**\n'
                f'**→ `Tempo total de serviço`: {str(horas).zfill(2)} horas e {str(minutos).zfill(2)} minutos**'
                + pausas_desc, colour=log_color)
            embed_log.set_author(name='LOG: Pica-Ponto fechado por Alto Comando/Staff', icon_url=inter.user.display_avatar)
            
            if canal_log:
                await canal_log.send(embed=embed_log)
                
            if user:
                try:
                    await user.send(f'**<:aviso:1269036173381206132> AVISO:** Seu pica-ponto foi finalizado por: {inter.user.mention}!\n<:sirene:1269032464374829087>Tome cuidado em deixar o pica-ponto aberto ao sair de serviço. Em caso de dúvidas, procure o responsável por ter finalizado o seu ponto.\n> <:relogio:1269034530388574309> Tempo com pica-ponto aberto: **`{str(horas).zfill(2)} horas`** e **`{str(minutos).zfill(2)} minutos`**\n**`OBS`:** {aviso_obs}')
                except Exception: pass
                
        except Exception as e:
            print(e)
            
        try:
            await self.original_message.delete()
        except Exception: pass
        
        await inter.edit_original_response(content=f'<a:check:1269034091882221710> **Pica-ponto finalizado!** As horas {"foram" if contabiliza else "não foram"} contabilizadas.', view=None)


    @discord.ui.button(label='Contabiliza', style=discord.ButtonStyle.success)
    async def contabiliza_callback(self, button, inter: discord.Interaction):
        await self.fechar_ponto(inter, contabiliza=True)

    @discord.ui.button(label='Não Contabiliza', style=discord.ButtonStyle.danger)
    async def nao_contabiliza_callback(self, button, inter: discord.Interaction):
        await self.fechar_ponto(inter, contabiliza=False)


class finalizarPonto(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Pausar', emoji='⏸️', style=discord.ButtonStyle.secondary, custom_id="button_pause")
    async def pause_callback(self, button, inter: discord.Interaction):
        cargo_adm = inter.guild.get_role(config["staff_role_id"]) if inter.guild else None
        is_staff = cargo_adm in inter.user.roles if cargo_adm and hasattr(inter.user, "roles") else False
        
        target_user_id = None
        for u_id, est in active_pontos.items():
            if est["msg_id"] == inter.message.id:
                target_user_id = u_id
                break
                
        if not target_user_id:
            return await inter.response.send_message("❌ Este painel de pica-ponto expirou ou o bot foi reiniciado.", ephemeral=True)
            
        if inter.user.id != target_user_id and not is_staff:
            return await inter.response.send_message("❌ Você não tem permissão para pausar o pica-ponto de outra pessoa.", ephemeral=True)
            
        estado = active_pontos[target_user_id]
        agora = int(datetime.datetime.now(obter_timezone()).timestamp())
        
        if estado["status"] == "ativo":
            estado["status"] = "pausado"
            estado["inicio_pausa"] = agora
            button.label = "Retomar"
            button.emoji = "▶️"
            button.style = discord.ButtonStyle.success
            await inter.response.defer()
        else:
            estado["status"] = "ativo"
            duracao_pausa = agora - estado["inicio_pausa"]
            estado["total_pausa"] += duracao_pausa
            estado["pausas"].append([estado["inicio_pausa"], agora])
            estado["inicio_pausa"] = 0
            
            button.label = "Pausar"
            button.emoji = "⏸️"
            button.style = discord.ButtonStyle.secondary
            await inter.response.defer()

        save_active_pontos()

        target_member = inter.guild.get_member(int(target_user_id)) if inter.guild else None
        target_mention = target_member.mention if target_member else f"<@{target_user_id}>"
        target_name = target_member.name if target_member else str(target_user_id)
        target_avatar = target_member.display_avatar if target_member else None

        horario_inicio = estado["inicio"]
        display_horario = horario_inicio + estado["total_pausa"]
        
        desc = f'**→ <:busts_in_silhouette:1269035235463397397> Funcionário:** {target_mention}\n\n'
        
        if estado["status"] == "pausado":
            trabalhado = estado["inicio_pausa"] - horario_inicio - estado["total_pausa"]
            h, m = int(trabalhado // 3600), int((trabalhado % 3600) // 60)
            desc += f'**→ <:alarm_clock:1269034530388574309> Tempo Trabalhado:** `{h}h:{m}m` (Pausado)\n\n'
        else:
            desc += f'**→ <:alarm_clock:1269034530388574309> Iniciado em:** <t:{horario_inicio}> (<t:{display_horario}:R>)\n\n'
            
        desc += '**❗ Quando encerrar o seu serviço, encerre o pica-ponto no botão abaixo**\n'
        
        for p in estado["pausas"]:
            p_in = datetime.datetime.fromtimestamp(p[0], obter_timezone()).strftime("%H:%M")
            p_out = datetime.datetime.fromtimestamp(p[1], obter_timezone()).strftime("%H:%M")
            desc += f'\n**⏸️ Pausa:** `{p_in}` **▶️ Volta:** `{p_out}`'
            
        if estado["status"] == "pausado":
            p_in = datetime.datetime.fromtimestamp(estado["inicio_pausa"], obter_timezone()).strftime("%H:%M")
            desc += f'\n**⏸️ Pausa:** `{p_in}` *(Em andamento...)*'
            
        novo_embed = discord.Embed(description=desc, color=discord.Colour.yellow() if estado["status"] == "pausado" else discord.Colour.green())
        if target_avatar:
            novo_embed.set_author(name=f'Pica-Ponto de {target_name}', icon_url=target_avatar)
        else:
            novo_embed.set_author(name=f'Pica-Ponto de {target_name}')
        novo_embed.set_footer(text=f'{config["server_name"]} • 2026')
        
        await inter.message.edit(embed=novo_embed, view=self)

    @discord.ui.button(label='Finalizar', emoji='⏹', style=discord.ButtonStyle.danger, custom_id="button_end")
    async def end_callback(self, button, inter: discord.Interaction):
        cargo_adm = inter.guild.get_role(config["staff_role_id"])
        
        if cargo_adm in inter.user.roles:
            for user_id, estado in list(active_pontos.items()):
                if estado["msg_id"] == inter.message.id:
                    if inter.user.id != user_id:
                        view_opcoes = OpcoesFechamentoStaff(user_id, inter.message)
                        return await inter.response.send_message(
                            f"Você está encerrando o ponto de <@{user_id}>. Deseja contabilizar as horas?",
                            view=view_opcoes, ephemeral=True
                        )
                    break
                    
        if inter.user.id not in active_pontos:
            return await inter.response.send_message("❌ Seu pica-ponto expirou ou o bot foi reiniciado. Inicie um novo!", ephemeral=True)
        if inter.message.id != active_pontos[inter.user.id]["msg_id"]:
            return await inter.response.send_message("❌ Este não é o seu painel ativo mais recente.", ephemeral=True)

        estado = active_pontos[inter.user.id]
        
        await inter.response.defer(ephemeral=True)
        try:
            await inter.message.delete()
        except Exception: pass

        horario_atual = int(datetime.datetime.now(obter_timezone()).timestamp())
        if estado["status"] == "pausado":
            duracao_pausa = horario_atual - estado["inicio_pausa"]
            estado["total_pausa"] += duracao_pausa
            estado["pausas"].append([estado["inicio_pausa"], horario_atual])

        horario_inicio = estado["inicio"]
        segundos_totais = horario_atual - horario_inicio - estado["total_pausa"]
        if segundos_totais < 0: segundos_totais = 0
        horas, minutos = int(segundos_totais // 3600), int((segundos_totais % 3600) // 60)
        active_pontos.pop(inter.user.id)
        save_active_pontos()

        await db.add_time(inter.user.id, segundos_totais)
        
        import json
        pauses_json = json.dumps(estado["pausas"])
        await db.create_registry(inter.user.id, horario_inicio, horario_atual, False, segundos_totais, pauses_json)

        await inter.followup.send(f'⏰ **Serviço finalizado!**\n⏰ Tempo total de serviço: `{horas}` horas e `{minutos}` minutos', ephemeral=True)

        canal_log = inter.guild.get_channel(config["log_channel_id"])

        data_abertura = datetime.datetime.fromtimestamp(horario_inicio, obter_timezone()).strftime("%d/%m/%Y, %H:%M:%S")
        pausas_desc = ''
        for p in estado["pausas"]:
            p_in = datetime.datetime.fromtimestamp(p[0], obter_timezone()).strftime("%d/%m/%Y %H:%M")
            p_out = datetime.datetime.fromtimestamp(p[1], obter_timezone()).strftime("%H:%M")
            pausas_desc += f'\n**→ `Pausa`: {p_in} \u2192 Volta: {p_out}**'
        embed_log = discord.Embed(description=f'**→ `Status Pica-Ponto`: Fechado**\n**→ `Funcionário`: {inter.user.mention}**\n'
            f'**→ `Horário de Abertura`: {data_abertura}**\n'
            f'**→ `Horário de Fechamento`: {datetime.datetime.now(obter_timezone()).strftime("%d/%m/%Y, %H:%M:%S")}**\n'
            f'**→ `Tempo total de serviço`: {str(horas).zfill(2)} horas e {str(minutos).zfill(2)} minutos**'
            + pausas_desc,
            colour=discord.Colour.red())

        embed_log.set_author(name=f'LOG: Pica-Ponto fechado por {inter.user.name}', icon_url=inter.user.display_avatar)
        await canal_log.send(embed=embed_log)


class BotoesSemana(View):
    def __init__(self, top_todos, reset: bool = False):
        super().__init__(timeout=30.0)
        self.top_todos = top_todos
        self.reset = reset

    async def _enviar_relatorio(self, inter: discord.Interaction):
        """Envia o cabeçalho + embeds por funcionário + backup."""
        if self.top_todos:
            embed_cabecalho = discord.Embed(
                title='\U0001f4c5 Relatório Semanal de Horas',
                description=f'Por {inter.user.mention}  •  {datetime.datetime.now(obter_timezone()).strftime("%d/%m/%Y %H:%M")}',
                color=discord.Colour.blue()
            )
            await inter.channel.send(embed=embed_cabecalho)

            for user_data in self.top_todos:
                user_id = user_data[0]
                total_seg = user_data[1]
                sign_total = "-" if total_seg < 0 else ""
                abs_total = abs(total_seg)
                horas_total = int(abs_total // 3600)
                minutos_total = int((abs_total % 3600) // 60)

                registros = await db.get_all_user_registries(user_id)
                por_dia = {}
                nao_contabilizados = []
                for reg in registros:
                    data_str = datetime.datetime.fromtimestamp(reg[0], obter_timezone()).strftime("%d/%m/%Y")
                    por_dia[data_str] = por_dia.get(data_str, 0) + (reg[3] or 0)
                    if reg[3] == 0 and reg[2] and reg[2] > 10000:
                        nao_contabilizados.append((data_str, reg[2]))

                func_db = await db.get_funcionario(user_id)
                if func_db:
                    nome_exib = f"[{func_db[1]}] {func_db[2]}"
                else:
                    membro = inter.guild.get_member(user_id)
                    nome_exib = membro.display_name if membro else f"ID: {user_id}"

                embed_user = discord.Embed(
                    description=f'**{nome_exib}**\n\u23f1\ufe0f **Total Semanal: `{sign_total}{str(horas_total).zfill(2)}h {str(minutos_total).zfill(2)}m`**',
                    color=discord.Colour.blurple()
                )
                for dia, seg_dia in sorted(por_dia.items()):
                    if seg_dia == 0: continue
                    sign_dia = "-" if seg_dia < 0 else ""
                    abs_seg = abs(seg_dia)
                    h_dia = int(abs_seg // 3600)
                    m_dia = int((abs_seg % 3600) // 60)
                    embed_user.add_field(
                        name=f'\U0001f4c5 {dia}',
                        value=f'`{sign_dia}{str(h_dia).zfill(2)}h {str(m_dia).zfill(2)}m`',
                        inline=True
                    )
                    
                for nc in nao_contabilizados:
                    data_str, staff_id = nc
                    embed_user.add_field(
                        name=f'\U0001f4c5 {data_str} (Não Contabilizado)',
                        value=f'`00h 00m` • Fechado por <@{staff_id}>',
                        inline=False
                    )
                    
                await inter.channel.send(embed=embed_user)
        else:
            await inter.channel.send('\u26a0\ufe0f Nenhum funcionário com cargo de ponto e horas registadas esta semana.')

        # Backup
        try:
            await inter.channel.send(
                content='\U0001f4be **Backup da base de dados:**',
                file=discord.File('db.sqlite3')
            )
        except Exception as e:
            await inter.channel.send(f'\u274c Erro ao enviar backup: `{e}`')

        # PDF do Relatório
        try:
            pdf_path = await gerar_pdf_semanal(self.top_todos, inter.guild)
            if pdf_path:
                await inter.channel.send(
                    content='\U0001f4c4 **Relatório Semanal Completo em PDF:**',
                    file=discord.File(pdf_path)
                )
                dono_id = config.get("owner_id")
                if dono_id:
                    dono = inter.client.get_user(dono_id)
                    if not dono:
                        try:
                            dono = await inter.client.fetch_user(dono_id)
                        except:
                            pass
                    if dono:
                        try:
                            await dono.send(
                                content='\U0001f4c4 **Relatório Semanal Completo em PDF:**',
                                file=discord.File(pdf_path)
                            )
                        except Exception as e:
                            print(f"Erro ao enviar PDF para o dono: {e}")
        except Exception as e:
            await inter.channel.send(f'\u274c Erro ao gerar PDF: `{e}`')

    @discord.ui.button(label='\u2714\ufe0f Confirmar', style=discord.ButtonStyle.danger)
    async def confirmar_callback(self, button, inter: discord.Interaction):
        for child in self.children:
            child.disabled = True
        await inter.response.edit_message(view=self)

        await self._enviar_relatorio(inter)

        if self.reset:
            # Arquiva a semana correctamente (associa pontos, cria pagamentos)
            resultado = await db.encerrar_semana(config.get('cargos_patentes', {}))
            # Cria nova semana activa para a próxima semana
            await db.get_or_criar_semana_activa()
            # Zera tempo semanal actual
            await db.reset_all_times()
            n_impagos = len(resultado.get('pagamentos', []))
            embed_ok = discord.Embed(
                title='\u2705 Semana Encerrada e Arquivada',
                description=f'Relatório publicado, backup enviado e semana arquivada com sucesso!\n'
                            f'**{n_impagos}** registo(s) de pagamento criado(s).\n'
                            f'Utilize o painel admin para marcar pagamentos: `https://ems.discloud.app/admin/definicoes`',
                color=discord.Colour.green()
            )
            await inter.followup.send(embed=embed_ok, ephemeral=True)
            canal_log = inter.guild.get_channel(config['log_channel_id'])
            embed_log = discord.Embed(
                description=f'**\u2192 `Staff`: {inter.user.mention}**\n**\u2192 Encerramento semanal efetuado. Semana arquivada com {n_impagos} pagamentos pendentes.**',
                colour=discord.Colour.red()
            )
            embed_log.set_author(name='LOG: Encerramento Semanal', icon_url=inter.user.display_avatar)
            if canal_log:
                await canal_log.send(embed=embed_log)
        else:
            embed_ok = discord.Embed(
                title='\u2705 Relatório Enviado',
                description='Relatório publicado e backup enviado. Os dados **não foram apagados**.',
                color=discord.Colour.green()
            )
            await inter.followup.send(embed=embed_ok, ephemeral=True)
            canal_log = inter.guild.get_channel(config['log_channel_id'])
            embed_log = discord.Embed(
                description=f'**\u2192 `Staff`: {inter.user.mention}**\n**\u2192 Relatório semanal gerado e backup enviado. Sem reset.**',
                colour=discord.Colour.blue()
            )
            embed_log.set_author(name='LOG: Relatório Semanal', icon_url=inter.user.display_avatar)
            await canal_log.send(embed=embed_log)

    @discord.ui.button(label='Cancelar', style=discord.ButtonStyle.secondary)
    async def cancelar_callback(self, button, inter: discord.Interaction):
        await inter.response.edit_message(
            embed=discord.Embed(description='\u274c Operção cancelada.', color=discord.Colour.greyple()),
            view=None
        )


class ConfirmarReset(View):
    def __init__(self):
        super().__init__(timeout=15.0)

    @discord.ui.button(label='Confirmar', style=discord.ButtonStyle.green)
    async def confirmar_callback(self, button, inter: discord.Interaction):
        await db.reset_all_times()
        await db.reset_all_registries()
        
        embed = discord.Embed(description='**Toda as informações (Horas/Minutos/Registros) dos pica-pontos foram resetadas!**',
                              color=discord.Colour.red())
        await inter.response.send_message(embed=embed)
        
        canal_log = inter.guild.get_channel(config['log_channel_id'])
        embed_log = discord.Embed(description=f'**→ `Staff`: {inter.user.mention}**\n'
            f'**→ Toda a base de dados de pica-ponto acaba de ser resetada.**', colour=discord.Colour.red())
        embed_log.set_author(name='LOG: Reset ALL Database', icon_url=inter.user.display_avatar)
        await canal_log.send(embed=embed_log)

class BotoesReset(View):
    def __init__(self):
        super().__init__(timeout=30.0)

    @discord.ui.button(label='Sim', style=discord.ButtonStyle.danger)
    async def confirm_callback(self, button, inter: discord.Interaction):
        embed = discord.Embed(description='**Você quer realmente resetar toda a base de dados?**',
                              color=discord.Colour.red())
        await inter.response.edit_message(embed=embed, view=ConfirmarReset())

    @discord.ui.button(label='Não', style=discord.ButtonStyle.blurple)
    async def recusar_callback(self, button, inter: discord.Interaction):
        await inter.message.delete()


def setup(client):
    client.add_cog(PicaPonto(client))