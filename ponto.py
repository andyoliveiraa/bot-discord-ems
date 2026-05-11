import datetime
import discord
from discord.commands import Option
from discord.ext import commands, tasks
from discord.ui import View, InputText, Modal
from pytz import timezone
import json
from db import Database, get_configs

db = Database('db.sqlite3')
config = get_configs()

active_pontos = {}
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
                
        pagamento_semana = (total_seg / 3600) * valor_hora
        total_semana_geral += total_seg
        total_pagamento_geral += pagamento_semana
        
        horas_total = int(total_seg // 3600)
        minutos_total = int((total_seg % 3600) // 60)
        
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 10, txt=f"Funcionario: {nome_func}", ln=1, align='L')
        pdf.set_font("Arial", size=11)
        pdf.cell(200, 8, txt=f"Total Semana: {horas_total}h {minutos_total}m - A receber: {formatar_moeda_pdf(pagamento_semana)}", ln=1, align='L')
        
        registros = await db.get_all_user_registries(user_id)
        por_dia = {}
        for reg in registros:
            data_str = datetime.datetime.fromtimestamp(reg[0], timezone(config["timezone"])).strftime("%d/%m/%Y")
            por_dia[data_str] = por_dia.get(data_str, 0) + (reg[3] or 0)
            
        for dia, seg_dia in sorted(por_dia.items()):
            h_dia = int(seg_dia // 3600)
            m_dia = int((seg_dia % 3600) // 60)
            pagamento_dia = (seg_dia / 3600) * valor_hora
            pdf.cell(200, 6, txt=f"  - {dia}: {h_dia}h {m_dia}m | A receber: {formatar_moeda_pdf(pagamento_dia)}", ln=1, align='L')
            
        pdf.cell(200, 5, txt="", ln=1)
        
    pdf.set_font("Arial", 'B', 13)
    pdf.cell(200, 10, txt="RESUMO DA SEMANA", ln=1, align='C')
    h_geral = int(total_semana_geral // 3600)
    m_geral = int((total_semana_geral % 3600) // 60)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Total de Horas Trabalhadas: {h_geral}h {m_geral}m", ln=1, align='L')
    pdf.cell(200, 10, txt=f"Total a Pagar: {formatar_moeda_pdf(total_pagamento_geral)}", ln=1, align='L')
    
    file_path = "relatorio_semanal.pdf"
    pdf.output(file_path)
    return file_path

def save_active_pontos():
    import json
    with open(ACTIVE_PONTOS_FILE, "w") as f:
        json.dump(active_pontos, f)

class PicaPonto(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.auto_close_task.start()
        self.auto_backup_task.start()

    def cog_unload(self):
        self.auto_close_task.cancel()
        self.auto_backup_task.cancel()

    @tasks.loop(minutes=5)
    async def auto_close_task(self):
        agora = int(datetime.datetime.now(timezone(config["timezone"])).timestamp())
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
                    data_abertura = datetime.datetime.fromtimestamp(horario_inicio, timezone(config["timezone"])).strftime("%d/%m/%Y, %H:%M:%S")
                    embed_log = discord.Embed(description=f'**→ `Status Pica-Ponto`: Fechado Automaticamente (24h Inatividade)** *(horas não contabilizadas)*\n**→ `Funcionário`: {user.mention}**\n'
                        f'**→ `Horário de Abertura`: {data_abertura}**\n'
                        f'**→ `Horário de Fechamento`: {datetime.datetime.now(timezone(config["timezone"])).strftime("%d/%m/%Y, %H:%M:%S")}**\n**→ `Tempo total de serviço`: 00 horas e 00 minutos**', colour=discord.Colour.dark_gray())
                    embed_log.set_author(name='LOG: Inatividade Detectada', icon_url=self.client.user.display_avatar)
                    await canal_log.send(embed=embed_log)
                    try:
                        await user.send(f'**<:aviso:1269036173381206132> AVISO:** Seu pica-ponto foi finalizado automaticamente por exceder 24 horas de inatividade!\n<:sirene:1269032464374829087> Suas horas não foram contabilizadas.')
                    except: pass

    @auto_close_task.before_loop
    async def before_auto_close_task(self):
        await self.client.wait_until_ready()

    @tasks.loop(time=datetime.time(hour=7, minute=0, tzinfo=timezone(config["timezone"])))
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

    @commands.Cog.listener()
    async def on_ready(self):
        print('Pica-Ponto carregado com sucesso!')
        await db.setup_db()
        self.client.add_view(view=finalizarPonto())
        await self.fechar_pontos_pendentes()

    async def fechar_pontos_pendentes(self):
        import os
        if not os.path.exists(ACTIVE_PONTOS_FILE):
            return
            
        try:
            with open(ACTIVE_PONTOS_FILE, "r") as f:
                pontos_pendentes = json.load(f)
        except Exception:
            return
            
        if not pontos_pendentes:
            return
            
        agora = int(datetime.datetime.now(timezone(config["timezone"])).timestamp())
        canal_log = self.client.get_channel(config["log_channel_id"])
        
        for user_id_str, estado in pontos_pendentes.items():
            user_id = int(user_id_str)
            if estado["status"] == "pausado":
                estado["total_pausa"] += agora - estado["inicio_pausa"]
                estado["pausas"].append([estado["inicio_pausa"], agora])
            
            horario_inicio = estado["inicio"]
            segundos_totais = agora - horario_inicio - estado["total_pausa"]
            if segundos_totais < 0: segundos_totais = 0
            
            await db.add_time(user_id, segundos_totais)
            pauses_json = json.dumps(estado["pausas"])
            await db.create_registry(user_id, horario_inicio, agora, True, segundos_totais, pauses_json)
            
            if canal_log:
                horas, minutos = int(segundos_totais // 3600), int((segundos_totais % 3600) // 60)
                data_abertura = datetime.datetime.fromtimestamp(horario_inicio, timezone(config["timezone"])).strftime("%d/%m/%Y, %H:%M:%S")
                user = self.client.get_user(user_id)
                user_mention = user.mention if user else f"<@{user_id}>"
                
                embed_log = discord.Embed(description=f'**→ `Status Pica-Ponto`: Fechado Automático (Crash/Restart)**\n**→ `Funcionário`: {user_mention}**\n'
                    f'**→ `Horário de Abertura`: {data_abertura}**\n'
                    f'**→ `Horário de Fechamento`: {datetime.datetime.now(timezone(config["timezone"])).strftime("%d/%m/%Y, %H:%M:%S")}**\n'
                    f'**→ `Tempo total de serviço`: {str(horas).zfill(2)} horas e {str(minutos).zfill(2)} minutos**', colour=discord.Colour.orange())
                embed_log.set_author(name='LOG: Pica-Ponto fechado pelo Sistema', icon_url=self.client.user.display_avatar)
                try:
                    await canal_log.send(embed=embed_log)
                except Exception:
                    pass
                    
        try:
            os.remove(ACTIVE_PONTOS_FILE)
        except:
            pass
        active_pontos.clear()

    @commands.slash_command(description='[ADM] Adiciona horas/minutos para uma pessoa no pica-ponto', contexts={discord.InteractionContextType.guild})
    @commands.has_any_role(config['staff_role_id'])
    async def addtempo(self, ctx: discord.ApplicationContext, usuario: Option(discord.Member, 'Selecione o usuário', required=True),
                    horas: Option(int, "Digite a quantidade de horas", required=True, min_value=0),
                    minutos: Option(int, "Digite a quantidade de minutos", required=True, min_value=0, max_value=59),
                    motivo: Option(str, "Digite o motivo da adição de horas (Ficará em exibição no log)", required=True)):

        func = await db.get_funcionario(usuario.id)
        if not func:
            return await ctx.respond('❌ Este usuário não é um funcionário registrado no sistema.', ephemeral=True)

        total = (int(horas) * 3600) + (int(minutos) * 60)
        await db.add_time(usuario.id, total)

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
    @commands.has_any_role(config['staff_role_id'])
    async def deltempo(self, ctx: discord.ApplicationContext, usuario: Option(discord.Member, 'Selecione o usuário', required=True),
                    horas: Option(int, "Digite a quantidade de horas", required=True, min_value=0),
                    minutos: Option(int, "Digite a quantidade de minutos", required=True, min_value=0, max_value=59),
                    motivo: Option(str, "Digite o motivo da remoção de horas (Ficará em exibição no log)", required=True)):

        func = await db.get_funcionario(usuario.id)
        if not func:
            return await ctx.respond('❌ Este usuário não é um funcionário registrado no sistema.', ephemeral=True)

        total = (int(horas) * 3600) + (int(minutos) * 60)
        await db.del_time(usuario.id, total)

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
    @commands.has_any_role(config['staff_role_id'])
    async def contratar(self, ctx: discord.ApplicationContext,
                       usuario: Option(discord.Member, 'Selecione o usuário', required=True),
                       patente: Option(str, 'Selecione a patente', choices=[discord.OptionChoice(name=v['nome'], value=k) for k, v in config.get("cargos_patentes", {}).items()], required=True),
                       nome: Option(str, 'Nome do funcionário', required=True),
                       motivo: Option(str, 'Motivo da contratação', required=True)):
        
        await ctx.defer()
        
        patente_info = config["cargos_patentes"][patente]
        letra = patente_info["letra"]
        cargo_patente_id = patente_info["id"]
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
        
        try:
            await usuario.send(f'**<:aviso:1269036173381206132> AVISO!** Você foi contratado(a) e registrado(a) no sistema!\n**→ Staff:** {ctx.author.mention}\n**→ Patente:** {patente_info["nome"]}\n**→ Callsign:** `{callsign}`\n**→ Motivo:** {motivo}')
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
    @commands.has_any_role(config['staff_role_id'])
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
            cargo_patente = ctx.guild.get_role(patente_info["id"])
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
            
        await db.remove_funcionario(usuario.id)
        
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
    @commands.has_any_role(config['staff_role_id'])
    async def promover(self, ctx: discord.ApplicationContext,
                       usuario: Option(discord.Member, 'Selecione o usuário', required=True),
                       nova_patente: Option(str, 'Selecione a nova patente', choices=[discord.OptionChoice(name=v['nome'], value=k) for k, v in config.get("cargos_patentes", {}).items()], required=True),
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
            cargo_antigo = ctx.guild.get_role(patente_antiga_info["id"])
            if cargo_antigo:
                cargos_para_remover.append(cargo_antigo)
                
        cargos_para_adicionar = []
        cargo_novo = ctx.guild.get_role(nova_patente_info["id"])
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
            
        await db.add_funcionario(usuario.id, nova_patente, novo_callsign, nome_func)
        
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



    @commands.slash_command(description='[ADM] Reseta as horas do pica-ponto de um determinado usuário', contexts={discord.InteractionContextType.guild})
    @commands.has_any_role(config['staff_role_id'])
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

    @commands.slash_command(description='[ADM] Configura para 0 horas e apaga os dados de todos os usuários registrados.', contexts={discord.InteractionContextType.guild})
    @commands.has_any_role(config['staff_role_id'])
    async def resetar_todos(self, ctx: discord.ApplicationContext):

        await ctx.respond(view=BotoesReset())

    @commands.slash_command(description='Retorna o ranking das top 10 pessoas com mais horas na semana.', contexts={discord.InteractionContextType.guild})
    async def ranking(self, ctx: discord.ApplicationContext):

        top10 = await db.get_ranking()
        
        embed = discord.Embed(title='🏆 Ranking Semanal (TOP 10)', color=discord.Colour.gold())
        for index, user in enumerate(top10):
            horas, minutos = int(user[1] // 3600), int((user[1] % 3600) // 60)
            
            func_db = await db.get_funcionario(user[0])
            pagamento_str = ""
            if func_db:
                patente_info = config.get("cargos_patentes", {}).get(func_db[0])
                if patente_info:
                    valor_hora = patente_info.get("valor_hora", 0)
                    pagamento = (user[1] / 3600) * valor_hora
                    pagamento_str = f' - 💰 `{formatar_moeda(pagamento)}`'
            
            embed.add_field(name=f'{index+1}º Lugar', value=f'<@{user[0]}> - `{horas}h:{minutos}m`{pagamento_str}', inline=False)
            
        await ctx.respond(embed=embed)

    @commands.slash_command(name='semana', description='[ADM] Mostra o relatório semanal de horas e envia backup.', contexts={discord.InteractionContextType.guild})
    @commands.has_any_role(config['staff_role_id'])
    async def semana(self, ctx: discord.ApplicationContext):
        top_todos = await db.get_ranking(amount=100)
        # Filtrar apenas quem tem o cargo ponto_role_id
        cargo_ponto = ctx.guild.get_role(config['ponto_role_id'])
        top_filtrado = [u for u in top_todos if cargo_ponto and ctx.guild.get_member(u[0]) and cargo_ponto in ctx.guild.get_member(u[0]).roles]
        agora_str = datetime.datetime.now(timezone(config['timezone'])).strftime('%d/%m/%Y \u00e0s %H:%M')

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
    @commands.has_any_role(config['staff_role_id'])
    async def resetarsemana(self, ctx: discord.ApplicationContext):
        top_todos = await db.get_ranking(amount=100)
        cargo_ponto = ctx.guild.get_role(config['ponto_role_id'])
        top_filtrado = [u for u in top_todos if cargo_ponto and ctx.guild.get_member(u[0]) and cargo_ponto in ctx.guild.get_member(u[0]).roles]
        agora_str = datetime.datetime.now(timezone(config['timezone'])).strftime('%d/%m/%Y \u00e0s %H:%M')

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
            hr_inicio = datetime.datetime.fromtimestamp(k[0], timezone(config["timezone"])).strftime("%H:%M")
            hr_fim = datetime.datetime.fromtimestamp(k[1], timezone(config["timezone"])).strftime("%H:%M")
            data_str = datetime.datetime.fromtimestamp(k[0], timezone(config["timezone"])).strftime("%d/%m/%Y")
            
            staff = True if k[2] == 1 else False
            duracao = k[3]
            pausas_str = k[4] if len(k) > 4 else '[]'
            try:
                pausas = json.loads(pausas_str)
            except:
                pausas = []

            hr = str(duracao // 3600).zfill(2)
            mins = str((duracao % 3600) // 60).zfill(2)
            
            total_semana_segundos += duracao
            total_dia_segundos[data_str] = total_dia_segundos.get(data_str, 0) + duracao

            if data_str not in registros_por_dia:
                registros_por_dia[data_str] = []
                
            registros_por_dia[data_str].append(f'🟢 `{hr_inicio}` → `{hr_fim}`  **({hr}h {mins}m)**{"  🟡" if staff else ""}')
            for p in pausas:
                p_in = datetime.datetime.fromtimestamp(p[0], timezone(config["timezone"])).strftime("%H:%M")
                p_out = datetime.datetime.fromtimestamp(p[1], timezone(config["timezone"])).strftime("%H:%M")
                registros_por_dia[data_str].append(f'  ╰ ⏸️ Pausa: `{p_in}` → Volta: `{p_out}`')

        hr_total = str(total_semana_segundos // 3600).zfill(2)
        mins_total = str((total_semana_segundos % 3600) // 60).zfill(2)
        
        desc = f'Funcionário: {usuario.mention}\n⏱️ **Tempo Total na Semana: `{hr_total}h {mins_total}m`**'
        if valor_hora > 0:
            pagamento_total = (total_semana_segundos / 3600) * valor_hora
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
            hr_dia = str(seg_dia // 3600).zfill(2)
            min_dia = str((seg_dia % 3600) // 60).zfill(2)
            
            titulo_campo = f'📅 {dia}  —  ⏱️ `{hr_dia}h {min_dia}m`'
            if valor_hora > 0:
                pagamento_dia = (seg_dia / 3600) * valor_hora
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
                p_in = datetime.datetime.fromtimestamp(p[0], timezone(config["timezone"])).strftime("%H:%M")
                p_out = datetime.datetime.fromtimestamp(p[1], timezone(config["timezone"])).strftime("%H:%M")
                desc += f'\n**⏸️ Pausa:** `{p_in}` **▶️ Volta:** `{p_out}`'
                
            if estado["status"] == "pausado":
                p_in = datetime.datetime.fromtimestamp(estado["inicio_pausa"], timezone(config["timezone"])).strftime("%H:%M")
                desc += f'\n**⏸️ Pausa:** `{p_in}` *(Em andamento...)*'
                
            embed = discord.Embed(description=desc, color=discord.Colour.yellow() if estado["status"] == "pausado" else discord.Colour.green())
            embed.set_author(name=f'Pica-Ponto de {ctx.user}', icon_url=ctx.user.display_avatar)
            embed.set_footer(text=f'{config["server_name"]} • 2026')
            
            msg = await ctx.channel.send(embed=embed, view=finalizarPonto())
            estado["msg_id"] = msg.id
            return await ctx.respond("✅ Seu painel de pica-ponto foi atualizado neste canal!", ephemeral=True)
            
        horario = int(datetime.datetime.now(timezone(config["timezone"])).timestamp())
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


class finalizarPonto(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Pausar', emoji='⏸️', style=discord.ButtonStyle.secondary, custom_id="button_pause")
    async def pause_callback(self, button, inter: discord.Interaction):
        if inter.user.id not in active_pontos:
            return await inter.response.send_message("❌ Seu pica-ponto expirou ou o bot foi reiniciado. Inicie um novo!", ephemeral=True)
        if active_pontos[inter.user.id]["msg_id"] != inter.message.id:
            return await inter.response.send_message("❌ Este não é o seu painel ativo mais recente.", ephemeral=True)
            
        estado = active_pontos[inter.user.id]
        agora = int(datetime.datetime.now(timezone(config["timezone"])).timestamp())
        
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

        horario_inicio = estado["inicio"]
        display_horario = horario_inicio + estado["total_pausa"]
        
        desc = f'**→ <:busts_in_silhouette:1269035235463397397> Funcionário:** {inter.user.mention}\n\n'
        
        if estado["status"] == "pausado":
            trabalhado = estado["inicio_pausa"] - horario_inicio - estado["total_pausa"]
            h, m = int(trabalhado // 3600), int((trabalhado % 3600) // 60)
            desc += f'**→ <:alarm_clock:1269034530388574309> Tempo Trabalhado:** `{h}h:{m}m` (Pausado)\n\n'
        else:
            desc += f'**→ <:alarm_clock:1269034530388574309> Iniciado em:** <t:{horario_inicio}> (<t:{display_horario}:R>)\n\n'
            
        desc += '**❗ Quando encerrar o seu serviço, encerre o pica-ponto no botão abaixo**\n'
        
        for p in estado["pausas"]:
            p_in = datetime.datetime.fromtimestamp(p[0], timezone(config["timezone"])).strftime("%H:%M")
            p_out = datetime.datetime.fromtimestamp(p[1], timezone(config["timezone"])).strftime("%H:%M")
            desc += f'\n**⏸️ Pausa:** `{p_in}` **▶️ Volta:** `{p_out}`'
            
        if estado["status"] == "pausado":
            p_in = datetime.datetime.fromtimestamp(estado["inicio_pausa"], timezone(config["timezone"])).strftime("%H:%M")
            desc += f'\n**⏸️ Pausa:** `{p_in}` *(Em andamento...)*'
            
        novo_embed = discord.Embed(description=desc, color=discord.Colour.yellow() if estado["status"] == "pausado" else discord.Colour.green())
        novo_embed.set_author(name=f'Pica-Ponto de {inter.user}', icon_url=inter.user.display_avatar)
        novo_embed.set_footer(text=f'{config["server_name"]} • 2026')
        
        await inter.message.edit(embed=novo_embed, view=self)

    @discord.ui.button(label='Finalizar', emoji='⏹', style=discord.ButtonStyle.danger, custom_id="button_end")
    async def end_callback(self, button, inter: discord.Interaction):
        cargo_adm = inter.guild.get_role(config["staff_role_id"])
        
        if cargo_adm in inter.user.roles:
            for user_id, estado in list(active_pontos.items()):
                if estado["msg_id"] == inter.message.id:
                    if inter.user.id != user_id:
                        try:
                            horario_atual = int(datetime.datetime.now(timezone(config["timezone"])).timestamp())
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
                            import json
                            pauses_json = json.dumps(estado["pausas"])
                            await db.create_registry(int(user_id), horario_inicio, horario_atual, True, segundos_totais, pauses_json)
                            
                            canal_log = inter.guild.get_channel(config["log_channel_id"])
                            data_abertura = datetime.datetime.fromtimestamp(horario_inicio, timezone(config["timezone"])).strftime("%d/%m/%Y, %H:%M:%S")
                            pausas_desc = ''
                            for p in estado["pausas"]:
                                p_in = datetime.datetime.fromtimestamp(p[0], timezone(config["timezone"])).strftime("%d/%m/%Y %H:%M")
                                p_out = datetime.datetime.fromtimestamp(p[1], timezone(config["timezone"])).strftime("%H:%M")
                                pausas_desc += f'\n**→ `Pausa`: {p_in} \u2192 Volta: {p_out}**'
                            embed_log = discord.Embed(description=f'**→ `Status Pica-Ponto`: Fechado por {inter.user.mention}** *(horas não contabilizadas)*\n**→ `Funcionário`: {user.mention}**\n'
                                f'**→ `Horário de Abertura`: {data_abertura}**\n'
                                f'**→ `Horário de Fechamento`: {datetime.datetime.now(timezone(config["timezone"])).strftime("%d/%m/%Y, %H:%M:%S")}**\n'
                                f'**→ `Tempo total de serviço`: {str(horas).zfill(2)} horas e {str(minutos).zfill(2)} minutos**'
                                + pausas_desc, colour=discord.Colour.yellow())
                            embed_log.set_author(name='LOG: Pica-Ponto fechado por Alto Comando/Staff', icon_url=inter.user.display_avatar)
                            await canal_log.send(embed=embed_log)
                            await user.send(f'**<:aviso:1269036173381206132> AVISO:** Seu pica-ponto foi finalizado por: {inter.user.mention}!\n<:sirene:1269032464374829087>Tome cuidado em deixar o pica-ponto aberto ao sair de serviço. Em caso de dúvidas, procure o responsável por ter finalizado o seu ponto.\n> <:relogio:1269034530388574309> Tempo com pica-ponto aberto: **`{str(horas).zfill(2)} horas`** e **`{str(minutos).zfill(2)} minutos`**\n**`OBS`:** Suas horas não foram contabilizadas.')
                        except Exception as e:
                            print(e)
                        await inter.message.delete()
                        return await inter.response.send_message('<a:check:1269034091882221710> **Pica-ponto finalizado!** As horas não foram contabilizadas.', ephemeral=True)
                    break
                    
        if inter.user.id not in active_pontos:
            return await inter.response.send_message("❌ Seu pica-ponto expirou ou o bot foi reiniciado. Inicie um novo!", ephemeral=True)
        if inter.message.id != active_pontos[inter.user.id]["msg_id"]:
            return await inter.response.send_message("❌ Este não é o seu painel ativo mais recente.", ephemeral=True)

        estado = active_pontos[inter.user.id]
        
        await inter.message.delete()

        horario_atual = int(datetime.datetime.now(timezone(config["timezone"])).timestamp())
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

        await inter.response.send_message(f'⏰ **Serviço finalizado!**\n⏰ Tempo total de serviço: `{horas}` horas e `{minutos}` minutos', ephemeral=True)

        canal_log = inter.guild.get_channel(config["log_channel_id"])

        data_abertura = datetime.datetime.fromtimestamp(horario_inicio, timezone(config["timezone"])).strftime("%d/%m/%Y, %H:%M:%S")
        pausas_desc = ''
        for p in estado["pausas"]:
            p_in = datetime.datetime.fromtimestamp(p[0], timezone(config["timezone"])).strftime("%d/%m/%Y %H:%M")
            p_out = datetime.datetime.fromtimestamp(p[1], timezone(config["timezone"])).strftime("%H:%M")
            pausas_desc += f'\n**→ `Pausa`: {p_in} \u2192 Volta: {p_out}**'
        embed_log = discord.Embed(description=f'**→ `Status Pica-Ponto`: Fechado**\n**→ `Funcionário`: {inter.user.mention}**\n'
            f'**→ `Horário de Abertura`: {data_abertura}**\n'
            f'**→ `Horário de Fechamento`: {datetime.datetime.now(timezone(config["timezone"])).strftime("%d/%m/%Y, %H:%M:%S")}**\n'
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
                description=f'Por {inter.user.mention}  •  {datetime.datetime.now(timezone(config["timezone"])).strftime("%d/%m/%Y %H:%M")}',
                color=discord.Colour.blue()
            )
            await inter.channel.send(embed=embed_cabecalho)

            for user_data in self.top_todos:
                user_id = user_data[0]
                total_seg = user_data[1]
                horas_total = int(total_seg // 3600)
                minutos_total = int((total_seg % 3600) // 60)

                registros = await db.get_all_user_registries(user_id)
                por_dia = {}
                for reg in registros:
                    data_str = datetime.datetime.fromtimestamp(reg[0], timezone(config["timezone"])).strftime("%d/%m/%Y")
                    por_dia[data_str] = por_dia.get(data_str, 0) + (reg[3] or 0)

                embed_user = discord.Embed(
                    description=f'<@{user_id}>\n\u23f1\ufe0f **Total Semanal: `{str(horas_total).zfill(2)}h {str(minutos_total).zfill(2)}m`**',
                    color=discord.Colour.blurple()
                )
                for dia, seg_dia in sorted(por_dia.items()):
                    h_dia = int(seg_dia // 3600)
                    m_dia = int((seg_dia % 3600) // 60)
                    embed_user.add_field(
                        name=f'\U0001f4c5 {dia}',
                        value=f'`{str(h_dia).zfill(2)}h {str(m_dia).zfill(2)}m`',
                        inline=True
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
            await db.reset_all_times()
            await db.reset_all_registries()
            embed_ok = discord.Embed(
                title='\u2705 Semana Encerrada',
                description='Relatório publicado, backup enviado e base de dados resetada com sucesso!',
                color=discord.Colour.green()
            )
            await inter.followup.send(embed=embed_ok, ephemeral=True)
            canal_log = inter.guild.get_channel(config['log_channel_id'])
            embed_log = discord.Embed(
                description=f'**\u2192 `Staff`: {inter.user.mention}**\n**\u2192 Encerramento semanal efetuado. Base de dados resetada.**',
                colour=discord.Colour.red()
            )
            embed_log.set_author(name='LOG: Encerramento Semanal', icon_url=inter.user.display_avatar)
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