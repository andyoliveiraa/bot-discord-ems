import os
import signal
import sys
import subprocess
import time

if "--run-bot" not in sys.argv:
    # --- WATCHER ---
    WATCHER_LOCK = "watcher.lock"
    if os.path.exists(WATCHER_LOCK):
        try:
            with open(WATCHER_LOCK, "r") as f:
                old_pid = int(f.read().strip())
            try:
                os.kill(old_pid, 0)
                os.kill(old_pid, signal.SIGTERM)
            except OSError:
                pass
        except Exception:
            pass

    with open(WATCHER_LOCK, "w") as f:
        f.write(str(os.getpid()))

    while True:
        print("[SISTEMA] Iniciando processo do bot...")
        process = subprocess.Popen([sys.executable, sys.argv[0], "--run-bot"])
        try:
            process.wait()
        except KeyboardInterrupt:
            print("[SISTEMA] Interrompido pelo usuário.")
            process.terminate()
            break
        
        if process.returncode == 0:
            print("[SISTEMA] Bot encerrado.")
            break
        else:
            print(f"[SISTEMA] O bot foi encerrado de forma anormal (Erro {process.returncode}). Reiniciando em 5 segundos...")
            with open("crashed.txt", "w") as f:
                f.write("crash")
            time.sleep(5)
    sys.exit(0)

# --- BOT CODE ---
LOCK_FILE = "bot.lock"
if os.path.exists(LOCK_FILE):
    try:
        with open(LOCK_FILE, "r") as f:
            old_pid = int(f.read().strip())
        
        try:
            os.kill(old_pid, 0)
            os.kill(old_pid, signal.SIGTERM)
        except OSError:
            pass
    except Exception:
        pass

with open(LOCK_FILE, "w") as f:
    f.write(str(os.getpid()))

import asyncio
import aiohttp
from itertools import cycle
import json
import discord
import pytz
from discord.ext import commands
from discord.commands import Option
from discord.ui import InputText, Modal, Button, View
from datetime import datetime
from db import get_configs

client = commands.Bot(command_prefix=".", help_command=None, intents=discord.Intents().all())
client.load_extension('ponto')

config = get_configs()

async def att_status():
    status = cycle(["🛠️ Desenvolvido por andyydias", f"⚔ {config['server_name']}"])
    while True:
        new_status = next(status)
        await client.change_presence(activity=discord.Game(name=new_status))
        await asyncio.sleep(40)
        if new_status == f"⚔ {config['server_name']}":  # Quando estiver no último status ↓
            users = sum(guild.member_count for guild in client.guilds) if client.guilds else 0
            await client.change_presence(activity=discord.Game(name=f'👮️ Gerenciando {users} funcionários!'))
            await asyncio.sleep(50)

@client.event
async def on_ready():
    print('Bot está online!')
    
    if os.path.exists("crashed.txt"):
        try:
            dono_id = config.get("owner_id")
            if dono_id:
                dono = await client.fetch_user(dono_id)
                agora = datetime.now(pytz.timezone(config['timezone'])).strftime("%d/%m/%Y %H:%M:%S")
                await dono.send(f"⚠️ **AVISO DO SISTEMA** ⚠️\nO bot encontrou um erro crítico e foi **reiniciado automaticamente** em `{agora}`.")
            os.remove("crashed.txt")
        except Exception as e:
            print("Erro ao enviar aviso de reinício:", e)

    if not hasattr(client, 'status_task'):
        client.status_task = client.loop.create_task(att_status())
        
    if not hasattr(client, 'web_server_task'):
        from dashboard import app as web_app
        web_app.config['BOT_CLIENT'] = client
        port = int(os.environ.get("PORT", 8080))
        client.web_server_task = client.loop.create_task(web_app.run_task(host='0.0.0.0', port=port))
        print(f"Servidor Web (Dashboard) rodando na porta {port}")

@client.event
async def on_application_command(ctx: discord.ApplicationContext):
    agora = datetime.now(pytz.timezone(config['timezone'])).strftime("%d/%m/%Y %H:%M:%S")
    canal = f"#{ctx.channel.name}" if hasattr(ctx.channel, 'name') else "DM"
    print(f"[{agora}] 🔧 Comando executado: /{ctx.command.name} | Usuário: {ctx.author} | Sala: {canal} | Servidor: {ctx.guild.name if ctx.guild else 'DM'}")

@client.event
async def on_application_command_error(ctx: discord.ApplicationContext, error: discord.DiscordException):
    if isinstance(error, commands.NoPrivateMessage):
        return await ctx.respond('**<a:x_:1269034170395394118> ERRO!** Este comando não pode ser utilizado no privado.')

    if isinstance(error, commands.CommandOnCooldown):
        if error.retry_after >= 3600:
            tempo = f'{error.retry_after / 3600:.1f} horas'
        elif error.retry_after >= 60:
            tempo = f'{error.retry_after / 60:.1f} minutos'
        else:
            tempo = f'{round(error.retry_after)} segundos'
        return await ctx.respond(f'**<a:x_:1269034170395394118> ERRO!** Este comando está em cooldown! Tente novamente em `{tempo}`!', ephemeral=True)

    if isinstance(error, commands.MissingAnyRole):
        return await ctx.respond('**<a:x_:1269034170395394118> ERRO!** Você não tem permissão para executar este comando.\n'
                                 f'> Cargo Necessário: <@&{error.missing_roles[0]}>')

    if isinstance(error, commands.MissingPermissions):
        permissions = {
            "administrator": "Administrador",
            "manage_messages": "Gerenciar Mensagens"
        }
        return await ctx.respond('**<a:x_:1269034170395394118> ERRO!** Você não tem permissão para executar este comando.\n'
                                 f'> Permissão Necessária: `{" - ".join([permissions[perm] for perm in error.missing_permissions])}`')

    original = getattr(error, 'original', error)
    if isinstance(original, discord.NotFound) and original.code == 10062:
        return
    if isinstance(original, discord.HTTPException) and original.code == 40060:
        return

    canallog = client.get_channel(config['log_channel_id'])
    if ctx.command is None:
        comando = "Nenhum/Invalído"
    else:
        comando = ctx.command
    embedlog = discord.Embed(title='ERRO!', description=f'Comando utilizado: `{comando}`\nServidor: `{ctx.guild.name} / {ctx.guild.id}`\nCanal do comando: `{ctx.channel} / {ctx.channel.id}`\nAutor do comando: {ctx.author.mention} `/ {ctx.author.id}`\n\n**ERRO:**\n```py\n{error}\n```', color=discord.Colour.red())
    embedlog.set_footer(text='Developed by andyydias')
    if canallog:
        await canallog.send(embed=embedlog)
    else:
        print(f"[ERRO] Canal de logs (ID: {config['log_channel_id']}) não encontrado. Erro ao executar {comando}: {error}")

@client.slash_command(description='[ADM] Adiciona cargo a um usuário', contexts={discord.InteractionContextType.guild})
@commands.has_guild_permissions(administrator=True)
async def addrole(ctx: discord.ApplicationContext, cargo: Option(discord.Role, "Digite o cargo desejado", required=True),
                  user: Option(discord.Member, "Mencione um usuário", required=True)):
    await user.add_roles(cargo)
    await ctx.respond(f'Sucesso! Você atribuiu o cargo {cargo.mention} ao {user.mention}!')

@client.slash_command(description='Envia uma mensagem EMBED!', contexts={discord.InteractionContextType.guild})
@commands.has_guild_permissions(administrator=True)
async def embed(ctx: discord.ApplicationContext):
    embed = discord.Embed(title='Gerenciador de Embed', description='**Para enviar uma mensagem com o mesmo visual que esta (padrão embed), clique no botão abaixo, e preencha apenas os campos que você deseja.**', color=discord.Colour.red())
    embed.set_footer(text=f'{config["server_name"]} • 2026', icon_url=client.user.display_avatar)
    create_embed = Button(label='Criar Embed', style=discord.ButtonStyle.blurple, emoji='🛠')
    async def button_callback(inter: discord.Interaction):
        await inter.response.send_modal(embed_modal(ctx))

    view = View()
    view.add_item(create_embed)
    create_embed.callback = button_callback
    await ctx.respond(embed=embed, ephemeral=True, view=view)

class embed_modal(Modal):
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        super().__init__(title='Gerador de Embed', timeout=720)
        self.add_item(InputText(label='Título da Embed', style=discord.InputTextStyle.short, required=True, max_length=250))
        self.add_item(InputText(label='Descrição da Embed', style=discord.InputTextStyle.long, required=True, max_length=4000))
        self.add_item(InputText(label='Imagem (thumbnail)', placeholder='Links suportados: https:// e http://', style=discord.InputTextStyle.short, required=False))
        self.add_item(InputText(label='Imagem grande', placeholder='Links suportados: https:// e http://', style=discord.InputTextStyle.short, required=False))
        self.add_item(InputText(label='Cor da Embed', style=discord.InputTextStyle.short, required=True))

    async def callback(self, inter: discord.Interaction):
        embed = discord.Embed(title=self.children[0].value, description=self.children[1].value)
        try:
            color = getattr(discord.Colour, self.children[4].value.lower())
        except AttributeError:
            color = discord.Colour.random

        if self.children[2].value.startswith('http:') or self.children[2].value.startswith('https:'):
            embed.set_thumbnail(url=self.children[2].value)
        if self.children[3].value.startswith('http:') or self.children[3].value.startswith('https:'):
            embed.set_image(url=self.children[3].value)

        embed.color = color()
        embed.set_footer(text=f'{config["server_name"]} • 2026', icon_url=client.user.display_avatar)
        await inter.channel.send(embed=embed)
        await inter.response.send_message(f'<a:check:1269034091882221710> Embed criada com sucesso em {inter.channel.mention}!', ephemeral=True)

@client.slash_command(description='Limpa mensagens do canal', contexts={discord.InteractionContextType.guild})
@commands.has_guild_permissions(manage_messages=True)
async def clear(ctx: discord.ApplicationContext,
                quantidade: Option(int, 'Insira a quantidade de mensagens a serem deletadas', required=True)):
    msgs = len(
        await ctx.channel.purge(limit=quantidade, bulk=True)
    )
    await ctx.respond(f'<a:check:1269034091882221710> Foram deletadas {msgs} mensagens!', delete_after=8.0)

@client.slash_command(description='Mostra a latência e o status do bot', contexts={discord.InteractionContextType.guild})
async def ping(ctx: discord.ApplicationContext):
    latency = round(client.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"**Status:** Online 🟢\n**Latência:** `{latency}ms`",
        color=discord.Colour.green()
    )
    embed.set_footer(text=f'{config["server_name"]} • 2026', icon_url=client.user.display_avatar)
    await ctx.respond(embed=embed)




client.run(config['token'])