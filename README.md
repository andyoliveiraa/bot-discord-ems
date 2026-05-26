# 🤖 Pica-Ponto Pro: Gestão de RH e Dashboard Web (FiveM/MTA)

Sistema profissional de gestão de funcionários e registo de horas (ponto) para comunidades de roleplay, com **Dashboard Web Integrado**, sistema de **Arquivamento Semanal**, **Controlo de Pagamentos**, **Planilha Pública de Produtividade** e **Relatório PDF Ultra-Detalhado**.

---

## 📋 Funcionalidades Principais

### 🚀 Gestão de Ponto (Discord & Web)
- **Painel Interativo:** Registo de entrada/saída via comando `/ponto` com botões de Pausa/Retoma/Finalizar.
- **Persistência Total:** Pontos ativos são salvos em disco e restaurados automaticamente após reinícios ou crashes, permitindo que o funcionário finalize o ponto normalmente sem perder horas.
- **Encerramento Automático:** Fecha pontos abertos por mais de 24h para evitar abusos.
- **Edição via Dashboard:** Administradores podem adicionar/remover tempo, cancelar pontos ou ajustar horários exatos diretamente pelo painel web.

### 📊 Dashboard Web
- **Planilha Pública:** Link permanente (`/planilha`) sem necessidade de login, que exibe as horas semanais em tempo real e estimativa de pagamentos de toda a equipa. Atualização automática a cada 60 segundos.
- **Sincronização de Perfil:** Fotos de perfil do Discord sincronizadas em tempo real.
- **Visão Geral:** Ranking Top 10, estimativa de pagamento e horas semanais da semana corrente.
- **Meus Pontos:** Histórico detalhado por dia com visualização de pausas, duração de cada turno e tipo de fecho.
- **Pontos Abertos (Admin):** Monitorização em tempo real de todos os pontos ativos da equipa, com cronómetro ao vivo.
- **Rastreamento de IPs (Segurança):** Registo do IP real e dispositivo de quem acede (compatível com Cloudflare) com notificação ao Dono via Discord.

### 💶 Financeiro, Arquivamento e PDF
- **Arquivamento Semanal:** Encerra a semana, arquivando todos os pontos e criando registos de pagamento por funcionário.
- **Controlo de Pagamentos:** Marca funcionários como "Pagos" no dashboard com registo de quem marcou e quando.
- **Lembretes Diários:** O bot notifica automaticamente os staffs sobre pagamentos pendentes todas as manhãs, com nomes e números de funcionário (sem IDs numéricos).
- **Relatório PDF Ultra-Detalhado (NOVO):** Disponível em cada semana encerrada no painel admin:
  - Lista todos os turnos individualmente com horários exatos (entrada, saída, pausas)
  - Identifica fechos por Staff (com ID) e turnos não contabilizados
  - Regista ajustes manuais de horas (adicionadas/removidas por Staff) com cor diferenciada
  - Apresenta a **fórmula matemática completa** de cálculo do pagamento por funcionário
  - Inclui página de resumo geral com total da semana
  - Enviado automaticamente para o canal de Logs do Discord ao clicar no botão "PDF Detalhado"

### 👥 Sistema de RH Integrado
- **Contratação/Demissão:** Automatização de cargos, números de funcionário (identificadores) e apelidos limpos no Discord.
- **Promoções/Despromoções:** Mudança de patente com registo de motivo e logs.
- **Apelidos Limpos no Discord:** O bot mantém o apelido dos membros no Discord estritamente com o seu **Nome**, ocultando siglas antigas para maior profissionalismo.
- **Números de Funcionário Permanentes:** Atribuição sequencial automática a partir de **`1001`** (ex: `1001`, `1002`, `1003`...), que permanecem fixos ao funcionário (sem reordenação dinâmica ao demitir alguém) e servem para aceder ao painel.
- **Reset de Senhas:** Gerador de links seguros para acesso ao dashboard, enviado por DM.
- **Relatórios de Semana:** Nome e número do funcionário em todos os relatórios e lembretes Discord.

---

## ⚙️ Gestão no Dashboard Admin

Aceda ao **Painel de Administração** (`/admin/definicoes`) e de **Configuração** (`/admin/configuracoes`) no dashboard para:
- **Gestão de Patentes / Salários:** Adicionar, editar ou remover patentes, definir os seus identificadores do Discord (Role IDs) e os valores recebidos à hora dinamicamente e sem tocar no código fonte.
- **Controlo de Pagamentos:** Ver quem está pago/por pagar em cada semana encerrada e marcar pagamentos com um clique.
- **Gerar PDF Detalhado:** Botão em cada semana encerrada para gerar e enviar o relatório analítico completo no canal de Logs.
- **Pontos Abertos:** Monitorização ao vivo de todos os pontos ativos com opção de fechar ou cancelar pelo painel.
- **Resetar Senhas:** De funcionários em caso de esquecimento.
- **Definições Gerais:** Editar Nome do Servidor, Fuso Horário, Rich Presence do Discord diretamente pela interface.
- **Logs do Sistema:** Registo auditável de todas as ações administrativas realizadas no painel.

---

## 🛠️ Instalação (Inicial)

O sistema baseia-se num ficheiro `config.json` e num ficheiro de base de dados SQLite (`db.sqlite3`).
1. **Dependências:** `pip install -r requirements.txt`
2. **Configuração Inicial:** Preencha as configurações cruciais (Discord Token, IDs de canais e cargos) no `config.json`.
3. **Execução:** `python main.py` (O bot e o servidor Web iniciam no mesmo processo).
4. **Finalizar a Configuração:** Use a página do site `/admin/configuracoes` para personalizar o resto do bot (Cargos, Canais, etc).

> **Nota:** As configurações alteradas via Dashboard são guardadas na base de dados SQLite e aplicadas sem necessidade de reiniciar o bot.

---

## 📝 Comandos Discord

### Comandos de Utilizador
- `/ponto` — Abre o painel individual para Iniciar, Pausar ou Terminar a jornada de trabalho.
- `/meuponto` — Exibe estatísticas rápidas sobre as horas já acumuladas na semana corrente.
- `/reset_password` — Redefine a sua própria senha de acesso à Web Dashboard.

### Comandos Staff
- `/contratar @user [patente] [nome] [motivo]` — Registra um novo funcionário, atribui número de funcionário e gera senha web.
- `/promover @user [nova_patente] [motivo]` — Altera a patente e os cargos Discord associados.
- `/editar_funcionario @user [motivo] [novo_callsign] [novo_nome] [novo_cargo]` — Altera manualmente o número de funcionário, nome e/ou cargo de um funcionário.
- `/definir_numero @user [novo_numero] [motivo]` — Atribui diretamente um número de funcionário. Se o número estiver ocupado por outra pessoa, reatribui automaticamente o proprietário anterior para o próximo número livre disponível na sua patente.
- `/despedir @user [motivo]` — Remove o funcionário da corporação e retira os seus cargos.
- `/addtempo @user [horas] [minutos] [motivo]` — Adiciona tempo manual a um funcionário.
- `/deltempo @user [horas] [minutos] [motivo]` — Remove tempo manual de um funcionário.
- `/pontosreg @user` — Consulta o histórico detalhado de registos de um utilizador nesta semana.
- `/resetarsemana` — Gera PDF, faz backup e encerra a semana (gera dívidas a pagar no dashboard).
- `/semana` — Apenas visualiza o relatório PDF atual de pagamentos sem encerrar a semana ativa.
- `/ranking` — Top 10 de horas trabalhadas na semana atual (exibe Nº Func. e Nome).
- `/autocorrecao` — Força a auto-correção de nomes e apelidos de todos os membros do Discord conforme os registos da base de dados (removendo siglas e callsigns dos nicks no Discord).
- `/resetarsenha @user` — Gera um novo link de redefinição de senha para o Dashboard em nome da Direção.
- `/resetar_todos` — Painel interativo para limpar e apagar dados gerais (usar com cuidado).

---

## 🛡️ Segurança e Estabilidade
- **Base de Dados:** SQLite com `aiosqlite` para operações assíncronas sem bloquear eventos do Discord.
- **Senhas:** Hashing seguro com `Werkzeug` (bcrypt).
- **IP Tracking:** Rastreamento exato de endereços via APIs externas compatíveis com Cloudflare, notificando o Dono em DMs.
- **Backups:** Envio automático da Base de Dados às 07:00 para as DMs do Dono e canal de Logs.
- **Logs de Auditoria:** Todas as ações administrativas (pagamentos, promoções, demissões, etc.) são registadas na base de dados com timestamp e utilizador responsável.

---

## 📦 Dependências Principais
- `py-cord` — Biblioteca Discord
- `quart` — Servidor Web assíncrono (Flask-compatível)
- `aiosqlite` — Base de dados SQLite assíncrona
- `fpdf` — Geração de relatórios PDF
- `aiohttp` — Pedidos HTTP assíncronos
- `pytz` — Gestão de fusos horários
- `werkzeug` — Hashing de senhas

---
**Desenvolvido e Otimizado por andyydias**
