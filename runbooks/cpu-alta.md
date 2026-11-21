# Runbook: Lab-EC2-CPU-Alta

| | |
| --- | --- |
| **Alarme** | `Lab-EC2-CPU-Alta` (CloudWatch, região us-east-2) |
| **Recurso** | EC2 `Lab-Monitoramento EC2` (t3.micro, 2 vCPUs, Amazon Linux 2023) |
| **Notificação** | Tópico SNS `Lab-Alertas` (e-mail de alarme e de recuperação) |
| **Severidade** | Média (laboratório sem usuários reais) |
| **Última validação** | Incidente simulado de 08/11/2026 (veja o [post-mortem](../docs/post-mortem-cpu-alta.md)) |

## 1. O que significa

A média de `CPUUtilization` da instância ficou **acima de 80% em 2 períodos seguidos de 5 minutos**, ou seja, por pelo menos 10 minutos. Um pico curto, de um único período, não dispara o alarme.

O alarme trata dados ausentes como "bom". Com a instância parada ele fica em OK, e a ausência de alerta **não** prova que o ambiente está saudável.

## 2. Impacto

- A aplicação Flask (porta 8080) pode responder mais devagar ou deixar de responder.
- A t3.micro é burstável: CPU alta por muito tempo consome créditos e, no modo padrão, pode gerar cobrança de créditos excedentes (métrica `CPUSurplusCreditsCharged`).
- O Datadog Agent e o envio de logs ao S3 também disputam a mesma CPU.
- Em um ambiente real, o impacto seria lentidão ou indisponibilidade para os usuários.

## 3. Como investigar

Siga na ordem e pare quando achar a causa.

**3.1 Confirmar o alarme**

1. CloudWatch → Alarmes → `Lab-EC2-CPU-Alta` → veja o gráfico e a aba **Histórico**.
2. Observe a forma da curva: um degrau que se mantém sugere um processo preso ou carga constante; picos repetidos sugerem tarefa agendada ou rajada de requisições.
3. Confirme se havia algo planejado (teste, instalação, deploy) no mesmo horário.

**3.2 Entrar na instância**

```bash
ssh -i "Lab-monitoramento-key.pem" ec2-user@<IP-PUBLICO-ATUAL>
```

Se o SSH não responder, a instância pode estar saturada. Veja em EC2 → aba **Monitoramento** e **Verificações de status**, e tente de novo após alguns minutos. Se as verificações de status falharem, vá direto para a seção 4.

**3.3 Achar o processo responsável**

```bash
uptime
ps -eo pid,user,%cpu,%mem,etime,cmd --sort=-%cpu | head -10
vmstat 1 5
```

- `uptime`: carga média de 1, 5 e 15 minutos. Em 2 vCPUs, valores acima de 2 indicam saturação.
- `ps`: os 10 processos que mais usam CPU, com o tempo de execução.
- `vmstat`: se a coluna `wa` (espera de disco) for alta, o problema não é só CPU.

**3.4 Verificar a aplicação e o agente**

```bash
tail -n 50 ~/app-monitorada/app.log
tail -n 200 ~/app-monitorada/app.log | grep -o "Endpoint /[a-z]*" | sort | uniq -c
sudo systemctl status datadog-agent --no-pager
```

- O segundo comando mostra quais endpoints receberam mais chamadas (uma rajada em `/lenta` ou `/erro` explica CPU alta).
- Confirme se o `datadog-agent` está estável e não consumindo CPU de forma anormal.

**3.5 Verificar os créditos de CPU**

CloudWatch → Métricas → EC2 → Por instância → `CPUCreditBalance` e `CPUSurplusCreditsCharged`. Saldo de créditos caindo ou créditos excedentes sendo cobrados indicam uso sustentado acima do limite da instância.

## 4. Mitigação

| Situação | Ação |
| --- | --- |
| Processo de teste ou carga conhecida (por exemplo `stress-ng`) | Interromper o processo: `pkill stress-ng` ou `Ctrl+C` na sessão onde ele roda |
| Aplicação Flask em loop ou travada | Achar o processo com `sudo lsof -i :8080`, encerrar com `kill <PID>` (se não sair, `kill -9 <PID>`) e iniciar de novo com o comando padrão da aplicação |
| Rajada de requisições | Identificar a origem pelo log e, se for abuso, restringir a origem no Security Group |
| Causa não identificada e instância lenta | **Salvar os logs antes**, e depois reiniciar a instância (EC2 → Estado da instância → Reiniciar) |
| Problema recorrente | Registrar para análise de capacidade (veja a seção 7) |

**Salvar o log no S3 antes de reiniciar:**

```bash
aws s3 cp ~/app-monitorada/app.log s3://NOME-DO-BUCKET/logs/app-incidente-$(date +%F-%H%M).log --region us-east-2
```

**Confirmar a recuperação:** depois da mitigação, a média de CPU deve ficar abaixo de 80% em um período de 5 minutos. O alarme volta para **OK** e envia o e-mail de recuperação.

## 5. Escalonamento

Este laboratório não tem equipe de plantão. Em um ambiente real, o fluxo seria:

1. **N1 (operação/monitoramento):** investiga e aplica as mitigações das seções 3 e 4.
2. **N2 (infraestrutura/cloud):** acionado se, em cerca de 15 minutos, a causa não for identificada ou a mitigação não funcionar, ou se as verificações de status da instância falharem.
3. **Time da aplicação:** acionado se a causa for o código ou o comportamento da aplicação (loop, consulta pesada, pico de uso).

O prazo de 15 minutos é um exemplo e deve ser ajustado à criticidade do serviço.

## 6. Pós-incidente

- Registrar os horários em UTC (início, detecção, mitigação, recuperação) e calcular MTTD e MTTR.
- Escrever o post-mortem com linha do tempo, causa raiz e ações preventivas, usando o [modelo](../docs/post-mortem-cpu-alta.md) como referência.
- Se o alarme foi falso positivo ou barulhento, avaliar o limite (80%) e o número de períodos (2 de 2).

## 7. Limitações conhecidas

- O CloudWatch básico mede a EC2 a cada 5 minutos, por isso a detecção leva cerca de 10 minutos com esta regra.
- Memória e disco não são métricas nativas da EC2. Exigem o CloudWatch Agent.
- Não há alarme para falha de status da instância nem para o saldo de créditos de CPU (veja as ações do post-mortem).
