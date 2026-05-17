from quart import Quart, render_template, request, session, redirect, url_for, flash, jsonify
import os
import asyncio
import aiohttp
import secrets
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash
from db import Database, get_configs, save_configs
import datetime
from pytz import timezone as tz

load_dotenv() # Carrega .env

app = Quart(__name__)
# Configuração inicial ( fallback para config.json )
config = get_configs()
app.secret_key = config.get('secret_key', 'chave_secreta_padrao_muito_segura_123!')
db = Database('db.sqlite3')

@app.before_serving
async def startup():
    await db.setup_db()
    # Migra se for o primeiro arranque com a nova versão
    await db.migrate_from_json()
    # Recarrega config da BD
    await recarregar_config()
    await db.get_or_criar_semana_activa()

@app.route('/api/track-visit', methods=['POST'])
async def api_track_visit():
    if session.get('visitor_notified'):
        return jsonify({'ok': True})

    # Detecção de IP Real (Suporte para Cloudflare e Proxies)
    final_ip = request.headers.get('CF-Connecting-IP') or \
               request.headers.get('X-Real-IP') or \
               request.headers.get('X-Forwarded-For', request.remote_addr)
    
    if final_ip and ',' in final_ip:
        final_ip = final_ip.split(',')[0].strip()

    user_agent = request.headers.get('User-Agent', 'Desconhecido')
    device = "Desktop / Computador"
    if any(m in user_agent.lower() for m in ['mobile', 'android', 'iphone', 'ipad']):
        device = "Telemóvel / Tablet"

    # Lookup de Localização
    location_data = {}
    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(f"http://ip-api.com/json/{final_ip}?fields=status,message,country,city,isp,org,as,query") as resp:
                if resp.status == 200:
                    location_data = await resp.json()
    except Exception as e:
        print(f"[DEBUG] Erro ao consultar localização: {e}")

    bot = app.config.get('BOT_CLIENT')
    owner_id = config.get('owner_id')

    user_id = session.get('user_id')
    user_info = "Visitante"
    if user_id:
        func = await db.get_funcionario(user_id)
        if func:
            user_info = f"{func[1]} ({func[2]})" # Ex: D-02 (Andy Oliveira)

    if bot and owner_id:
        try:
            owner = bot.get_user(int(owner_id)) or await bot.fetch_user(int(owner_id))
            if owner:
                city = location_data.get('city', 'Desconhecida')
                country = location_data.get('country', 'Desconhecido')
                isp = location_data.get('isp', 'Desconhecido')
                
                msg = (
                    f"🌐 **Novo acesso ao Dashboard!** ({user_info})\n"
                    f"📍 **IP:** `{final_ip}`\n"
                    f"🗺️ **Localização:** `{city}, {country}`\n"
                    f"📡 **ISP:** `{isp}`\n"
                    f"💻 **Dispositivo:** `{device}`\n"
                    f"📝 **User-Agent:** `{user_agent[:80]}...`"
                )
                await owner.send(msg)
                session['visitor_notified'] = True
                
                # Gravar log na base de dados
                await db.add_log(
                    categoria='dashboard',
                    user_id=user_id or 0,
                    mensagem=f"Acesso ao Dashboard: {user_info}",
                    detalhes={
                        'ip': final_ip,
                        'localizacao': f"{city}, {country}",
                        'isp': isp,
                        'dispositivo': device,
                        'user_agent': user_agent
                    },
                    cor='primary'
                )
                print(f"[SEGURANÇA] Log de acesso gravado e notificação enviada.")
        except Exception as e:
            print(f"[SEGURANÇA] Erro ao enviar notificação: {e}")
    
    return jsonify({'ok': True})

def formatar_moeda(valor):
    return f"{valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') + " €"

async def recarregar_config():
    global config
    # Carrega da BD
    db_configs = await db.get_all_configs()
    if db_configs:
        config.update(db_configs)
        print("[DASHBOARD] Configurações recarregadas da BD.")
    else:
        # Fallback para config.json se a BD estiver vazia
        config = get_configs()
    
    app.secret_key = config.get('secret_key', 'chave_secreta_padrao_muito_segura_123!')
    
    # Sincroniza config com o módulo ponto
    try:
        import ponto
        ponto.config = config
    except ImportError:
        pass
    
    # Sincroniza config com o objeto bot
    bot = app.config.get('BOT_CLIENT')
    if bot:
        # Se o bot tem o atributo config (definido no main.py), atualiza-o
        if hasattr(bot, 'config'):
            bot.config.update(config)
        else:
            bot.config = config

@app.template_filter('timestamp_fmt')
def timestamp_fmt(ts):
    try:
        return datetime.datetime.fromtimestamp(int(ts), tz(config.get('timezone', 'UTC'))).strftime('%H:%M')
    except Exception:
        return '--:--'

@app.template_filter('timestamp_semana')
def timestamp_semana(ts):
    try:
        return datetime.datetime.fromtimestamp(int(ts), tz(config.get('timezone', 'UTC'))).strftime('%d/%m/%Y')
    except Exception:
        return '??/??/????'

@app.template_filter('get_avatar')
def get_avatar_filter(user_id):
    bot = app.config.get('BOT_CLIENT')
    if bot:
        try:
            user = bot.get_user(int(user_id))
            if user:
                return user.display_avatar.url
        except Exception:
            pass
    # Fallback para o avatar padrão do Discord
    return f"https://cdn.discordapp.com/embed/avatars/{int(user_id) % 5}.png"


# ── helpers ──────────────────────────────────────────────────────────────────

def login_required(fn):
    import functools
    @functools.wraps(fn)
    async def wrapper(*a, **kw):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return await fn(*a, **kw)
    return wrapper

def direcao_required(fn):
    import functools
    @functools.wraps(fn)
    async def wrapper(*a, **kw):
        if not session.get('is_direcao'):
            return jsonify({'erro': 'Acesso restrito à Direção'}), 403
        return await fn(*a, **kw)
    return wrapper

def owner_required(fn):
    import functools
    @functools.wraps(fn)
    async def wrapper(*a, **kw):
        user_id = session.get('user_id')
        if not user_id or str(user_id) != str(config.get('owner_id')):
            await flash('Acesso restrito ao Proprietário.', 'danger')
            return redirect(url_for('index'))
        return await fn(*a, **kw)
    return wrapper

# ── index ─────────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
async def index():
    user_id = session['user_id']
    func = await db.get_funcionario(user_id)
    if not func:
        session.clear()
        return redirect(url_for('login'))

    tempo_semanal = await db.get_user_time(user_id)
    tempo_total = tempo_semanal[1] if tempo_semanal else 0
    horas = int(tempo_total // 3600)
    minutos = int((tempo_total % 3600) // 60)

    patente_nome = func[0]
    patente_info = config.get('cargos_patentes', {}).get(func[0])
    valor_hora = 0
    if patente_info:
        patente_nome = patente_info.get('nome', func[0])
        valor_hora = patente_info.get('valor_hora', 0)

    mins_pagar = horas * 60 + minutos
    pagamento_estimado = (mins_pagar / 60) * valor_hora

    ranking = await db.get_ranking(10)
    ranking_fmt = []
    for rank in ranking:
        r_user = await db.get_funcionario(rank[0])
        nome = r_user[2] if r_user else f"ID: {rank[0]}"
        callsign = r_user[1] if r_user else ''
        rh = int(rank[1] // 3600)
        rm = int((rank[1] % 3600) // 60)
        ranking_fmt.append({
            'user_id': rank[0],
            'nome': nome, 
            'callsign': callsign, 
            'tempo': f"{rh}h {rm}m"
        })

    historico = await db.get_pagamentos_user(user_id)

    is_admin = session.get('is_admin', False)
    is_direcao = session.get('is_direcao', False)
    return await render_template('index.html',
        func=func, horas=horas, minutos=minutos,
        is_admin=is_admin, is_direcao=is_direcao,
        ranking=ranking_fmt, 
        patente_nome=patente_nome,
        pagamento_estimado=formatar_moeda(pagamento_estimado),
        historico=historico)

# ── login / logout ────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
async def login():
    if request.method == 'POST':
        form = await request.form
        callsign = form.get('callsign')
        password = form.get('password')
        func = await db.get_funcionario_by_callsign(callsign)
        if func and func[4]:
            if await asyncio.to_thread(check_password_hash, func[4], password):
                session['user_id'] = func[0]
                is_admin = False
                bot = app.config.get('BOT_CLIENT')
                if bot:
                    for guild in bot.guilds:
                        member = guild.get_member(func[0])
                        if member and any(str(r.id) == str(config.get('staff_role_id')) for r in member.roles):
                            is_admin = True
                            break
                session['is_admin'] = is_admin
                
                # Check for Direção (Owner, specific patente in DB, or specific roles in Discord)
                is_direcao = (func[0] == config.get('owner_id'))
                direcao_patentes = ['sub_diretor', 'diretor_adjunto', 'diretor']
                if not is_direcao and func[1] in direcao_patentes:
                    is_direcao = True
                
                print(f"[DEBUG] Login {func[2]} (ID: {func[0]}): is_admin={is_admin}, DB Patente={func[1]}")
                
                if not is_direcao and bot:
                    direcao_roles = []
                    for p_key in ['sub_diretor', 'diretor_adjunto', 'diretor']:
                        p_info = config.get('cargos_patentes', {}).get(p_key)
                        if p_info and 'id' in p_info:
                            direcao_roles.append(int(p_info['id']))
                    print(f"[DEBUG] Checking Direção roles: {direcao_roles}")
                    for guild in bot.guilds:
                        member = guild.get_member(func[0])
                        if not member:
                            try: member = await guild.fetch_member(func[0])
                            except Exception as e: 
                                print(f"[DEBUG] Fetch member error in guild {guild.id}: {e}")
                                continue
                        
                        if member:
                            member_role_ids = [r.id for r in member.roles]
                            print(f"[DEBUG] Member roles in {guild.name}: {member_role_ids}")
                            if any(rid in direcao_roles for rid in member_role_ids):
                                is_direcao = True
                                break
                
                print(f"[DEBUG] Final is_direcao result: {is_direcao}")
                session['is_direcao'] = is_direcao
                return redirect(url_for('index'))
            else:
                await flash('Senha incorreta.', 'danger')
        else:
            await flash('Utilizador não encontrado ou não configurado.', 'danger')
    return await render_template('login.html')

@app.route('/logout')
async def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
async def reset_password(token):
    func = await db.get_funcionario_by_reset_token(token)
    if not func:
        return 'Token inválido ou expirado.', 400
    if request.method == 'POST':
        form = await request.form
        new_password = form.get('password')
        senha_hash = await asyncio.to_thread(generate_password_hash, new_password)
        await db.update_password(func[0], senha_hash)
        await db.set_reset_token(func[0], secrets.token_urlsafe(32))
        await flash('Senha alterada com sucesso! Já pode fazer login.', 'success')
        return redirect(url_for('login'))
    return await render_template('reset_password.html', func=func, token=token)

# ── meus pontos ───────────────────────────────────────────────────────────────

@app.route('/meus-pontos')
@login_required
async def meus_pontos():
    user_id = session['user_id']
    func = await db.get_funcionario(user_id)
    is_admin = session.get('is_admin', False)
    is_direcao = session.get('is_direcao', False)

    # Staff pode ver pontos de outro utilizador via ?uid=
    target_id = user_id
    target_func = func
    func_list = []
    if is_admin or is_direcao:
        func_list = await db.get_all_funcionarios()
        func_list.sort(key=lambda x: (x[3] or '').lower()) # Sort by name, None-safe
        uid_param = request.args.get('uid')
        if uid_param:
            try:
                target_id = int(uid_param)
                target_func = await db.get_funcionario(target_id)
            except Exception:
                pass

    tz_cfg = config.get('timezone', 'UTC')
    registros = await db.get_all_user_registries_with_id(target_id)

    por_dia = {}
    for reg in registros:
        rid, started, finished, staff_finished, duration, pauses = reg
        data_str = datetime.datetime.fromtimestamp(started, tz(tz_cfg)).strftime('%d/%m/%Y')
        if data_str not in por_dia:
            por_dia[data_str] = {'registros': [], 'total_seg': 0}
        por_dia[data_str]['total_seg'] += duration if duration else 0


        import json
        try:
            pausas = json.loads(pauses) if pauses else []
        except Exception:
            pausas = []

        hr_in = datetime.datetime.fromtimestamp(started, tz(tz_cfg)).strftime('%H:%M')
        hr_out = datetime.datetime.fromtimestamp(finished, tz(tz_cfg)).strftime('%H:%M') if finished else '--:--'
        h_dur = int((duration or 0) // 3600)
        m_dur = int(((duration or 0) % 3600) // 60)

        por_dia[data_str]['registros'].append({
            'id': rid,
            'hr_in': hr_in,
            'hr_out': hr_out,
            'duration_h': h_dur,
            'duration_m': m_dur,
            'duration_seg': duration or 0,
            'staff_finished': staff_finished,
            'cancelado': (duration == 0 and staff_finished and staff_finished > 10000),
            'pausas': pausas,
        })

    dias_formatados = []
    for dia, dados in sorted(por_dia.items(), key=lambda x: tuple(x[0].split('/')[::-1])):
        th = int(dados['total_seg'] // 3600)
        tm = int((dados['total_seg'] % 3600) // 60)
        dias_formatados.append({'dia': dia, 'total_h': th, 'total_m': tm, 'registros': dados['registros']})

    from db import get_configs
    config_atual = get_configs()
    patente_info = config_atual.get('cargos_patentes', {}).get(func[0] if func else '', {})
    valor_hora = patente_info.get('valor_hora', 0) if patente_info else 0

    return await render_template('meus_pontos.html',
        func=func, target_func=target_func, target_id=target_id,
        dias=dias_formatados, is_admin=is_admin, is_direcao=is_direcao,
        valor_hora=valor_hora, func_list=func_list)

# ── API: editar ponto ─────────────────────────────────────────────────────────

@app.route('/api/ponto/<int:ponto_id>/editar', methods=['POST'])
async def api_editar_ponto(ponto_id):
    if not session.get('is_direcao'):
        return jsonify({'erro': 'Ação permitida apenas para a Direção'}), 403

    ponto = await db.get_ponto_by_id(ponto_id)
    if not ponto or ponto[7] is not None:
        return jsonify({'erro': 'Ponto não encontrado ou já arquivado'}), 404

    form = await request.form
    action = form.get('action')
    user_id = ponto[1]
    duration_actual = ponto[5] or 0

    if action == 'add_time':
        h = int(form.get('horas', 0))
        m = int(form.get('minutos', 0))
        delta = h * 3600 + m * 60
        new_dur = duration_actual + delta
        await db.update_ponto_duration(ponto_id, new_dur)
        await db.add_time(user_id, delta)
        await db.add_log('dashboard', session['user_id'], f"Adicionou {h}h {m}m ao ponto #{ponto_id}", {'user_ponto': user_id}, cor='info')
        return jsonify({'ok': True, 'nova_duration': new_dur})

    elif action == 'remove_time':
        h = int(form.get('horas', 0))
        m = int(form.get('minutos', 0))
        delta = h * 3600 + m * 60
        new_dur = max(0, duration_actual - delta)
        removed = duration_actual - new_dur
        await db.update_ponto_duration(ponto_id, new_dur)
        await db.del_time(user_id, removed)
        await db.add_log('dashboard', session['user_id'], f"Removeu {h}h {m}m do ponto #{ponto_id}", {'user_ponto': user_id}, cor='warning')
        return jsonify({'ok': True, 'nova_duration': new_dur})

    elif action == 'cancel':
        staff_id = session['user_id']
        await db.del_time(user_id, duration_actual)
        await db.cancel_ponto(ponto_id, staff_id)
        await db.add_log('dashboard', staff_id, f"Cancelou o ponto #{ponto_id}", {'user_ponto': user_id}, cor='danger')
        return jsonify({'ok': True})

    elif action == 'edit_times':
        try:
            # Recebe strings no formato HH:MM
            str_in = form.get('hr_in')
            str_out = form.get('hr_out')
            
            # Precisamos manter a data original do ponto no fuso horário configurado
            tz_obj = tz(config.get('timezone', 'UTC'))
            base_date = datetime.datetime.fromtimestamp(ponto[2], tz_obj).date()
            
            t_in = datetime.datetime.strptime(str_in, '%H:%M').time()
            t_out = datetime.datetime.strptime(str_out, '%H:%M').time()
            
            # Criar novos datetimes localizados
            dt_in = tz_obj.localize(datetime.datetime.combine(base_date, t_in))
            dt_out = tz_obj.localize(datetime.datetime.combine(base_date, t_out))
            
            new_in = int(dt_in.timestamp())
            new_out = int(dt_out.timestamp())
            
            # Se a saída for antes da entrada, assume que virou o dia (adiciona 24h)
            if new_out < new_in:
                new_out += 86400
                
            new_duration = new_out - new_in
            
            # Diferença para atualizar o total do usuário
            diff = new_duration - duration_actual
            
            await db.update_ponto_times(ponto_id, new_in, new_out, new_duration)
            if diff > 0:
                await db.add_time(user_id, diff)
            elif diff < 0:
                await db.del_time(user_id, abs(diff))
            
            await db.add_log('dashboard', session['user_id'], f"Alterou horários do ponto #{ponto_id}", {'hr_in': str_in, 'hr_out': str_out}, cor='info')
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'erro': f'Erro ao processar horários: {str(e)}'}), 400

    return jsonify({'erro': 'Acção inválida'}), 400

@app.route('/api/active-ponto/version')
async def api_active_ponto_version():
    if not session.get('is_admin'):
        return jsonify({'erro': 'Não autorizado'}), 403
    import ponto
    return jsonify({'version': ponto.active_pontos_version})

@app.route('/admin/pontos-abertos')
async def admin_pontos_abertos():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    
    from ponto import active_pontos
    client = app.config.get('BOT_CLIENT')
    
    open_points = []
    for user_id, estado in active_pontos.items():
        # Obter informações do usuário
        func = await db.get_funcionario(user_id)
        nome = f"ID: {user_id}"
        callsign = ""
        if func:
            callsign = func[1]
            nome = func[2]
        
        avatar = ""
        if client:
            try:
                user = client.get_user(user_id) or await client.fetch_user(user_id)
                avatar = user.display_avatar.url if user else ""
            except:
                pass
        
        open_points.append({
            'user_id': user_id,
            'nome': nome,
            'callsign': callsign,
            'avatar': avatar,
            'inicio': estado['inicio'],
            'status': estado['status'],
            'pausado': estado['status'] == 'pausado',
            'inicio_pausa': estado.get('inicio_pausa', 0),
            'total_pausa': estado.get('total_pausa', 0)
        })
        
    return await render_template('pontos_abertos.html', pontos=open_points, is_admin=True)

@app.route('/api/active-ponto/<int:target_user_id>/<action>', methods=['POST'])
async def api_active_ponto_action(target_user_id, action):
    if not session.get('is_admin'):
        return jsonify({'erro': 'Não autorizado'}), 403
        
    from ponto import active_pontos, save_active_pontos
    if target_user_id not in active_pontos:
        return jsonify({'erro': 'Ponto não encontrado ou já encerrado'}), 404
        
    estado = active_pontos[target_user_id]
    client = app.config.get('BOT_CLIENT')
    form = await request.form
    staff_id = session['user_id']
    
    try:
        if action == 'close':
            contabiliza = form.get('contabiliza') == 'true'
            horario_atual = int(datetime.datetime.now(tz(config.get('timezone', 'UTC'))).timestamp())
            
            if estado["status"] == "pausado":
                duracao_pausa = horario_atual - estado["inicio_pausa"]
                estado["total_pausa"] += duracao_pausa
                estado["pausas"].append([estado["inicio_pausa"], horario_atual])
                
            horario_inicio = estado["inicio"]
            segundos_totais = horario_atual - horario_inicio - estado["total_pausa"]
            if segundos_totais < 0: segundos_totais = 0
            
            active_pontos.pop(target_user_id)
            save_active_pontos()
            
            if contabiliza:
                await db.add_time(target_user_id, segundos_totais)
            
            import json
            pauses_json = json.dumps(estado["pausas"])
            await db.create_registry(target_user_id, horario_inicio, horario_atual, staff_id, segundos_totais if contabiliza else 0, pauses_json)
            
            # Tentar enviar LOG no Discord
            if client:
                try:
                    canal_log = client.get_channel(config["log_channel_id"])
                    if canal_log:
                        import discord
                        data_abertura = datetime.datetime.fromtimestamp(horario_inicio, tz(config.get('timezone', 'UTC'))).strftime("%d/%m/%Y, %H:%M:%S")
                        
                        log_desc = f'**→ `Status Pica-Ponto`: Fechado pelo Painel (Staff)** *({"contabilizado" if contabiliza else "não contabilizado"})*\n'
                        log_desc += f'**→ `Funcionário`: <@{target_user_id}>**\n'
                        log_desc += f'**→ `Horário de Abertura`: {data_abertura}**\n'
                        log_desc += f'**→ `Horário de Fechamento`: {datetime.datetime.fromtimestamp(horario_atual, tz(config.get("timezone", "UTC"))).strftime("%d/%m/%Y, %H:%M:%S")}**'
                        
                        embed_log = discord.Embed(description=log_desc, colour=discord.Colour.green() if contabiliza else discord.Colour.orange())
                        embed_log.set_author(name='LOG: Pica-Ponto fechado pelo Painel Web', icon_url=client.user.display_avatar)
                        await canal_log.send(embed=embed_log)
                        
                        # Tentar avisar usuário
                        user = client.get_user(target_user_id) or await client.fetch_user(target_user_id)
                        if user:
                            h, m = int(segundos_totais // 3600), int((segundos_totais % 3600) // 60)
                            await user.send(f'**<:aviso:1269036173381206132> AVISO:** Seu pica-ponto foi finalizado através do Painel Web!\n> <:relogio:1269034530388574309> Tempo: **`{h}h {m}m`**\n**Estado:** {"Contabilizado" if contabiliza else "Não Contabilizado"}')
                except:
                    pass
            
            return jsonify({'ok': True})
            
        elif action == 'cancel':
            horario_atual = int(datetime.datetime.now(tz(config.get('timezone', 'UTC'))).timestamp())
            horario_inicio = estado["inicio"]
            
            active_pontos.pop(target_user_id)
            save_active_pontos()
            
            import json
            await db.create_registry(target_user_id, horario_inicio, horario_atual, staff_id, 0, json.dumps(estado["pausas"]))
            
            if client:
                try:
                    canal_log = client.get_channel(config["log_channel_id"])
                    if canal_log:
                        import discord
                        embed_log = discord.Embed(
                            description=f'**→ `Status`: Cancelado pelo Painel**\n**→ `Funcionário`: <@{target_user_id}>**\n**→ `Staff`: <@{staff_id}>**',
                            colour=discord.Colour.red()
                        )
                        await canal_log.send(embed=embed_log)
                except: pass
                
            return jsonify({'ok': True})
            
        elif action == 'edit':
            new_time_str = form.get('new_time') # Formato HH:MM
            if not new_time_str:
                return jsonify({'erro': 'Horário inválido'}), 400
                
            tz_obj = tz(config.get('timezone', 'UTC'))
            base_date = datetime.datetime.fromtimestamp(estado['inicio'], tz_obj).date()
            t_new = datetime.datetime.strptime(new_time_str, '%H:%M').time()
            dt_new = tz_obj.localize(datetime.datetime.combine(base_date, t_new))
            
            estado['inicio'] = int(dt_new.timestamp())
            save_active_pontos()
            return jsonify({'ok': True})
            
    except Exception as e:
        return jsonify({'erro': str(e)}), 500
    
    return jsonify({'erro': 'Acção inválida'}), 400

# ── Planilha Pública ─────────────────────────────────────────────────────────

@app.route('/planilha')
async def planilha_publica():
    funcionarios = await db.get_all_funcionarios()
    from db import get_configs
    config_atual = get_configs()
    cargos = config_atual.get('cargos_patentes', {})
    
    impagos_raw = await db.get_semanas_com_impagos()
    impagos_por_user = {}
    for imp in impagos_raw:
        uid = imp[1]
        valor = imp[2]
        impagos_por_user[uid] = impagos_por_user.get(uid, 0) + valor

    planilha_list = []
    for f in funcionarios:
        uid, pat_id, callsign, nome = f
        
        tempo = await db.get_user_time(uid)
        tempo_seg = tempo[1] if tempo else 0
        h = int(tempo_seg // 3600)
        m = int((tempo_seg % 3600) // 60)
        
        patente_info = cargos.get(pat_id, {})
        valor_hora = patente_info.get('valor_hora', 0)
        
        mins = h * 60 + m
        estimativa = (mins / 60) * valor_hora
        pendente = impagos_por_user.get(uid, 0)
        
        # Filtra se quisermos (neste caso, mostramos todos)
        planilha_list.append({
            'user_id': uid,
            'callsign': callsign,
            'nome': nome,
            'patente_nome': patente_info.get('nome', pat_id),
            'patente_id': pat_id,
            'horas': h,
            'minutos': m,
            'estimativa': estimativa,
            'pendente': pendente
        })
    
    # Sort by cargo valor (maior para menor) then by callsign
    planilha_list.sort(key=lambda x: (
        -cargos.get(x['patente_id'], {}).get('valor_hora', 0),
        x['callsign']
    ))
    
    return await render_template('planilha.html', planilha=planilha_list, config=config, formatar_moeda=formatar_moeda)

# ── admin ─────────────────────────────────────────────────────────────────────

@app.route('/admin')
async def admin():
    if not session.get('is_admin'):
        return 'Acesso Negado.', 403
    return await render_template('admin.html')

@app.route('/admin/definicoes')
async def admin_definicoes():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    from db import get_configs
    config_atual = get_configs()
    funcionarios = await db.get_all_funcionarios()
    semanas = await db.get_todas_semanas()
    cargos = config_atual.get('cargos_patentes', {})

    func_list = []
    for f in funcionarios:
        uid, pat_id, callsign, nome = f
        tempo = await db.get_user_time(uid)
        tempo_seg = tempo[1] if tempo else 0
        h = int(tempo_seg // 3600)
        m = int((tempo_seg % 3600) // 60)
        patente_info = cargos.get(pat_id, {})
        valor_hora = patente_info.get('valor_hora', 0)
        mins = h * 60 + m
        pagamento = (mins / 60) * valor_hora
        func_list.append({
            'user_id': uid, 'patente_id': pat_id,
            'patente_nome': patente_info.get('nome', pat_id),
            'callsign': callsign, 'nome': nome,
            'horas': h, 'minutos': m,
            'pagamento': formatar_moeda(pagamento)
        })

    semanas_info = []
    for s in semanas:
        sid, inicio, fim, encerrada = s
        tz_cfg = config.get('timezone', 'UTC')
        inicio_str = datetime.datetime.fromtimestamp(inicio, tz(tz_cfg)).strftime('%d/%m/%Y')
        fim_str = datetime.datetime.fromtimestamp(fim, tz(tz_cfg)).strftime('%d/%m/%Y') if fim else 'Activa'
        pagamentos = await db.get_pagamentos_semana(sid)
        
        pagamentos_enrich = []
        for p in pagamentos:
            uid_p = p[2]
            p_callsign = ""
            p_nome = ""
            for f_db in funcionarios:
                if f_db[0] == uid_p:
                    p_callsign = f_db[2]
                    p_nome = f_db[3]
                    break
            if not p_nome:
                p_nome = f"ID: {uid_p}"
            pagamentos_enrich.append({
                'id': p[0],
                'semana_id': p[1],
                'user_id': p[2],
                'valor': p[3],
                'pago': p[4],
                'pago_em': p[5],
                'pago_por': p[6],
                'callsign': p_callsign,
                'nome': p_nome
            })

        total_pago = sum(1 for p in pagamentos_enrich if p['pago'] == 1)
        total = len(pagamentos_enrich)
        semanas_info.append({
            'id': sid, 'inicio': inicio_str, 'fim': fim_str,
            'encerrada': encerrada, 'pagamentos': pagamentos_enrich,
            'total_pago': total_pago, 'total': total,
        })

    return await render_template('admin_definicoes.html', 
        func_list=func_list, 
        semanas=semanas_info, 
        cargos=cargos,
        config=config,
        is_admin=session.get('is_admin'),
        is_direcao=session.get('is_direcao'),
        ordenado_cargos=sorted(cargos.items(), key=lambda x: x[1].get('valor_hora', 0), reverse=True))

@app.route('/api/semana/<int:semana_id>/gerar-pdf', methods=['POST'])
@login_required
async def api_gerar_pdf_semana(semana_id):
    if not session.get('is_admin') and not session.get('is_direcao'):
        return jsonify({"success": False, "message": "Sem permissão."}), 403
    try:
        from pdf_helper import gerar_pdf_detalhado
        import discord
        semanas = await db.get_todas_semanas()
        semana_info = next((s for s in semanas if s[0] == semana_id), None)
        if not semana_info:
            return jsonify({"success": False, "message": "Semana não encontrada."}), 404
            
        inicio = semana_info[1]
        fim = semana_info[2]
        
        from db import get_configs
        config_atual = get_configs()
        
        pdf_path = await gerar_pdf_detalhado(db, config, semana_id, inicio, fim)
        if not pdf_path:
            return jsonify({"success": False, "message": "Erro ao gerar PDF ou sem pagamentos associados."}), 200
            
        bot_client = app.config.get('BOT_CLIENT')
        if bot_client:
            log_channel_id = config_atual.get('log_channel_id')
            if log_channel_id:
                channel = bot_client.get_channel(int(log_channel_id))
                if channel:
                    await channel.send(
                        content=f'📄 **Relatório Analítico Detalhado (Painel Web)**\nSemana ID: `{semana_id}`\nPor: <@{session.get("user_id")}>',
                        file=discord.File(pdf_path)
                    )
                    
        return jsonify({"success": True})
    except Exception as e:
        print(f"Erro ao gerar pdf: {e}")
        return jsonify({"success": False, "message": str(e)}), 200


@app.route('/api/admin/funcionario/<int:uid>/action', methods=['POST'])
@direcao_required
async def api_admin_func_action(uid):
    
    form = await request.form
    action = form.get('action') # promote, demote, fire
    
    bot = app.config.get('BOT_CLIENT')
    guild = None
    member = None
    if bot:
        guild_id = config.get('guild_id')
        if guild_id:
            guild = bot.get_guild(int(guild_id))
        if not guild and bot.guilds:
            guild = bot.guilds[0]
            
        if guild:
            member = guild.get_member(uid)
            if not member:
                try: member = await guild.fetch_member(uid)
                except: pass

    if action == 'fire':
        await db.remove_funcionario(uid)
        if member:
            # Tenta remover todos os cargos de patente
            cargos_patentes = config.get('cargos_patentes', {})
            for p_info in cargos_patentes.values():
                role_id = p_info.get('id')
                if role_id:
                    role = guild.get_role(role_id)
                    if role and role in member.roles:
                        try: await member.remove_roles(role)
                        except: pass
        await db.add_log('dashboard', session['user_id'], f"Despediu funcionário <@{uid}>", cor='danger')
        return jsonify({'ok': True})

    elif action in ['promote', 'demote']:
        new_patente = form.get('patente_id')
        cargos_patentes = config.get('cargos_patentes', {})
        if not new_patente or new_patente not in cargos_patentes:
            return jsonify({'erro': 'Patente inválida'}), 400
        
        # Obter dados do funcionário atual
        func = await db.get_funcionario(uid)
        if not func: return jsonify({'erro': 'Funcionário não encontrado'}), 404
        
        # Atualizar no DB
        await db.add_funcionario(uid, new_patente, func[1], func[2])
        
        if member:
            # Trocar cargos no Discord
            cargos_patentes = config.get('cargos_patentes', {})
            old_role_id = cargos_patentes.get(func[0], {}).get('id')
            new_role_id = cargos_patentes.get(new_patente, {}).get('id')
            
            old_role = guild.get_role(old_role_id) if old_role_id else None
            new_role = guild.get_role(new_role_id) if new_role_id else None
            
            if old_role and old_role in member.roles:
                try: await member.remove_roles(old_role)
                except: pass
            
            if new_role:
                try: await member.add_roles(new_role)
                except: pass
                
        await db.add_log('dashboard', session['user_id'], f"Alterou patente de <@{uid}> para {new_patente}", {'acao': action}, cor='info')
        return jsonify({'ok': True})

    return jsonify({'erro': 'Acção desconhecida'}), 400

# ── API: admin acções ─────────────────────────────────────────────────────────

@app.route('/api/funcionario/<int:uid>/resetar-senha', methods=['POST'])
async def api_resetar_senha(uid):
    if not session.get('is_admin'):
        return jsonify({'erro': 'Sem permissão'}), 403
    func = await db.get_funcionario(uid)
    if not func:
        return jsonify({'erro': 'Funcionário não encontrado'}), 404
    token = secrets.token_urlsafe(32)
    await db.set_reset_token(uid, token)
    link = f"https://ems.discloud.app/reset_password/{token}"
    bot = app.config.get('BOT_CLIENT')
    enviado = False
    if bot:
        try:
            user = bot.get_user(uid) or await bot.fetch_user(uid)
            if user:
                await user.send(f'🔒 A sua senha foi resetada por um administrador.\nDefina uma nova senha em: {link}')
                enviado = True
        except Exception:
            pass
    await db.add_log('dashboard', session['user_id'], f"Resetou senha de <@{uid}>", cor='warning')
    return jsonify({'ok': True, 'link': link, 'dm_enviada': enviado})

@app.route('/api/funcionario/<int:uid>/promover', methods=['POST'])
async def api_promover(uid):
    if not session.get('is_admin'):
        return jsonify({'erro': 'Sem permissão'}), 403
    form = await request.form
    nova_patente = form.get('patente')
    if not nova_patente or nova_patente not in config.get('cargos_patentes', {}):
        return jsonify({'erro': 'Patente inválida'}), 400

    bot = app.config.get('BOT_CLIENT')
    if not bot:
        return jsonify({'erro': 'Bot não disponível'}), 503

    func = await db.get_funcionario(uid)
    if not func:
        return jsonify({'erro': 'Funcionário não encontrado'}), 404

    cargos_patentes = config.get('cargos_patentes', {})
    nova_patente_info = cargos_patentes.get(nova_patente)
    if not nova_patente_info:
        return jsonify({'erro': 'Configuração da patente não encontrada'}), 400
    patente_antiga_info = cargos_patentes.get(func[0], {})
    nome_func = func[2]

    for guild in bot.guilds:
        member = guild.get_member(uid)
        if member:
            try:
                if patente_antiga_info.get('id'):
                    cargo_old = guild.get_role(patente_antiga_info['id'])
                    if cargo_old:
                        await member.remove_roles(cargo_old)
                cargo_new = guild.get_role(nova_patente_info['id'])
                if cargo_new:
                    await member.add_roles(cargo_new)
            except Exception:
                pass
            break

    novo_callsign = await db.get_next_callsign(nova_patente_info['letra'])
    velha_letra = func[1].split('-')[0] if func[1] and '-' in func[1] else ''
    velho_num = int(func[1].split('-')[1]) if func[1] and '-' in func[1] else 0

    await db.add_funcionario(uid, nova_patente, novo_callsign, nome_func)
    if velha_letra:
        await db.shift_callsigns_down(velha_letra, velho_num)

    return jsonify({'ok': True, 'novo_callsign': novo_callsign})

@app.route('/api/funcionario/<int:uid>/despedir', methods=['POST'])
async def api_despedir(uid):
    if not session.get('is_admin'):
        return jsonify({'erro': 'Sem permissão'}), 403
    form = await request.form
    motivo = form.get('motivo', 'Sem motivo indicado')

    func = await db.get_funcionario(uid)
    if not func:
        return jsonify({'erro': 'Funcionário não encontrado'}), 404

    bot = app.config.get('BOT_CLIENT')
    if bot:
        patente_info = config.get('cargos_patentes', {}).get(func[0], {})
        for guild in bot.guilds:
            member = guild.get_member(uid)
            if member:
                try:
                    cargos_rem = []
                    if patente_info.get('id'):
                        c = guild.get_role(patente_info['id'])
                        if c:
                            cargos_rem.append(c)
                    equipa_id = config.get('cargo_equipa_id')
                    if equipa_id:
                        ce = guild.get_role(equipa_id)
                        if ce:
                            cargos_rem.append(ce)
                    if cargos_rem:
                        await member.remove_roles(*cargos_rem)
                    await member.edit(nick=None)
                    await member.send(f'⚠️ Você foi despedido(a).\n**Motivo:** {motivo}')
                except Exception:
                    pass
                break

    velha_letra = func[1].split('-')[0] if func[1] and '-' in func[1] else ''
    velho_num = int(func[1].split('-')[1]) if func[1] and '-' in func[1] else 0
    await db.remove_funcionario(uid)
    if velha_letra:
        await db.shift_callsigns_down(velha_letra, velho_num)

    return jsonify({'ok': True})

@app.route('/api/pagamento/<int:semana_id>/<int:uid>/marcar-pago', methods=['POST'])
async def api_marcar_pago(semana_id, uid):
    if not session.get('is_admin'):
        return jsonify({'erro': 'Sem permissão'}), 403
    staff_id = session['user_id']
    await db.marcar_pago(semana_id, uid, staff_id)
    await db.add_log('dashboard', staff_id, f"Marcou pagamento como PAGO para <@{uid}>", {'semana': semana_id}, cor='success')

    bot = app.config.get('BOT_CLIENT')
    if bot:
        try:
            user = bot.get_user(uid) or await bot.fetch_user(uid)
            if user:
                pagamento = await db.get_pagamento(semana_id, uid)
                valor_str = formatar_moeda(pagamento[3]) if pagamento else '?'
                await user.send(f'✅ O seu pagamento de **{valor_str}** foi marcado como pago pelo staff!')
        except Exception:
            pass

    return jsonify({'ok': True})

@app.route('/api/semana/encerrar', methods=['POST'])
async def api_encerrar_semana():
    if not session.get('is_admin'):
        return jsonify({'erro': 'Sem permissão'}), 403
    resultado = await db.encerrar_semana(config.get('cargos_patentes', {}))
    await db.get_or_criar_semana_activa()
    await db.reset_all_times()
    await db.add_log('dashboard', session['user_id'], f"Encerrou a semana #{resultado['semana_id']}", cor='danger')
    return jsonify({'ok': True, 'semana_id': resultado['semana_id'],
                    'pagamentos': len(resultado['pagamentos'])})


# ── Logs do Sistema ──────────────────────────────────────────────────────────

@app.route('/admin/logs')
@login_required
@direcao_required
async def admin_logs():
    import json
    logs_raw = await db.get_logs(limit=500)
    
    logs_fmt = []
    for log in logs_raw:
        lid, ts, cat, uid, msg, det, cor = log
        try:
            detalhes = json.loads(det) if det else None
        except:
            detalhes = det

        logs_fmt.append({
            'id': lid,
            'timestamp': ts,
            'categoria': cat,
            'user_id': uid,
            'mensagem': msg,
            'detalhes': detalhes,
            'cor': cor
        })

    return await render_template('admin_logs.html', logs=logs_fmt)


# ── Configurações (Owner Only) ──────────────────────────────────────────────────

@app.route('/api/admin/patentes/save', methods=['POST'])
@login_required
async def api_admin_patentes_save():
    if not session.get('is_admin') and not session.get('is_direcao'):
        return jsonify({'erro': 'Acesso negado. Apenas Staff ou Direção.'}), 403

    form = await request.form
    p_slugs = form.getlist('p_slug[]')
    p_nomes = form.getlist('p_nome[]')
    p_roles = form.getlist('p_role[]')
    p_letras = form.getlist('p_letra[]')
    p_valores = form.getlist('p_valor[]')

    novas_patentes = {}
    for i in range(len(p_slugs)):
        slug = p_slugs[i].strip()
        if not slug: continue
        try:
            novas_patentes[slug] = {
                'nome': p_nomes[i],
                'id': int(p_roles[i]) if p_roles[i] else 0,
                'letra': p_letras[i].upper() if p_letras[i] else '',
                'valor_hora': float(p_valores[i]) if p_valores[i] else 0
            }
        except Exception as e:
            print(f"[DEBUG] Erro ao processar patente {slug}: {e}")

    if novas_patentes:
        await db.set_config('cargos_patentes', novas_patentes)
        await recarregar_config()
        
        # Atualiza o config.json para manter sincronia com o bot e as visualizações dinâmicas
        from db import get_configs, save_configs
        current_cfg = get_configs()
        current_cfg['cargos_patentes'] = novas_patentes
        save_configs(current_cfg)
        
        await db.add_log('dashboard', session['user_id'], "Alterou a configuração de Patentes/Salários no painel", cor='info')
        await flash('Patentes/Salários guardados com sucesso!', 'success')
        
    return redirect(url_for('admin_definicoes'))

@app.route('/admin/configuracoes')
@login_required
@owner_required
async def admin_configuracoes():
    return await render_template('admin_configuracoes.html', configs=config)

@app.route('/admin/configuracoes/save', methods=['POST'])
@login_required
@owner_required
async def admin_configuracoes_save():
    form = await request.form
    
    # 1. Geral
    geral_keys = [
        'server_name', 'nome_corp', 'log_channel_id', 'log_contratacoes_id', 
        'staff_role_id', 'cargo_equipa_id', 'timezone', 'owner_id'
    ]
    for k in geral_keys:
        val = form.get(k)
        if val:
            # Tenta converter IDs para int
            if '_id' in k or 'role' in k:
                try: val = int(val)
                except: pass
            await db.set_config(k, val)

    # 2. Patentes
    p_slugs = form.getlist('p_slug[]')
    p_nomes = form.getlist('p_nome[]')
    p_roles = form.getlist('p_role[]')
    p_letras = form.getlist('p_letra[]')
    p_valores = form.getlist('p_valor[]')

    novas_patentes = {}
    for i in range(len(p_slugs)):
        slug = p_slugs[i].strip()
        if not slug: continue
        try:
            novas_patentes[slug] = {
                'nome': p_nomes[i],
                'id': int(p_roles[i]) if p_roles[i] else 0,
                'letra': p_letras[i].upper() if p_letras[i] else '',
                'valor_hora': float(p_valores[i]) if p_valores[i] else 0
            }
        except Exception as e:
            print(f"[DEBUG] Erro ao processar patente {slug}: {e}")

    if novas_patentes:
        await db.set_config('cargos_patentes', novas_patentes)

    # 3. Rich Presence
    rp_interval = form.get('rp_interval')
    if rp_interval:
        try: await db.set_config('rp_interval', int(rp_interval))
        except: pass
    
    rp_statuses = form.get('rp_statuses', '').split('\n')
    rp_statuses = [s.strip() for s in rp_statuses if s.strip()]
    if rp_statuses:
        await db.set_config('rp_statuses', rp_statuses)

    # Recarregar tudo
    await recarregar_config()
    await db.add_log('dashboard', session['user_id'], "Alterou as configurações globais do sistema", cor='warning')
    await flash('Configurações guardadas com sucesso!', 'success')
    return redirect(url_for('admin_configuracoes'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
