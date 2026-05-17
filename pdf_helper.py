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


def _linha(pdf, txt, cor=(0, 0, 0), estilo='', tamanho=10, altura=6):
    pdf.set_text_color(*cor)
    pdf.set_font("Arial", estilo, tamanho)
    # Encode to latin-1 safely
    pdf.cell(190, altura, txt=txt.encode('latin-1', 'replace').decode('latin-1'), ln=1)
    pdf.set_text_color(0, 0, 0)


def _linha_multi(pdf, txt, cor=(0, 0, 0), tamanho=9):
    pdf.set_text_color(*cor)
    pdf.set_font("Arial", '', tamanho)
    pdf.multi_cell(190, 5, txt=txt.encode('latin-1', 'replace').decode('latin-1'))
    pdf.set_text_color(0, 0, 0)


async def gerar_pdf_detalhado(db, config_atual, semana_id, inicio, fim):
    """
    Gera um relatorio PDF ultra-detalhado de uma semana FECHADA:
    - Todos os turnos, pausas, ajustes de staff
    - Explicacao textual de cada calculo
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

    pdf = FPDF()
    pdf.set_margins(10, 10, 10)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # ── Cabecalho ──────────────────────────────────────────────────────────────
    pdf.set_fill_color(30, 30, 50)
    pdf.rect(0, 0, 210, 40, 'F')
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 18)
    pdf.cell(190, 12, "RELATORIO ANALITICO DE PAGAMENTOS", ln=1, align='C')
    pdf.set_font("Arial", '', 11)
    pdf.cell(190, 8, f"Periodo: {inicio_str} a {fim_str}  |  ID Semana: {semana_id}", ln=1, align='C')
    gerado_em = datetime.datetime.now(tz_obj).strftime('%d/%m/%Y as %H:%M')
    pdf.cell(190, 7, f"Documento gerado em: {gerado_em}", ln=1, align='C')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(6)

    # ── Nota introdutoria ──────────────────────────────────────────────────────
    pdf.set_fill_color(240, 248, 255)
    pdf.set_font("Arial", 'I', 9)
    intro = (
        "Este documento apresenta o detalhamento completo de todos os registos de ponto da semana encerrada. "
        "Para cada funcionario sao listados todos os turnos individualmente, com horarios de entrada e saida, "
        "pausas realizadas, ajustes manuais efetuados por Staff, e a formula exata de calculo do pagamento. "
        "Qualquer turno fechado por Staff ou pelo sistema esta devidamente identificado."
    )
    pdf.multi_cell(190, 5, intro.encode('latin-1', 'replace').decode('latin-1'), border=1, fill=True)
    pdf.ln(5)

    total_geral_pagar = 0
    total_geral_horas_seg = 0

    for p in pagamentos:
        user_id = p[2]
        valor_registado = p[3]   # Valor que foi guardado na DB ao encerrar
        pago = p[4]
        pago_em = p[5]
        pago_por = p[6]

        func_db = await db.get_funcionario(user_id)
        if func_db:
            nome_func = f"[{func_db[1]}] {func_db[2]}"
            cargo_id = func_db[0]
            cargo_nome = func_db[1] if len(func_db) > 1 else cargo_id
            patente_info = config_atual.get("cargos_patentes", {}).get(cargo_id, {})
            valor_hora = patente_info.get("valor_hora", 0)
        else:
            nome_func = f"Funcionario ID: {user_id}"
            cargo_nome = "Desconhecido"
            valor_hora = 0

        # ── Cabecalho do funcionario ───────────────────────────────────────────
        pdf.set_fill_color(50, 50, 80)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", 'B', 13)
        pdf.cell(190, 10, f"  {nome_func}", ln=1, fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", '', 9)
        estado_pag = "PAGO" if pago == 1 else "POR PAGAR"
        pdf.cell(190, 5, f"  Cargo: {cargo_nome}  |  Valor/Hora configurado: {_fmt_moeda(valor_hora)}  |  Estado: {estado_pag}", ln=1)
        if pago == 1 and pago_em:
            dt_pago = datetime.datetime.fromtimestamp(pago_em, tz_obj).strftime('%d/%m/%Y as %H:%M')
            pdf.cell(190, 5, f"  Pago em: {dt_pago}  |  Registado por Staff ID: {pago_por}", ln=1)
        pdf.ln(2)

        # ── Buscar todos os pontos da semana ───────────────────────────────────
        pontos = await db.get_pontos_semana_arquivo(semana_id, user_id)

        total_seg_turnos = 0
        total_seg_ajustes = 0
        total_seg_removidos = 0

        if not pontos:
            _linha(pdf, "  AVISO: Nenhum registo de ponto encontrado para este funcionario nesta semana.", cor=(180, 0, 0))
        else:
            _linha(pdf, f"  REGISTOS DE PONTO ({len(pontos)} entrada(s) encontrada(s)):", estilo='B', tamanho=10)
            pdf.ln(1)

            turno_num = 0
            for pt in pontos:
                p_id, started, finished, staff_finished, duration, pauses_str = pt

                try:
                    pausas = json.loads(pauses_str) if pauses_str else []
                except Exception:
                    pausas = []

                dt_in = datetime.datetime.fromtimestamp(started, tz_obj)
                dt_in_str = dt_in.strftime('%d/%m/%Y %H:%M:%S')

                # ── Ajuste manual de horas por Staff (staff_finished == 2 ou 3) ──
                if staff_finished == 2:
                    pdf.set_fill_color(220, 255, 220)
                    pdf.set_font("Arial", 'B', 9)
                    pdf.cell(190, 6, f"  [AJUSTE POSITIVO por Staff] em {dt_in_str}", ln=1, fill=True)
                    _linha_multi(pdf,
                        f"    O que aconteceu: Um membro do Staff adicionou manualmente {_fmt_dur(duration)} de "
                        f"trabalho a este funcionario. Isto e usado para corrigir erros ou atribuir horas "
                        f"que nao foram registadas automaticamente.",
                        cor=(0, 100, 0), tamanho=8)
                    _linha(pdf, f"    Horas adicionadas: +{_fmt_dur(duration)}  (={duration} segundos)", cor=(0, 120, 0), tamanho=9)
                    pdf.ln(2)
                    total_seg_ajustes += duration

                elif staff_finished == 3:
                    pdf.set_fill_color(255, 220, 220)
                    pdf.set_font("Arial", 'B', 9)
                    pdf.cell(190, 6, f"  [AJUSTE NEGATIVO por Staff] em {dt_in_str}", ln=1, fill=True)
                    _linha_multi(pdf,
                        f"    O que aconteceu: Um membro do Staff removeu manualmente {_fmt_dur(abs(duration))} "
                        f"de trabalho a este funcionario. Isto e usado para corrigir excessos ou erros.",
                        cor=(150, 0, 0), tamanho=8)
                    _linha(pdf, f"    Horas removidas: {_fmt_dur(duration)}  (={duration} segundos)", cor=(180, 0, 0), tamanho=9)
                    pdf.ln(2)
                    total_seg_removidos += abs(duration)

                else:
                    # ── Turno normal ───────────────────────────────────────────
                    turno_num += 1

                    dt_out_str = datetime.datetime.fromtimestamp(finished, tz_obj).strftime('%H:%M:%S') if finished else "Em aberto"
                    bruto_seg = (finished - started) if finished else 0

                    # Calcular total de pausas
                    total_pausa_seg = 0
                    for p_entry in pausas:
                        if len(p_entry) >= 2:
                            total_pausa_seg += (p_entry[1] - p_entry[0])

                    # Classificar tipo de fecho
                    if duration == 0 and isinstance(staff_finished, int) and staff_finished > 10000:
                        tipo_fecho = f"Fechado por Staff (ID: {staff_finished}) - HORAS NAO CONTABILIZADAS"
                        cor_fundo = (255, 240, 200)
                        cor_aviso = (180, 100, 0)
                    elif isinstance(staff_finished, int) and staff_finished > 10000:
                        tipo_fecho = f"Fechado por Staff (ID: {staff_finished}) - Horas contabilizadas"
                        cor_fundo = (240, 240, 255)
                        cor_aviso = (50, 50, 150)
                    elif staff_finished == 1:
                        tipo_fecho = "Fechado automaticamente pelo sistema (timeout 24h)"
                        cor_fundo = (255, 245, 220)
                        cor_aviso = (150, 100, 0)
                    else:
                        tipo_fecho = "Fechado pelo proprio funcionario"
                        cor_fundo = (245, 255, 245)
                        cor_aviso = (0, 100, 0)

                    pdf.set_fill_color(*cor_fundo)
                    pdf.set_font("Arial", 'B', 9)
                    pdf.cell(190, 6, f"  Turno #{turno_num} | {dt_in_str}  ->  {dt_out_str}", ln=1, fill=True)
                    pdf.set_font("Arial", '', 8)
                    pdf.set_text_color(*cor_aviso)
                    pdf.cell(190, 5, f"    Tipo de fecho: {tipo_fecho}", ln=1)
                    pdf.set_text_color(0, 0, 0)

                    # Detalhes das pausas
                    if pausas:
                        _linha(pdf, f"    Pausas realizadas neste turno ({len(pausas)} pausa(s)):", tamanho=8)
                        for i, p_entry in enumerate(pausas):
                            if len(p_entry) >= 2:
                                p_in_str = datetime.datetime.fromtimestamp(p_entry[0], tz_obj).strftime('%H:%M:%S')
                                p_out_str = datetime.datetime.fromtimestamp(p_entry[1], tz_obj).strftime('%H:%M:%S')
                                dur_pausa = p_entry[1] - p_entry[0]
                                _linha(pdf,
                                    f"      Pausa {i+1}: Inicio {p_in_str} -> Retorno {p_out_str}  "
                                    f"(duracao: {_fmt_dur(dur_pausa)} = {dur_pausa} segundos)",
                                    tamanho=8, cor=(80, 80, 80))
                    else:
                        _linha(pdf, "    Sem pausas registadas neste turno.", tamanho=8, cor=(100, 100, 100))

                    # Explicacao do calculo do turno
                    pdf.ln(1)
                    _linha(pdf, "    >> CALCULO DESTE TURNO:", estilo='B', tamanho=8)
                    _linha_multi(pdf,
                        f"       1. Tempo total do turno (entrada ate saida): {_fmt_dur(bruto_seg)}\n"
                        f"          Formula: {dt_in_str} ate {dt_out_str} = {bruto_seg} segundos brutos\n\n"
                        f"       2. Total de pausas a descontar: {_fmt_dur(total_pausa_seg)}\n"
                        f"          Explicacao: O tempo de pausa nao e trabalho efetivo e e subtraido do total bruto.\n\n"
                        f"       3. Tempo util (contabilizado) = {bruto_seg}s - {total_pausa_seg}s = {duration}s = {_fmt_dur(duration)}",
                        tamanho=8)

                    if duration == 0 and isinstance(staff_finished, int) and staff_finished > 10000:
                        _linha(pdf,
                            "       ATENCAO: Este turno foi marcado como NAO CONTABILIZADO pelo Staff. "
                            "O valor e 0 e NAO entra no calculo do pagamento.",
                            cor=(200, 80, 0), tamanho=8)
                    else:
                        total_seg_turnos += duration

                    pdf.ln(3)

        # ── Resumo do funcionario ──────────────────────────────────────────────
        total_seg_func = total_seg_turnos + total_seg_ajustes - total_seg_removidos

        pdf.set_fill_color(230, 230, 250)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(190, 8, "  RESUMO E CALCULO FINAL DO FUNCIONARIO:", ln=1, fill=True)
        pdf.set_font("Arial", '', 9)

        _linha_multi(pdf,
            f"  Componentes do tempo total:\n"
            f"    a) Soma dos turnos contabilizados:       {_fmt_dur(total_seg_turnos)}  ({total_seg_turnos} segundos)\n"
            f"    b) Ajustes positivos por Staff:          +{_fmt_dur(total_seg_ajustes)}  (+{total_seg_ajustes} segundos)\n"
            f"    c) Ajustes negativos por Staff:          -{_fmt_dur(total_seg_removidos)}  (-{ total_seg_removidos} segundos)\n\n"
            f"  Total efetivo = (a) + (b) - (c)\n"
            f"               = {total_seg_turnos}s + {total_seg_ajustes}s - {total_seg_removidos}s\n"
            f"               = {total_seg_func}s\n"
            f"               = {_fmt_dur(total_seg_func)}")

        # Calculo do pagamento
        abs_func = abs(total_seg_func)
        th = int(abs_func // 3600)
        tm = int((abs_func % 3600) // 60)
        # Pagar por minutos completos
        total_min = th * 60 + tm
        pagamento_calc = (total_min / 60) * valor_hora * (-1 if total_seg_func < 0 else 1)

        _linha_multi(pdf,
            f"\n  Calculo do pagamento:\n"
            f"    Tempo efetivo:      {th}h {tm:02d}m = {total_min} minutos totais\n"
            f"    Valor configurado:  {_fmt_moeda(valor_hora)} por hora\n\n"
            f"    Formula aplicada:   (minutos / 60) * valor_hora\n"
            f"                     =  ({total_min} / 60) * {valor_hora}\n"
            f"                     =  {total_min/60:.4f} * {valor_hora}\n"
            f"                     =  {pagamento_calc:.2f} EUR\n\n"
            f"  Valor registado no sistema ao encerrar a semana: {_fmt_moeda(valor_registado)}\n"
            f"  Valor recalculado agora:                         {_fmt_moeda(pagamento_calc)}")

        if abs(pagamento_calc - valor_registado) > 0.01:
            _linha(pdf,
                f"  NOTA: Existe uma diferenca de {_fmt_moeda(pagamento_calc - valor_registado)} entre "
                f"o valor recalculado e o valor registado. Isto pode dever-se a alteracoes "
                f"de configuracao (ex: valor/hora) apos o encerramento da semana.",
                cor=(150, 80, 0), tamanho=8)

        total_geral_pagar += pagamento_calc
        total_geral_horas_seg += total_seg_func

        # Linha separadora
        pdf.ln(2)
        pdf.set_draw_color(100, 100, 180)
        pdf.set_line_width(0.5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

    # ── Resumo geral da semana ─────────────────────────────────────────────────
    pdf.add_page()
    pdf.set_fill_color(30, 30, 50)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 12, "RESUMO GERAL DA SEMANA", ln=1, fill=True, align='C')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    th_g = int(abs(total_geral_horas_seg) // 3600)
    tm_g = int((abs(total_geral_horas_seg) % 3600) // 60)
    total_min_g = th_g * 60 + tm_g

    _linha_multi(pdf,
        f"Periodo da semana:          {inicio_str} a {fim_str}\n"
        f"Numero de funcionarios:     {len(pagamentos)}\n\n"
        f"Total de horas trabalhadas: {th_g}h {tm_g:02d}m  ({total_min_g} minutos)\n"
        f"Total a pagar (somatorio):  {_fmt_moeda(total_geral_pagar)}\n\n"
        f"NOTA: O total acima e a soma dos pagamentos individuais calculados neste relatorio.\n"
        f"Se existirem divergencias com os valores registados no sistema, verifique se\n"
        f"o valor/hora foi alterado apos o encerramento da semana.",
        tamanho=11)

    pdf.ln(8)
    pdf.set_fill_color(50, 50, 80)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(190, 12, f"  TOTAL A PAGAR:  {_fmt_moeda(total_geral_pagar)}", ln=1, fill=True)
    pdf.set_text_color(0, 0, 0)

    pdf.ln(8)
    pdf.set_font("Arial", 'I', 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(190, 5, "Documento gerado automaticamente pelo sistema de gestao EMS via Painel Web.",
             ln=1, align='C')

    file_path = f"relatorio_semana_{semana_id}.pdf"
    await asyncio.to_thread(pdf.output, file_path)
    return file_path
