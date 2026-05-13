from quart import Quart, render_template, request, session, redirect, url_for, flash
import os
from werkzeug.security import check_password_hash, generate_password_hash
from db import Database, get_configs

app = Quart(__name__)
config = get_configs()
app.secret_key = config.get('secret_key', 'chave_secreta_padrao_muito_segura_123!')
db = Database('db.sqlite3')

@app.route('/')
async def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    func = await db.get_funcionario(user_id)
    if not func:
        session.clear()
        return redirect(url_for('login'))
        
    tempo_semanal = await db.get_user_time(user_id)
    tempo_total = tempo_semanal[1] if tempo_semanal else 0
    horas = int(tempo_total // 3600)
    minutos = int((tempo_total % 3600) // 60)
    
    ranking = await db.get_ranking(10)
    ranking_formatado = []
    for rank in ranking:
        r_user = await db.get_funcionario(rank[0])
        nome = r_user[2] if r_user else f"ID: {rank[0]}"
        callsign = r_user[1] if r_user else ""
        r_horas = int(rank[1] // 3600)
        r_minutos = int((rank[1] % 3600) // 60)
        ranking_formatado.append({'nome': nome, 'callsign': callsign, 'tempo': f"{r_horas}h {r_minutos}m"})

    is_admin = session.get('is_admin', False)

    return await render_template('index.html', func=func, horas=horas, minutos=minutos, ranking=ranking_formatado, is_admin=is_admin)

@app.route('/login', methods=['GET', 'POST'])
async def login():
    if request.method == 'POST':
        form = await request.form
        callsign = form.get('callsign')
        password = form.get('password')
        
        func = await db.get_funcionario_by_callsign(callsign)
        if func and func[4]: # func[4] is password_hash
            if check_password_hash(func[4], password):
                session['user_id'] = func[0]
                
                # Verifica se o usuário é administrador (tem o cargo de staff)
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
                await flash("Senha incorreta.", "danger")
        else:
            await flash("Usuário não encontrado ou não configurado.", "danger")
            
    return await render_template('login.html')

@app.route('/logout')
async def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
async def reset_password(token):
    func = await db.get_funcionario_by_reset_token(token)
    if not func:
        return "Token inválido ou expirado.", 400
        
    if request.method == 'POST':
        form = await request.form
        new_password = form.get('password')
        senha_hash = generate_password_hash(new_password)
        await db.update_password(func[0], senha_hash)
        
        # Invalida o token
        import secrets
        await db.set_reset_token(func[0], secrets.token_urlsafe(32))
        
        await flash("Senha alterada com sucesso! Você já pode fazer login.", "success")
        return redirect(url_for('login'))
        
    return await render_template('reset_password.html', func=func, token=token)

@app.route('/admin')
async def admin():
    if not session.get('is_admin', False):
        return "Acesso Negado.", 403
    return await render_template('admin.html')
