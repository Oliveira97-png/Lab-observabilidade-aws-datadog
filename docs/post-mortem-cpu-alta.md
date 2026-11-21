# Post-mortem: CPU alta na EC2 (incidente simulado)

> **Este é um exercício de laboratório.** O incidente foi provocado de propósito para validar o alarme, a notificação e o tempo de detecção. O formato é *blameless*: foca em processo e sistema, não em pessoas.

| | |
| --- | --- |
| **Data** | 08/11/2026 |
| **Ambiente** | EC2 `Lab-Monitoramento EC2` (t3.micro, 2 vCPUs), região us-east-2 |
| **Alarme** | `Lab-EC2-CPU-Alta` (CloudWatch) → SNS `Lab-Alertas` → e-mail |
| **Duração do evento** | Cerca de 15 minutos de carga (01:36 a 01:51 UTC, aproximado) |
| **Runbook** | [cpu-alta.md](../runbooks/cpu-alta.md) |

## 1. Resumo

Foi gerada carga de CPU na instância com `stress-ng --cpu 2 --timeout 900s`, ocupando as duas vCPUs a 100% por 15 minutos. O alarme `Lab-EC2-CPU-Alta` entrou em estado Em alarme às 01:46:03 UTC e o e-mail de alerta chegou pelo SNS. Depois que a carga terminou, o alarme voltou para OK às 01:52:03 UTC, com o e-mail de recuperação.

O fluxo de detecção funcionou de ponta a ponta. O **tempo de detecção foi de cerca de 10 minutos**, o esperado para a regra configurada (2 períodos de 5 minutos).

## 2. Impacto

- Laboratório sem usuários reais: nenhum impacto sobre clientes.
- O impacto sobre a aplicação Flask durante a carga **não foi medido**.
- Em um ambiente real, 10 minutos até o primeiro alerta seriam um intervalo relevante de lentidão ou indisponibilidade sem aviso.

## 3. Linha do tempo (UTC)

| Horário | Evento | Fonte |
| --- | --- | --- |
| 01:14:13 | Alarme criado | Histórico do alarme |
| 01:15:03 | Alarme muda de "Dados insuficientes" para OK | Histórico do alarme |
| ~01:15 a ~01:25 | Pico isolado de CPU, chegando perto de 89% em um único período. **Não disparou** o alarme, porque a regra exige 2 períodos seguidos | Gráfico do alarme. Origem não investigada |
| ~01:36 | Início da carga (`stress-ng`) | Estimado pelo `top` (01:36:48, com cerca de 47 s de CPU por processo). Coerente com o primeiro ponto do alarme (período de 01:36, média de 99,9%) |
| **01:46:03** | OK → **Em alarme**. Os dois pontos avaliados (períodos de 01:36 e 01:41) tiveram média de cerca de 99,9% e 100% | Histórico do alarme e e-mail de alerta |
| 01:46 | E-mail de alerta recebido (22:46 no fuso -03) | E-mail do SNS |
| ~01:51 | Fim da carga (início + 900 s) | Estimado. Coerente com o ponto de 01:47, que teve média de 79,8% |
| **01:52:03** | Em alarme → **OK**. O ponto de 01:47 teve média de 79,8%, logo abaixo do limite de 80% | Histórico do alarme e e-mail de recuperação |
| 01:52 | E-mail de recuperação recebido (22:52 no fuso -03) | E-mail do SNS |

Os horários do histórico do alarme são exatos. O início e o fim da carga são estimativas.

## 4. Métricas

| Métrica | Valor | Observação |
| --- | --- | --- |
| **MTTD** (início da carga até o alarme) | ≈ 10 minutos | Coerente com 2 períodos de 5 minutos |
| **MTTR** (fim da carga até o OK) | ≈ 1 minuto | Valor otimista: com "2 de 2", basta um período abaixo de 80% para voltar a OK. A recuperação veio de um período com média de 79,8%, muito perto do limite, porque o fim da carga caiu no meio dele |

## 5. Causa raiz

Causa deliberada: execução do `stress-ng` na própria instância para saturar as 2 vCPUs. Não houve falha de aplicação, configuração ou capacidade.

Para o objetivo do exercício, a pergunta relevante é outra: **por que a detecção levou 10 minutos?** Porque o monitoramento básico da EC2 publica a métrica a cada 5 minutos e a regra do alarme pede 2 períodos seguidos acima de 80%.

## 6. Detecção e resposta

- **Detecção:** automática, pelo alarme do CloudWatch. Nenhuma verificação manual foi necessária.
- **Notificação:** e-mail de alarme e de recuperação, via SNS.
- **Resposta:** a mitigação foi esperar o término do processo, já que a carga era conhecida. Em um caso real, o runbook indica como identificar o processo e mitigar.
- **Monitor equivalente no Datadog:** não avaliado neste teste. O monitor criado no Datadog é de taxa de erro da aplicação, e não de CPU, e o trial já havia encerrado quando o teste de CPU foi feito.

## 7. O que funcionou

- O fluxo CloudWatch → SNS → e-mail funcionou nas duas transições (alarme e recuperação).
- O tratamento de dados ausentes como "bom" manteve o alarme em OK com a instância parada, sem ruído.
- O pico isolado anterior não gerou alerta: a regra de 2 pontos filtra picos curtos.
- A role da instância não pôde alterar o estado do alarme (`AccessDenied`), o que confirma o menor privilégio. O teste forçado de estado deve ser feito com o usuário IAM, pelo CloudShell.

## 8. O que não funcionou ou pode melhorar

- **Detecção lenta para um incidente crítico.** Dez minutos até o primeiro aviso é pouco para um serviço de produção.
- **A notificação não aponta para o runbook.** O texto do alarme não tem o link, e quem recebe o e-mail precisa saber onde procurar.
- **Só a CPU é monitorada.** Memória e disco não são métricas nativas da EC2 e não têm alarme.
- **Sem alerta de falha de status da instância** nem de saldo de créditos de CPU, relevantes para uma t3.micro.
- **Erro de configuração na criação do alarme:** duas notificações iguais para o estado OK geraram o erro `OKActions must not contain repeats`. Foi corrigido antes de salvar, mas indica que a configuração manual no console é propensa a erro.

## 9. Ações

| # | Ação | Objetivo | Status |
| --- | --- | --- | --- |
| 1 | Incluir o link do runbook na descrição do alarme | Quem recebe o alerta sabe o que fazer | A fazer |
| 2 | Criar alarme de `StatusCheckFailed` | Detectar falha da instância | A fazer |
| 3 | Criar alarme para `CPUCreditBalance` ou `CPUSurplusCreditsCharged` | Evitar surpresa de desempenho e de custo na t3.micro | A fazer |
| 4 | Instalar o CloudWatch Agent para memória e disco | Cobrir o que a EC2 não publica por padrão | A fazer |
| 5 | Avaliar monitoramento detalhado (1 minuto) ou outra regra de períodos | Reduzir o MTTD. O detalhado tem custo adicional, então comparar com o benefício | A avaliar |
| 6 | Recriar o alarme e o SNS com Terraform | Evitar erros de configuração manual e permitir reproduzir o ambiente | A fazer |

## 10. Aprendizados

- O tempo de detecção é consequência direta da resolução da métrica e da regra do alarme. Entender isso importa mais do que decorar o número.
- Alarme bom é o que gera uma ação. Sem runbook, o e-mail só avisa, e não orienta.
- Cobertura de monitoramento não é só "ter um alarme". É saber o que ele **não** cobre.
- Medir de verdade (com carga real) revelou comportamentos que a configuração sozinha não mostra, como o pico isolado que não disparou o alarme.
