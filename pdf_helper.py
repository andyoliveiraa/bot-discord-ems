import asyncio
import datetime
from pytz import timezone
import json


def _fmt_dur(segundos):
    """Formata segundos para texto legivel: Xh Ym."""
    abs_s = abs(int(segundos))
    h = abs_s // 3600
    m = (abs_s % 3600) // 60
    sinal = "-" if segundos < 0 else ""
    return f"{sinal}{h}h {m:02d}m"


def _fmt_moeda(valor):
    s = f"{abs(valor):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    sinal = "-" if valor < 0 else ""
    return f"{sinal}{s} EUR"


def _enc(txt):
    """Encode seguro para latin-1."""
    return txt.encode('latin-1', 'replace').decode('latin-1')


def _linha(pdf, txt, cor=(0, 0, 0), estilo='', tamanho=10, altura=6):
    pdf.set_text_color(*cor)
    pdf.set_font("Arial", estilo, tamanho)
    pdf.multi_cell(190, altura, _enc(txt), new_x='LMARGIN', new_y='NEXT')
    pdf.set_text_color(0, 0, 0)


def _linha_multi(pdf, txt, cor=(0, 0, 0), tamanho=9):
    pdf.set_text_color(*cor)
    pdf.set_font("Arial", '', tamanho)
    pdf.multi_cell(190, 5, _enc(txt), new_x='LMARGIN', new_y='NEXT')
    pdf.set_text_color(0, 0, 0)


def _cabecalho_func(pdf, nome_func, cargo_nome, valor_hora, estado_pag, pago, pago_em, pago_por, tz_obj):
    """Desenha o cabecalho colorido de um funcionario."""
    pdf.set_fill_color(50, 50, 80)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 13)
    pdf.multi_cell(190, 10, _enc(f"  {nome_func}"), fill=True, new_x='LMARGIN', new_y='NEXT')
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", '', 9)
    pdf.multi_cell(190, 5, _enc(
        f"  Cargo: {cargo_nome}  |  Valor/Hora: {_fmt_moeda(valor_hora)}  |  Estado: {estado_pag}"
    ), new_x='LMARGIN', new_y='NEXT')
    if pago == 1 and pago_em:
        dt_pago = datetime.datetime.fromtimestamp(pago_em, tz_obj).strftime('%d/%m/%Y as %H:%M')
        pdf.multi_cell(190, 5, _enc(f"  Pago em: {dt_pago}  |  Staff ID: {pago_por}"), new_x='LMARGIN', new_y='NEXT')
    pdf.ln(2)


async def gerar_pdf_detalhado(db, config_atual, semana_id, inicio, fim):
    """
    Gera um relatorio PDF ultra-detalhado de uma semana FECHADA:
    - Pagina de indice
    - 1 pagina por funcionario
    - Todos os turnos, pausas, ajustes de staff
    - Formula final por funcionario e resumo geral
    """
    try:
        from fpdf import FPDF
    except ImportError:
        return None

    tz_cfg = config_atual.get('timezone', 'UTC')
    tz_obj = timezone(tz_cfg)

    pagamentos = await db.get_pagamentos_semana(semana_id)
    if not pagamentos:
        return None

    inicio_str = datetime.datetime.fromtimestamp(inicio, tz_obj).strftime('%d/%m/%Y')
    fim_str = datetime.datetime.fromtimestamp(fim, tz_obj).strftime('%d/%m/%Y') if fim else 'N/A'
    gerado_em = datetime.datetime.now(tz_obj).strftime('%d/%m/%Y as %H:%M')

    # ── Pre-carregar dados de todos os funcionarios ────────────────────────────
    dados_funcs = []
    for p in pagamentos:
        user_id  = p[2]
        valor_registado = p[3]
        pago     = p[4]
        pago_em  = p[5]
        pago_por = p[6]

        func_db = await db.get_funcionario(user_id)
        if func_db:
            nome_func  = f"[{func_db[1]}] {func_db[2]}"
            cargo_id   = func_db[0]
            patente_info = config_atual.get("cargos_patentes", {}).get(cargo_id, {})
            cargo_nome = patente_info.get("nome", cargo_id)
            valor_hora   = patente_info.get("valor_hora", 0)
        else:
            nome_func  = f"Funcionario ID: {user_id}"
            cargo_nome = "Desconhecido"
            valor_hora = 0

        pontos = await db.get_pontos_semana_arquivo(semana_id, user_id)
        dados_funcs.append({
            "user_id": user_id,
            "nome_func": nome_func,
            "cargo_nome": cargo_nome,
            "valor_hora": valor_hora,
            "valor_registado": valor_registado,
            "pago": pago,
            "pago_em": pago_em,
            "pago_por": pago_por,
            "pontos": pontos or [],
        })

    # ── Criar PDF ──────────────────────────────────────────────────────────────
    pdf = FPDF()
    pdf.set_margins(10, 10, 10)
    pdf.set_auto_page_break(auto=True, margin=15)

    # ══════════════════════════════════════════════════════════════════════════
    # PAGINA 1 — CAPA + INDICE
    # ══════════════════════════════════════════════════════════════════════════
    pdf.add_page()

    # Fundo do cabecalho
    pdf.set_fill_color(30, 30, 50)
    pdf.rect(0, 0, 210, 45, 'F')
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 18)
    pdf.set_xy(10, 8)
    pdf.cell(190, 12, "RELATORIO ANALITICO DE PAGAMENTOS", ln=1, align='C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(190, 7, _enc(f"Periodo: {inicio_str} a {fim_str}  |  ID Semana: {semana_id}"), ln=1, align='C')
    pdf.cell(190, 7, _enc(f"Documento gerado em: {gerado_em}"), ln=1, align='C')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)

    # Nota introdutoria
    pdf.set_fill_color(240, 248, 255)
    pdf.set_font("Arial", 'I', 9)
    intro = (
        "Este documento apresenta o detalhamento completo de todos os registos de ponto da semana encerrada. "
        "Para cada funcionario sao listados todos os turnos individualmente, com horarios de entrada e saida, "
        "pausas realizadas, ajustes manuais efetuados por Staff, e a formula exata de calculo do pagamento."
    )
    pdf.multi_cell(190, 5, _enc(intro), border=1, fill=True, new_x='LMARGIN', new_y='NEXT')
    pdf.ln(6)

    # Indice
    pdf.set_fill_color(30, 30, 50)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(190, 9, "  INDICE DE FUNCIONARIOS", ln=1, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    # Cabecalhos da tabela do indice
    pdf.set_fill_color(200, 200, 230)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(8,   7, "#",         border=1, fill=True, align='C')
    pdf.cell(70,  7, "Nome",      border=1, fill=True)
    pdf.cell(45,  7, "Cargo",     border=1, fill=True)
    pdf.cell(30,  7, "Pagamento", border=1, fill=True, align='R')
    pdf.cell(20,  7, "Estado",    border=1, fill=True, align='C')
    pdf.cell(17,  7, "Pagina",    border=1, fill=True, align='C')
    pdf.ln()

    # Numero da pagina de cada funcionario: capa=1, indice=1, func começa na pag 2
    pagina_func_inicio = 2
    for i, d in enumerate(dados_funcs):
        pdf.set_font("Arial", '', 8)
        fill = (i % 2 == 0)
        pdf.set_fill_color(245, 245, 255) if fill else pdf.set_fill_color(255, 255, 255)

        # Calcular pagamento estimado para o indice
        total_seg = sum(
            pt[4] for pt in d["pontos"]
            if not (pt[4] == 0 and isinstance(pt[3], int) and pt[3] > 10000)
            and pt[3] not in (2, 3)
        )
        ajustes_pos = sum(pt[4] for pt in d["pontos"] if pt[3] == 2)
        ajustes_neg = sum(abs(pt[4]) for pt in d["pontos"] if pt[3] == 3)
        total_ef = total_seg + ajustes_pos - ajustes_neg
        th_i = int(abs(total_ef) // 3600)
        tm_i = int((abs(total_ef) % 3600) // 60)
        pag_calc = ((th_i * 60 + tm_i) / 60) * d["valor_hora"] * (-1 if total_ef < 0 else 1)

        estado_str = "PAGO" if d["pago"] == 1 else "A PAGAR"
        pag_num = pagina_func_inicio + i

        nome_curto = d["nome_func"][:35] + "..." if len(d["nome_func"]) > 35 else d["nome_func"]
        cargo_curto = d["cargo_nome"][:22] + "..." if len(d["cargo_nome"]) > 22 else d["cargo_nome"]

        pdf.cell(8,  6, str(i + 1),           border=1, fill=fill, align='C')
        pdf.cell(70, 6, _enc(nome_curto),      border=1, fill=fill)
        pdf.cell(45, 6, _enc(cargo_curto),     border=1, fill=fill)
        pdf.cell(30, 6, _enc(_fmt_moeda(pag_calc)), border=1, fill=fill, align='R')
        pdf.cell(20, 6, _enc(estado_str),      border=1, fill=fill, align='C')
        pdf.cell(17, 6, str(pag_num),          border=1, fill=fill, align='C')
        pdf.ln()

    # ══════════════════════════════════════════════════════════════════════════
    # PAGINAS DOS FUNCIONARIOS — 1 por funcionario
    # ══════════════════════════════════════════════════════════════════════════
    total_geral_pagar   = 0
    total_geral_horas_s = 0

    for idx, d in enumerate(dados_funcs):
        pdf.add_page()

        # Mini-cabecalho de contexto no topo
        pdf.set_fill_color(30, 30, 50)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", '', 8)
        pdf.cell(190, 5,
                 _enc(f"Relatorio Semana {semana_id}  |  {inicio_str} a {fim_str}  |  Funcionario {idx+1} de {len(dados_funcs)}"),
                 ln=1, fill=True, align='C')
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

        nome_func       = d["nome_func"]
        cargo_nome      = d["cargo_nome"]
        valor_hora      = d["valor_hora"]
        valor_registado = d["valor_registado"]
        pago            = d["pago"]
        pago_em         = d["pago_em"]
        pago_por        = d["pago_por"]
        pontos          = d["pontos"]
        estado_pag      = "PAGO" if pago == 1 else "POR PAGAR"

        # Cabecalho do funcionario
        _cabecalho_func(pdf, nome_func, cargo_nome, valor_hora, estado_pag, pago, pago_em, pago_por, tz_obj)

        total_seg_turnos   = 0
        total_seg_ajustes  = 0
        total_seg_removidos = 0

        if not pontos:
            _linha(pdf, "  AVISO: Nenhum registo de ponto encontrado para este funcionario nesta semana.",
                   cor=(180, 0, 0))
        else:
            _linha(pdf, f"  REGISTOS DE PONTO ({len(pontos)} entrada(s) encontrada(s)):", estilo='B', tamanho=10)
            pdf.ln(1)

            turno_num = 0
            for pt in pontos:
                p_id, started, finished, staff_finished, duration, pauses_str = pt
                duration = duration or 0

                try:
                    pausas = json.loads(pauses_str) if pauses_str else []
                except Exception:
                    pausas = []

                dt_in     = datetime.datetime.fromtimestamp(started, tz_obj)
                dt_in_str = dt_in.strftime('%d/%m/%Y %H:%M:%S')

                # Ajuste positivo por Staff
                if staff_finished == 2:
                    pdf.set_fill_color(220, 255, 220)
                    pdf.set_font("Arial", 'B', 9)
                    pdf.multi_cell(190, 6, _enc(f"  [AJUSTE POSITIVO por Staff] em {dt_in_str}"), fill=True, new_x='LMARGIN', new_y='NEXT')
                    _linha_multi(pdf,
                        f"    Staff adicionou manualmente {_fmt_dur(duration)} de trabalho a este funcionario.",
                        cor=(0, 100, 0), tamanho=8)
                    _linha(pdf, f"    Horas adicionadas: +{_fmt_dur(duration)}  ({duration}s)", cor=(0, 120, 0), tamanho=9)
                    pdf.ln(2)
                    total_seg_ajustes += duration

                # Ajuste negativo por Staff
                elif staff_finished == 3:
                    pdf.set_fill_color(255, 220, 220)
                    pdf.set_font("Arial", 'B', 9)
                    pdf.multi_cell(190, 6, _enc(f"  [AJUSTE NEGATIVO por Staff] em {dt_in_str}"), fill=True, new_x='LMARGIN', new_y='NEXT')
                    _linha_multi(pdf,
                        f"    Staff removeu manualmente {_fmt_dur(abs(duration))} de trabalho a este funcionario.",
                        cor=(150, 0, 0), tamanho=8)
                    _linha(pdf, f"    Horas removidas: {_fmt_dur(duration)}  ({duration}s)", cor=(180, 0, 0), tamanho=9)
                    pdf.ln(2)
                    total_seg_removidos += abs(duration)

                else:
                    # Turno normal
                    turno_num += 1
                    dt_out_str  = datetime.datetime.fromtimestamp(finished, tz_obj).strftime('%H:%M:%S') if finished else "Em aberto"
                    bruto_seg   = (finished - started) if finished else 0

                    total_pausa_seg = 0
                    for p_entry in pausas:
                        if len(p_entry) >= 2:
                            total_pausa_seg += (p_entry[1] - p_entry[0])

                    if duration == 0 and isinstance(staff_finished, int) and staff_finished > 10000:
                        tipo_fecho = f"Fechado por Staff (ID:{staff_finished}) - NAO CONTABILIZADO"
                        cor_fundo  = (255, 240, 200)
                        cor_aviso  = (180, 100, 0)
                    elif isinstance(staff_finished, int) and staff_finished > 10000:
                        tipo_fecho = f"Fechado por Staff (ID:{staff_finished}) - Contabilizado"
                        cor_fundo  = (240, 240, 255)
                        cor_aviso  = (50, 50, 150)
                    elif staff_finished == 1:
                        tipo_fecho = "Fechado automaticamente pelo sistema (timeout 24h)"
                        cor_fundo  = (255, 245, 220)
                        cor_aviso  = (150, 100, 0)
                    else:
                        tipo_fecho = "Fechado pelo proprio funcionario"
                        cor_fundo  = (245, 255, 245)
                        cor_aviso  = (0, 100, 0)

                    pdf.set_fill_color(*cor_fundo)
                    pdf.set_font("Arial", 'B', 9)
                    pdf.multi_cell(190, 6, _enc(f"  Turno #{turno_num} | {dt_in_str}  ->  {dt_out_str}"), fill=True, new_x='LMARGIN', new_y='NEXT')
                    pdf.set_font("Arial", '', 8)
                    pdf.set_text_color(*cor_aviso)
                    pdf.multi_cell(190, 5, _enc(f"    Tipo de fecho: {tipo_fecho}"), new_x='LMARGIN', new_y='NEXT')
                    pdf.set_text_color(0, 0, 0)

                    if pausas:
                        _linha(pdf, f"    Pausas neste turno ({len(pausas)}):", tamanho=8)
                        for i, p_entry in enumerate(pausas):
                            if len(p_entry) >= 2:
                                p_in_str  = datetime.datetime.fromtimestamp(p_entry[0], tz_obj).strftime('%H:%M:%S')
                                p_out_str = datetime.datetime.fromtimestamp(p_entry[1], tz_obj).strftime('%H:%M:%S')
                                dur_pausa = p_entry[1] - p_entry[0]
                                _linha(pdf,
                                    f"      Pausa {i+1}: {p_in_str} -> {p_out_str}  ({_fmt_dur(dur_pausa)} = {dur_pausa}s)",
                                    tamanho=8, cor=(80, 80, 80))
                    else:
                        _linha(pdf, "    Sem pausas registadas.", tamanho=8, cor=(100, 100, 100))

                    pdf.ln(1)
                    _linha(pdf, "    >> CALCULO DESTE TURNO:", estilo='B', tamanho=8)
                    _linha_multi(pdf,
                        f"       1. Tempo bruto ({dt_in_str} -> {dt_out_str}): {_fmt_dur(bruto_seg)} = {bruto_seg}s\n"
                        f"       2. Pausas a descontar: {_fmt_dur(total_pausa_seg)} = {total_pausa_seg}s\n"
                        f"       3. Tempo util = {bruto_seg}s - {total_pausa_seg}s = {duration}s = {_fmt_dur(duration)}",
                        tamanho=8)

                    if duration == 0 and isinstance(staff_finished, int) and staff_finished > 10000:
                        _linha(pdf,
                            "       ATENCAO: Turno NAO CONTABILIZADO pelo Staff. Nao entra no pagamento.",
                            cor=(200, 80, 0), tamanho=8)
                    else:
                        total_seg_turnos += duration

                    pdf.ln(3)

        # ── Resumo do funcionario ──────────────────────────────────────────────
        total_seg_func = total_seg_turnos + total_seg_ajustes - total_seg_removidos

        pdf.set_fill_color(230, 230, 250)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(190, 8, "  RESUMO E CALCULO FINAL:", ln=1, fill=True)
        pdf.set_font("Arial", '', 9)

        _linha_multi(pdf,
            f"  a) Turnos contabilizados:   {_fmt_dur(total_seg_turnos)} ({total_seg_turnos}s)\n"
            f"  b) Ajustes positivos Staff: +{_fmt_dur(total_seg_ajustes)} (+{total_seg_ajustes}s)\n"
            f"  c) Ajustes negativos Staff: -{_fmt_dur(total_seg_removidos)} (-{total_seg_removidos}s)\n"
            f"  Total efetivo = (a)+(b)-(c) = {_fmt_dur(total_seg_func)} ({total_seg_func}s)")

        abs_func  = abs(total_seg_func)
        th        = int(abs_func // 3600)
        tm        = int((abs_func % 3600) // 60)
        total_min = th * 60 + tm
        pagamento_calc = (total_min / 60) * valor_hora * (-1 if total_seg_func < 0 else 1)

        _linha_multi(pdf,
            f"\n  Calculo do pagamento:\n"
            f"    Tempo efetivo:     {th}h {tm:02d}m = {total_min} min\n"
            f"    Valor/hora config: {_fmt_moeda(valor_hora)}\n"
            f"    Formula:  ({total_min} / 60) * {valor_hora} = {pagamento_calc:.2f} EUR\n\n"
            f"    Valor registado no sistema:  {_fmt_moeda(valor_registado)}\n"
            f"    Valor recalculado agora:      {_fmt_moeda(pagamento_calc)}")

        if abs(pagamento_calc - valor_registado) > 0.01:
            _linha(pdf,
                f"  NOTA: Diferenca de {_fmt_moeda(pagamento_calc - valor_registado)} "
                f"(possivel alteracao de valor/hora apos encerramento da semana).",
                cor=(150, 80, 0), tamanho=8)

        total_geral_pagar   += pagamento_calc
        total_geral_horas_s += total_seg_func

    # ══════════════════════════════════════════════════════════════════════════
    # PAGINA FINAL — RESUMO GERAL
    # ══════════════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.set_fill_color(30, 30, 50)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 12, "RESUMO GERAL DA SEMANA", ln=1, fill=True, align='C')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    th_g       = int(abs(total_geral_horas_s) // 3600)
    tm_g       = int((abs(total_geral_horas_s) % 3600) // 60)
    total_min_g = th_g * 60 + tm_g

    _linha_multi(pdf,
        f"Periodo da semana:           {inicio_str} a {fim_str}\n"
        f"Numero de funcionarios:      {len(dados_funcs)}\n\n"
        f"Total de horas trabalhadas:  {th_g}h {tm_g:02d}m  ({total_min_g} minutos)\n"
        f"Total a pagar (somatorio):   {_fmt_moeda(total_geral_pagar)}\n\n"
        f"NOTA: Se existirem divergencias com os valores registados no sistema,\n"
        f"verifique se o valor/hora foi alterado apos o encerramento da semana.",
        tamanho=11)

    pdf.ln(8)
    pdf.set_fill_color(50, 50, 80)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(190, 12, _enc(f"  TOTAL A PAGAR:  {_fmt_moeda(total_geral_pagar)}"), ln=1, fill=True)
    pdf.set_text_color(0, 0, 0)

    pdf.ln(8)
    pdf.set_font("Arial", 'I', 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(190, 5, "Documento gerado automaticamente pelo sistema de gestao EMS via Painel Web.",
             ln=1, align='C')

    file_path = f"relatorio_semana_{semana_id}.pdf"
    await asyncio.to_thread(pdf.output, file_path)
    return file_path
