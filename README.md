# 🤖 Pica-Ponto Pro: Gestão de RH e Dashboard Web (FiveM/MTA)

Sistema profissional de gestão de funcionários e registo de horas (ponto) para comunidades de roleplay, agora com **Dashboard Web Integrado**, sistema de **Arquivamento Semanal**, **Controlo de Pagamentos** e **Planilha Pública de Produtividade**.

---

## 📋 Funcionalidades Principais

### 🚀 Gestão de Ponto (Discord & Web)
- **Painel Interativo:** Registo de entrada/saída via comando `/ponto` com botões de Pausa/Retoma.
- **Persistência Total:** Pontos ativos são salvos em disco e restaurados automaticamente após reinícios ou crashes, permitindo que o funcionário finalize o ponto normalmente sem perder horas.
- **Encerramento Automático:** Fecha pontos abertos por mais de 24h para evitar abusos.
- **Edição via Dashboard:** Administradores podem adicionar/remover tempo ou cancelar pontos diretamente pelo site.

### 📊 Dashboard Web (ems.discloud.app)
- **Planilha Pública:** Link permanente (`/planilha`) sem necessidade de login, que exibe as horas semanais atualizadas em tempo real e a estimativa de pagamentos de toda a equipa.
- **Sincronização de Perfil:** Fotos de perfil sincronizadas em tempo real com o Discord.
- **Visão Geral:** Gráfico de horas semanais, ranking Top 10 e estimativa de pagamento.
- **Meus Pontos:** Histórico detalhado por dia com visualização de pausas.
- **Rastreamento de IPs (Segurança):** O sistema regista o IP real e o dispositivo de quem acede (mesmo atrás do Cloudflare) e notifica o dono no Discord por segurança.

### 👥 Sistema de RH Integrado
- **Contratação/Demissão:** Automatização de cargos, callsigns (indicativos) e apelidos no Discord.
- **Promoções/Despromoções:** Mudança de patente com registo de motivo e logs.
- **Callsigns Inteligentes:** Reordenação automática (ex: se W-01 sai, W-02 passa a ser W-01).
- **Reset de Senhas:** Gerador de links seguros para acesso ao dashboard.

### 💶 Financeiro e Arquivamento
- **Arquivamento Semanal:** Encerra a semana gerando um PDF completo e arquiva os dados na BD.
- **Controlo de Pagamentos:** Marca funcionários como "Pagos" no dashboard.
- **Lembretes Diários:** O bot notifica automaticamente os staffs sobre pagamentos pendentes todas as manhãs.
- **Relatórios PDF:** Geração de folhas de pagamento profissionais com cálculos dinâmicos por patente.

---

## ⚙️ Gestão no Dashboard Admin

Aceda ao **Painel de Administração** (`/admin/definicoes`) e de **Configuração** (`/admin/configuracoes`) no dashboard para:
- **Gestão de Patentes / Salários:** Adicionar, editar ou remover patentes, definir os seus identificadores do Discord (Role IDs) e os valores recebidos à hora dinamicamente e sem tocar no código fonte.
- **Resetar Senhas:** De funcionários em caso de esquecimento.
- **Definições Gerais:** Editar Nome do Servidor, Links de Logos, Fuso Horário e Rich Presence do Discord diretamente pela interface.
- **Histórico Financeiro:** Visualizar e gerir o estado dos pagamentos de semanas passadas.

---

## 🛠️ Instalação (Inicial)

O sistema baseia-se num ficheiro `config.json` e num ficheiro de base de dados SQLite (`db.sqlite3`).
1. **Dependências:** `pip install -r requirements.txt`
2. **Configuração Inicial:** Preencha as configurações cruciais (Discord Token) no `config.json`.
3. **Execução:** `python main.py` (O sistema possui um **Watcher** integrado que reinicia o bot em caso de erro fatal `This event loop is already running`).
4. **Finalizar a Configuração:** Use a página do site `/admin/configuracoes` para personalizar o resto do bot (Cargos, Canais, etc).

---

## 📝 Comandos Discord

### Comandos de Utilizador
- `/ponto` — Abre o painel individual para Iniciar, Pausar ou Terminar a jornada de trabalho.
- `/meuponto` — Exibe estatísticas rápidas sobre as horas já acumuladas na semana corrente.
- `/reset_password` — Redefine a sua própria senha de acesso à Web Dashboard.

### Comandos Staff
- `/contratar @user [patente] [nome] [motivo]` — Registra um novo funcionário, cria callsign e gera senha web.
- `/promover @user [nova_patente] [motivo]` — Altera a patente, o callsign e os cargos Discord associados.
- `/despedir @user [motivo]` — Remove o funcionário da corporação e retira os seus cargos.
- `/addtempo @user [horas] [minutos] [motivo]` — Adiciona tempo manual a um funcionário.
- `/deltempo @user [horas] [minutos] [motivo]` — Remove tempo manual de um funcionário.
- `/pontosreg @user` — Consulta o histórico detalhado de registos de um utilizador nesta semana.
- `/resetarsemana` — Gera PDF, faz backup e encerra a semana (gera dívidas a pagar no dashboard).
- `/semana` — Apenas visualiza o relatório PDF atual de pagamentos sem encerrar a semana ativa.
- `/ranking` — Top 10 de horas trabalhadas na semana atual.
- `/autocorrecao` — Força a auto-correção de apelidos (Callsigns) e nomes de todos os membros do Discord conforme os registos da base de dados.
- `/resetarsenha @user` — Gera um novo link de redefinição de senha para o Dashboard em nome da Direção.
- `/resetar_todos` — Painel interativo para limpar e apagar dados gerais (usar com cuidado).

---

## 🛡️ Segurança e Estabilidade
- **Base de Dados:** SQLite com `aiosqlite` para operações assíncronas sem bloquear eventos do Discord.
- **Senhas:** Hashing seguro com `Werkzeug`.
- **IP Tracking:** Rastreamento exato de endereços via APIs externas compatíveis com Cloudflare (`meuip.com`), notificando o Dono em DMs para total monitorização do acesso às configs.
- **Backups:** Envio automático da Base de Dados às 07:00 para as DMs do Dono e canal de Logs.

---
**Desenvolvido e Otimizado por andyydias**
