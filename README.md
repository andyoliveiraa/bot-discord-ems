# 🤖 Pica-Ponto Pro: Gestão de RH e Dashboard Web (FiveM/MTA)

Sistema profissional de gestão de funcionários e registo de horas (ponto) para comunidades de roleplay, agora com **Dashboard Web Integrado**, sistema de **Arquivamento Semanal** e **Controlo de Pagamentos**.

---

## 📋 Funcionalidades Principais

### 🚀 Gestão de Ponto (Discord & Web)
- **Painel Interativo:** Registo de entrada/saída via comando `/ponto` com botões de Pausa/Retoma.
- **Auto-Recuperação:** Recupera pontos ativos após crashes ou reinícios do bot.
- **Encerramento Automático:** Fecha pontos abertos por mais de 24h para evitar abusos.
- **Edição via Dashboard:** Administradores podem adicionar/remover tempo ou cancelar pontos diretamente pelo site.

### 📊 Dashboard Web (ems.discloud.app)
- **Sincronização de Perfil:** Fotos de perfil sincronizadas em tempo real com o Discord.
- **Visão Geral:** Gráfico de horas semanais, ranking Top 10 e estimativa de pagamento.
- **Meus Pontos:** Histórico detalhado por dia com visualização de pausas.
- **Painel Administrativo:** Gestão completa de funcionários e configurações.

### 👥 Sistema de RH Integrado
- **Contratação/Demissão:** Automatização de cargos, callsigns (indicativos) e apelidos no Discord.
- **Promoções/Despromoções:** Mudança de patente com registo de motivo e logs.
- **Callsigns Inteligentes:** Reordenação automática (ex: se W-01 sai, W-02 passa a ser W-01).
- **Reset de Senhas:** Gerador de links seguros para acesso ao dashboard.

### 💶 Financeiro e Arquivamento
- **Arquivamento Semanal:** Encerra a semana gerando um PDF completo e arquiva os dados na BD.
- **Controlo de Pagamentos:** Marca funcionários como "Pagos" no dashboard.
- **Lembretes Diários:** O bot notifica automaticamente os staffs sobre pagamentos pendentes todas as manhãs.
- **Relatórios PDF:** Geração de folhas de pagamento profissionais com cálculos por patente.

---

## 🛠️ Configuração (`config.json`)

| Campo | Descrição |
|---|---|
| `server_name` | Nome da sua cidade/comunidade. |
| `owner_id` | ID do Discord do dono (recebe backups e logs críticos). |
| `log_channel_id` | Canal principal de logs de pontos e erros. |
| `log_contratacoes_id` | Canal exclusivo para logs de RH (Contratar/Promover). |
| `staff_role_id` | Cargo que tem acesso aos comandos administrativos e ao Dashboard Admin. |
| `ponto_role_id` | Cargo necessário para bater o ponto. |
| `cargos_patentes` | Configuração de salários, cargos e letras de indicativo. |

---

## 💻 Instalação

1. **Dependências:** `pip install -r requirements.txt`
2. **Configuração:** Preencha o `config.json` com os seus IDs e Token.
3. **Execução:** `python main.py` (O sistema possui um **Watcher** integrado que reinicia o bot em caso de erro).

---

## 📝 Comandos Staff (Discord)

- `/contratar @user [patente] [motivo]`
- `/promover @user [patente] [motivo]`
- `/despedir @user [motivo]`
- `/resetarsemana` — Gera PDF, faz backup e arquiva a semana.
- `/semana` — Apenas visualiza o relatório atual sem encerrar.
- `/ranking` — Top 10 de horas da semana.
- `/autocorrecao` — Sincroniza callsigns e nomes de todos os membros.

---

## ⚙️ Dashboard Admin

Aceda a `/admin/definicoes` no dashboard para:
- Editar o **Valor/Hora** de cada patente em tempo real.
- Resetar senhas de funcionários.
- Visualizar e gerir o histórico de pagamentos de semanas passadas.

---

## 🛡️ Segurança e Estabilidade
- **Base de Dados:** SQLite com `aiosqlite` para operações assíncronas.
- **Senhas:** Hashing seguro com `Werkzeug`.
- **Watcher:** Monitorização de processo para 99.9% de uptime.
- **Backups:** Diários às 07:00 enviados para o dono e canal de logs.

---
**Desenvolvido por andyydias**
