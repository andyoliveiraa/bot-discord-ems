from quart import Quart, render_template, request, session, redirect, url_for, flash, jsonify
import os
import asyncio
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

async def get_user_avatar(user_id):
    bot = app.config.get('BOT_CLIENT')
    if bot:
        try:
            # Pega do cache primeiro
            user = bot.get_user(int(user_id))
            if not user:
                # Se não no cache, faz fetch
                user = await bot.fetch_user(int(user_id))
            if user:
                return user.display_avatar.url
        except Exception:
            pass
    return None

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


# ── helpers ──────────────────────────────────────────────────────────────────

def login_required(fn):
    import functools
    @functools.wraps(fn)
    async def wrapper(*a, **kw):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return await fn(*a, **kw)
    return wrapper

def admin_required(fn):
    import functools
    @functools.wraps(fn)
    async def wrapper(*a, **kw):
        if not session.get('is_admin'):
            return jsonify({'erro': 'Sem permissão'}), 403
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
        avatar = await get_user_avatar(rank[0])
        ranking_fmt.append({
            'nome': nome, 
            'callsign': callsign, 
            'tempo': f"{rh}h {rm}m",
            'avatar_url': avatar
        })

    historico = await db.get_pagamentos_user(user_id)
    avatar_url = await get_user_avatar(user_id)

    is_admin = session.get('is_admin', False)
    return await render_template('index.html',
        func=func, horas=horas, minutos=minutos,
        ranking=ranking_fmt, is_admin=is_admin,
        patente_nome=patente_nome,
        pagamento_estimado=formatar_moeda(pagamento_estimado),
        historico=historico,
        avatar_url=avatar_url)

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

    # Staff pode ver pontos de outro utilizador via ?uid=
    target_id = user_id
    target_func = func
    if is_admin:
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
    avatar_url = await get_user_avatar(target_id)

    return await render_template('meus_pontos.html',
        func=func, target_func=target_func, target_id=target_id,
        dias=dias_formatados, is_admin=is_admin, valor_hora=valor_hora,
        avatar_url=avatar_url)

# ── API: editar ponto ─────────────────────────────────────────────────────────

@app.route('/api/ponto/<int:ponto_id>/editar', methods=['POST'])
async def api_editar_ponto(ponto_id):
    if not session.get('is_admin'):
        return jsonify({'erro': 'Sem permissão'}), 403

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
            'pagamento': formatar_moeda(pagamento),
            'avatar_url': await get_user_avatar(uid)
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
        func_list=func_list, semanas=semanas_info,
        cargos=cargos, is_admin=True)

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

    nova_patente_info = config['cargos_patentes'][nova_patente]
    patente_antiga_info = config['cargos_patentes'].get(func[0], {})
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
