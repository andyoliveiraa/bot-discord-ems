import sys

new_func = '''
async def gerar_pdf_detalhado_ativa(db, config_atual, guild=None):
    """
    Gera PDF detalhado da semana ATIVA sem fechar.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        return None
        
    tz_cfg = config_atual.get('timezone', 'UTC')
    from pytz import timezone
    import datetime
    tz_obj = timezone(tz_cfg)
    
    semana_ativa = await db.get_semana_activa()
    inicio_str = datetime.datetime.fromtimestamp(semana_ativa[1], tz_obj).strftime('%d/%m/%Y') if semana_ativa else 'Desconhecido'
    fim_str = 'ATIVA'
    gerado_em = datetime.datetime.now(tz_obj).strftime('%d/%m/%Y as %H:%M')
    
    ranking = await db.get_ranking(amount=500)
    
    dados_funcs = []
    for user_data in ranking:
        user_id = user_data[0]
        total_seg = user_data[1]
        
        func_db = await db.get_funcionario(user_id)
        if func_db:
            nome_func = f"[{func_db[1]}] {func_db[2]}"
            cargo_id = func_db[0]
            patente_info = config_atual.get("cargos_patentes", {}).get(cargo_id, {})
            cargo_nome = patente_info.get("nome", cargo_id)
            valor_hora = patente_info.get("valor_hora", 0)
        else:
            if guild:
                membro = guild.get_member(user_id)
                nome_func = membro.display_name if membro else f"ID: {user_id}"
            else:
                nome_func = f"ID: {user_id}"
            cargo_nome = "Desconhecido"
            valor_hora = 0
            
        # Pega os pontos da semana ativa (com ID, como o arquivo espera)
        pontos = await db.get_all_user_registries_with_id(user_id)
        if not pontos and total_seg == 0:
            continue
            
        # Calcula valor registado simulado (não existe na BD porque ainda não encerrou)
        # O _construir_pdf também recalcula o valor exato no final, portanto podemos mandar 0 ou a estimativa
        abs_func = abs(total_seg)
        th = int(abs_func // 3600)
        tm = int((abs_func % 3600) // 60)
        total_min = th * 60 + tm
        pagamento_calc = (total_min / 60) * valor_hora * (-1 if total_seg < 0 else 1)
        
        dados_funcs.append({
            "user_id": user_id,
            "nome_func": nome_func,
            "cargo_nome": cargo_nome,
            "valor_hora": valor_hora,
            "valor_registado": pagamento_calc,
            "pago": 0,
            "pago_em": None,
            "pago_por": None,
            "pontos": pontos or [],
        })
        
    if not dados_funcs:
        return None
        
    return await _construir_pdf(dados_funcs, inicio_str, fim_str, gerado_em, "ATIVA", tz_obj)
'''

with open('pdf_helper.py', 'a', encoding='utf-8') as f:
    f.write(new_func)

print("Funcao injetada.")
