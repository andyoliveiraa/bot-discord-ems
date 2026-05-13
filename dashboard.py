from quart import Quart, render_template, request, session, redirect, url_for, flash, jsonify
import os
import asyncio
import aiohttp
import secrets
from werkzeug.security import check_password_hash, generate_password_hash
from db import Database, get_configs, save_configs

app = Quart(__name__)
config = get_configs()
app.secret_key = config.get('secret_key', 'chave_secreta_padrao_muito_segura_123!')
db = Database('db.sqlite3')

@app.before_serving
async def startup():
    await db.setup_db()
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
                print(f"[TRACK] Notificação com localização enviada para {owner_id}")
        except Exception as e:
            print(f"[DEBUG] Erro ao enviar notificação: {e}")
    
    return jsonify({'ok': True})

def formatar_moeda(valor):
    return f"{valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') + " €"

def recarregar_config():
    global config
    config = get_configs()
    app.secret_key = config.get('secret_key', 'chave_secreta_padrao_muito_segura_123!')
    # Sincroniza config com o módulo ponto
    try:
        import ponto
        ponto.config = config
    except ImportError:
        pass

@app.template_filter('timestamp_fmt')
def timestamp_fmt(ts):
    import datetime
    from pytz import timezone as tz
    try:
        return datetime.datetime.fromtimestamp(int(ts), tz(config.get('timezone', 'UTC'))).strftime('%H:%M')
    except Exception:
        return '--:--'

@app.template_filter('timestamp_semana')
def timestamp_semana(ts):
    import datetime
    from pytz import timezone as tz
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
    import datetime
    from pytz import timezone as tz
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
        func_list.sort(key=lambda x: x[3].lower()) # Sort by name
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
        hr_out = datetime.datetime.fromtimestamp(finished, tz(tz_cfg)).strftime('%H:%M')
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
    for dia, dados in sorted(por_dia.items(), key=lambda x: x[0].split('/')[::-1]):
        th = int(dados['total_seg'] // 3600)
        tm = int((dados['total_seg'] % 3600) // 60)
        dias_formatados.append({'dia': dia, 'total_h': th, 'total_m': tm, 'registros': dados['registros']})

    patente_info = config.get('cargos_patentes', {}).get(func[0] if func else '', {})
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
        return jsonify({'ok': True, 'nova_duration': new_dur})

    elif action == 'remove_time':
        h = int(form.get('horas', 0))
        m = int(form.get('minutos', 0))
        delta = h * 3600 + m * 60
        new_dur = max(0, duration_actual - delta)
        removed = duration_actual - new_dur
        await db.update_ponto_duration(ponto_id, new_dur)
        await db.del_time(user_id, removed)
        return jsonify({'ok': True, 'nova_duration': new_dur})

    elif action == 'cancel':
        staff_id = session['user_id']
        await db.del_time(user_id, duration_actual)
        await db.cancel_ponto(ponto_id, staff_id)
        return jsonify({'ok': True})

    elif action == 'edit_times':
        try:
            # Recebe strings no formato HH:MM
            str_in = form.get('hr_in')
            str_out = form.get('hr_out')
            
            # Precisamos manter a data original do ponto
            base_date = datetime.datetime.fromtimestamp(ponto[2]).date()
            
            t_in = datetime.datetime.strptime(str_in, '%H:%M').time()
            t_out = datetime.datetime.strptime(str_out, '%H:%M').time()
            
            # Criar novos timestamps
            new_in = int(datetime.datetime.combine(base_date, t_in).timestamp())
            new_out = int(datetime.datetime.combine(base_date, t_out).timestamp())
            
            # Se a saída for antes da entrada, assume que virou o dia (adiciona 24h)
            if new_out < new_in:
                new_out += 86400
                
            new_duration = new_out - new_in
            
            # Diferença para atualizar o total do usuário
            diff = new_duration - duration_actual
            
            async with db.pool.connect() as conn: # Usando pool se disponível ou connector direto
                await db.update_ponto_times(ponto_id, new_in, new_out, new_duration)
                if diff > 0:
                    await db.add_time(user_id, diff)
                elif diff < 0:
                    await db.del_time(user_id, abs(diff))
                    
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'erro': f'Erro ao processar horários: {str(e)}'}), 400

    return jsonify({'erro': 'Acção inválida'}), 400

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
    funcionarios = await db.get_all_funcionarios()
    semanas = await db.get_todas_semanas()
    cargos = config.get('cargos_patentes', {})

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
        import datetime
        from pytz import timezone as tz
        tz_cfg = config.get('timezone', 'UTC')
        inicio_str = datetime.datetime.fromtimestamp(inicio, tz(tz_cfg)).strftime('%d/%m/%Y')
        fim_str = datetime.datetime.fromtimestamp(fim, tz(tz_cfg)).strftime('%d/%m/%Y') if fim else 'Activa'
        pagamentos = await db.get_pagamentos_semana(sid)
        total_pago = sum(1 for p in pagamentos if p[4] == 1)
        total = len(pagamentos)
        semanas_info.append({
            'id': sid, 'inicio': inicio_str, 'fim': fim_str,
            'encerrada': encerrada, 'pagamentos': pagamentos,
            'total_pago': total_pago, 'total': total,
        })

    return await render_template('admin_definicoes.html', 
        func_list=func_list, 
        semanas=semanas_info, 
        cargos=cargos,
        is_admin=session.get('is_admin'),
        is_direcao=session.get('is_direcao'),
        ordenado_cargos=sorted(cargos.items(), key=lambda x: x[1].get('valor_hora', 0), reverse=True))

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
        # Note: add_funcionario uses ON CONFLICT UPDATE, so it works for updates too
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
    return jsonify({'ok': True, 'link': link, 'dm_enviada': enviado})

@app.route('/api/funcionario/<int:uid>/promover', methods=['POST'])
async def api_promover(uid):
    if not session.get('is_admin'):
        return jsonify({'erro': 'Sem permissão'}), 403
    form = await request.form
    nova_patente = form.get('patente')
    motivo = form.get('motivo', 'Dashboard')
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

@app.route('/api/config/salario', methods=['POST'])
async def api_update_salario():
    if not session.get('is_admin'):
        return jsonify({'erro': 'Sem permissão'}), 403
    form = await request.form
    patente_id = form.get('patente_id')
    novo_valor = form.get('valor_hora')
    if not patente_id or not novo_valor:
        return jsonify({'erro': 'Dados inválidos'}), 400
    try:
        novo_valor = int(novo_valor)
    except ValueError:
        return jsonify({'erro': 'Valor inválido'}), 400

    cfg = get_configs()
    if patente_id not in cfg.get('cargos_patentes', {}):
        return jsonify({'erro': 'Patente não encontrada'}), 404
    cfg['cargos_patentes'][patente_id]['valor_hora'] = novo_valor
    await asyncio.to_thread(save_configs, cfg)
    recarregar_config()
    return jsonify({'ok': True})

@app.route('/api/pagamento/<int:semana_id>/<int:uid>/marcar-pago', methods=['POST'])
async def api_marcar_pago(semana_id, uid):
    if not session.get('is_admin'):
        return jsonify({'erro': 'Sem permissão'}), 403
    staff_id = session['user_id']
    await db.marcar_pago(semana_id, uid, staff_id)

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
    return jsonify({'ok': True, 'semana_id': resultado['semana_id'],
                    'pagamentos': len(resultado['pagamentos'])})
