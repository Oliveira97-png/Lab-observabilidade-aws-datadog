# Laboratório de Observabilidade em Cloud: AWS + Datadog

Laboratório prático em que uma aplicação Python/Flask roda em uma instância EC2 e é monitorada de duas formas: pelos serviços nativos da AWS (CloudWatch e SNS) e pelo Datadog (métricas, traces e logs). A instância ainda envia seus logs para um bucket S3 usando uma role do IAM com menor privilégio.

O objetivo é praticar o ciclo completo de operação em nuvem: provisionar, proteger, monitorar, alertar, simular um incidente, medir o tempo de detecção e documentar.

> Este é um projeto de estudo, não um ambiente de produção. Uma instância, sem balanceador e criado pelo console. A seção \[Limitações e próximos passos](#limitações-e-próximos-passos) diz o que mudaria em produção.

## Arquitetura

!\[Topologia do laboratório](docs/img/topologia\_lab\_observabilidade.png)

Três fluxos saem da EC2:

1. **Alerta nativo:** a métrica de CPU vai ao CloudWatch, o alarme aciona o SNS e o SNS envia o e-mail.
2. **Logs e backup:** um cron usa o AWS CLI para enviar o `app.log` ao S3. A permissão vem de uma role do IAM, sem chaves de acesso na instância.
3. **Observabilidade:** o Datadog Agent envia métricas, traces (APM) e logs ao Datadog.

## Recursos e o que cada um faz

|Recurso|Função no projeto|
|-|-|
|**EC2 t3.micro** (Amazon Linux 2023, us-east-2)|Hospeda a aplicação e o agente. Instância burstável, escolhida pelo custo|
|**Security Group**|Firewall da instância. SSH (22) e a aplicação (8080) liberados somente para o meu IP|
|**App Flask**|API de teste com endpoints que geram tráfego normal (`/`, `/status`), lentidão (`/lenta`) e erro HTTP 500 (`/erro`)|
|**Datadog Agent 7 + ddtrace**|O Agent coleta métricas do host e lê o `app.log`. O ddtrace gera traces de latência e erro por endpoint|
|**Bucket S3**|Guarda cópias do `app.log`. Acesso público bloqueado, versionamento, criptografia SSE-S3 e regra de ciclo de vida que expira objetos em 30 dias|
|**Role e política do IAM**|Dão à EC2 permissão temporária para gravar e ler somente na pasta `logs/` do bucket|
|**MFA e usuário de leitura (IAM)**|MFA no usuário root e no administrador. Usuário `Lab-leitura`, em grupo com `ReadOnlyAccess` e MFA próprio, para acesso sem permissão de alteração|
|**Cron + AWS CLI**|Enviam o `app.log` ao S3 de hora em hora|
|**Alarme do CloudWatch**|Monitora `CPUUtilization` e dispara quando a média passa de 80% em 2 períodos seguidos de 5 minutos|
|**Tópico SNS**|Recebe a mudança de estado do alarme e entrega o e-mail de alarme e o de recuperação|
|**AWS Budgets**|Alerta de custo mensal de US$ 5, para evitar surpresa na fatura|

## Decisões de projeto

* **Role do IAM em vez de chaves de acesso.** Chaves podem vazar e precisam de rotação. A role entrega credenciais temporárias e automáticas à instância.
* **Política limitada à pasta `logs/`.** Princípio do menor privilégio. Provado na prática: gravar em outra pasta retorna `AccessDenied` (veja abaixo).
* **Ciclo de vida de 30 dias no bucket.** Controla custo. Como o versionamento está ativo, a regra também exclui permanentemente as versões antigas.
* **Alarme tratando dados ausentes como "bom".** A instância é desligada entre as sessões de estudo, e sem essa configuração o alarme ficaria em "dados insuficientes".
* **Sem balanceador de carga.** Foge do foco do projeto (monitoramento) e aumenta o custo.
* **SSH local com arquivo `.pem`.** O EC2 Instance Connect do navegador não funciona com o SSH restrito ao meu IP, e abrir para `0.0.0.0/0` não era aceitável.

## Como foi construído

### 1\. Base AWS e segurança

Alerta de custo, usuário IAM administrador (a conta root não é usada no dia a dia), EC2 com Amazon Linux 2023 e Security Group restrito ao meu IP.

### 2\. Aplicação e Datadog

Aplicação Flask na porta 8080 (as portas 5000 e 5001 são usadas pelo próprio Agent). Datadog Agent com APM (`ddtrace-run`) e coleta de logs a partir do arquivo `app.log`.
O que foi validado no Datadog:

* **APM:** o serviço aparece com requisições, taxa de erro (gerada pelo `/erro`) e latência alta (gerada pelo `/lenta`).
* **Logs:** os eventos INFO, WARNING e ERROR da aplicação chegam ao Live Tail, junto com os códigos HTTP.
* **Dashboard** "Lab Observabilidade - AWS + Datadog", com 11 widgets: infraestrutura do host (CPU, memória, disco, carga do sistema, rede e I/O de disco), aplicação (requisições, taxa de erro e latência p95), logs da aplicação e estado dos alertas.
* **Monitor** `\[Lab] Taxa de erro alta no serviço flask`: dispara quando a taxa de erro do serviço passa de 10% nos últimos 5 minutos. A mensagem traz o impacto, como investigar e o destinatário por e-mail. Disparou durante os testes, com e-mail de alerta recebido, e voltou a OK. O Datadog também listou 7 monitors de host e 2 de APM, de pacotes recomendados.

!\[Dashboard no Datadog](docs/img/datadog-dashboard.png)

!\[Monitor de taxa de erro](docs/img/datadog-monitor.png)

!\[E-mail do alerta do Datadog](docs/img/datadog-alerta-email.png)

### 3\. S3 e IAM

Política de menor privilégio (`Lab-EC2-S3-Logs`):

```json
{
  "Version": "2012-10-17",
  "Statement": \[
    {
      "Effect": "Allow",
      "Action": \["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::NOME-DO-BUCKET/logs/\*"
    },
    {
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::NOME-DO-BUCKET",
      "Condition": { "StringLike": { "s3:prefix": \["logs/\*"] } }
    }
  ]
}
```

A role `Lab-EC2-S3-Role` tem relação de confiança com `ec2.amazonaws.com` e só essa política anexada. Foi anexada à instância pelo console.

Envio automático do log, a cada hora (cron):

```
0 \* \* \* \* /usr/bin/aws s3 cp /home/ec2-user/app-monitorada/app.log s3://NOME-DO-BUCKET/logs/app-$(date +\\%F-\\%H00).log --region us-east-2
```

**Validação da role**, a partir da EC2 (o ID da conta foi substituído):

!\[Teste da role](docs/img/terminal-role-s3.png)

* `get-caller-identity` mostra `assumed-role/Lab-EC2-S3-Role`.
* O envio para `logs/` funciona.
* O envio para outra pasta retorna `AccessDenied`.

A role também não consegue alterar alarmes do CloudWatch, como esperado, porque só tem permissão de S3.

### 4\. Alerta nativo: CloudWatch + SNS

|Configuração|Valor|
|-|-|
|Métrica|`CPUUtilization` (EC2)|
|Estatística / período|Média / 5 minutos|
|Condição|Maior que 80%|
|Pontos de dados|2 de 2|
|Dados ausentes|Tratar como "bom" (não violando)|
|Notificações|Em alarme e OK, ambas para o tópico SNS `Lab-Alertas`|

## Incidente simulado

Para validar o fluxo completo, gerei carga na CPU da EC2 com `stress-ng --cpu 2 --timeout 900s` (duas vCPUs a 100% por 15 minutos).

|Horário (UTC)|Evento|Fonte|
|-|-|-|
|\~01:36|Início da carga|Estimado pelo `top`|
|**01:46:03**|OK → Em alarme (e-mail de alerta)|Histórico do alarme|
|\~01:51|Fim da carga|Estimado (início + 900 s)|
|**01:52:03**|Em alarme → OK (e-mail de recuperação)|Histórico do alarme|

!\[Histórico do alarme](docs/img/alarme-historico.png)

* **MTTD ≈ 10 minutos** no CloudWatch. É coerente com a regra: 2 períodos de 5 minutos, com a resolução de 5 minutos do monitoramento básico.
* **MTTR ≈ 1 minuto**, valor otimista: com a regra 2 de 2, basta um período abaixo de 80% para o alarme voltar a OK. A recuperação veio de um período de 5 minutos com média de 79,8%, muito perto do limite, porque o fim da carga caiu no meio dele.
* Um pico anterior, de um único período acima de 80%, **não** disparou o alarme, como previsto pela regra.
* O início da carga é uma estimativa. Os horários do alarme são exatos.



!\[E-mail de alerta](docs/img/email-alerta.png)



!\[E-mail de recuperação](docs/img/email-recuperacao.png)



Detalhes em [post-mortem do incidente](docs/post-mortem-cpu-alta.md) e no [runbook do alarme](runbooks/cpu-alta.md).

## CloudWatch x Datadog

|Critério|CloudWatch (nativo)|Datadog|
|-|-|-|
|Resolução das métricas de EC2|5 minutos (monitoramento básico)|Coleta pelo Agent em intervalos menores|
|Tempo de detecção medido (MTTD)|≈ 10 minutos|Não medido (o trial do Datadog já havia encerrado)|
|Alertas configurados|Alarme de CPU, com e-mail via SNS|Monitor de taxa de erro da aplicação, com e-mail, e monitors de host e APM|
|Métricas de memória e disco|Exigem o CloudWatch Agent|Incluídas no Agent|
|Traces de aplicação (APM)|Não faz parte deste projeto|Sim, por endpoint|
|Logs com busca|Não configurado neste projeto|Sim, com Live Tail e correlação|
|Configuração|Simples e sem instalação para métricas básicas|Exige instalar e configurar o Agent|
|Custo|Dentro dos limites gratuitos neste laboratório|Cobrado à parte, com trial de 14 dias|

O CloudWatch resolve bem o alerta básico de infraestrutura sem instalar nada. O Datadog entrega mais visibilidade da aplicação (traces e logs correlacionados), ao custo de mais configuração e de um serviço pago à parte.

## Troubleshooting

|Problema|Causa|Solução|
|-|-|-|
|Firewall da EC2 mostrava RDP|AMI do Windows selecionada|Trocar para Amazon Linux 2023|
|EC2 Instance Connect falhava|SG restrito ao meu IP; a conexão do navegador sai de IPs da AWS|SSH local com o `.pem`|
|SSH com timeout depois de dias|IP do provedor ou da EC2 mudou|Conferir meu IP, atualizar o SG e usar o IP atual da EC2|
|Flask: porta 5000/5001 em uso|O Datadog Agent usa essas portas|Usar a porta 8080|
|Flask: porta 8080 em uso|Processo antigo ficou ativo|`lsof -i :8080` e `kill -9 <PID>`|
|APM não habilitava|Indentação errada no YAML|`enabled: true` com 2 espaços sob `apm\_config:`|
|Só os erros apareciam nos logs|O `dd-agent` não atravessava `/home/ec2-user`|`chmod o+x /home/ec2-user` e reiniciar o Agent|
|Descrição do IAM com "caracteres inválidos"|O campo não aceita acentos nem `/`|Descrição sem acentos e sem barra|
|Role sem a política de S3 na criação|Caso de uso do Systems Manager selecionado, que trava a política do SSM|Voltar à Etapa 1 e escolher o caso de uso EC2 simples|
|Política anexada como "limite de permissões"|Seleção na tela errada|Anexar como política de permissões, sem limite|
|Alarme: `OKActions must not contain repeats`|Duas notificações iguais para o estado OK|Uma notificação para "Em alarme" e outra para "OK"|
|`set-alarm-state` negado na EC2|A role só tem permissão de S3 (comportamento esperado)|Rodar o comando no CloudShell com o usuário IAM|
|Cron não existe na EC2|Amazon Linux 2023 não traz o cron|`sudo dnf install -y cronie` e `systemctl enable --now crond`|
|Cron com erro de data|`%` tem significado especial no cron|Escapar com `\\%`|
|Alarme não disparou no primeiro pico|A regra exige 2 períodos seguidos acima de 80%|Manter a carga por pelo menos 10 minutos|
|Política `ReadOnlyAccess` difícil de achar|A busca traz cerca de 190 políticas com esse texto no nome|Filtrar por função de trabalho e escolher o nome exato|
|Usuário de leitura sem como ativar o próprio MFA|`ReadOnlyAccess` não permite cadastrar dispositivos MFA|O administrador atribui o dispositivo MFA ao usuário|

## Custos e governança

* Conta no **plano Free da AWS**, com créditos e prazo limitado. S3, IAM, SNS e CloudWatch consomem centavos neste laboratório.
* Alerta de custo (AWS Budgets) em US$ 5 por mês.
* O Datadog é cobrado à parte, com trial de 14 dias. O alerta de custo da AWS não cobre o Datadog.
* A EC2 é interrompida ao fim de cada sessão (nunca encerrada).
* Regra de ciclo de vida no bucket para evitar acúmulo de logs.

## Segurança

* Acesso público ao bucket bloqueado, com versionamento e criptografia ativados.
* A role da EC2 só acessa a pasta `logs/` do bucket (menor privilégio, com teste negativo).
* **MFA** ativo no usuário root e no usuário IAM administrador. A conta root não é usada no dia a dia.
* Usuário `Lab-leitura`, em um grupo com a política `ReadOnlyAccess` e MFA próprio. Testado: consegue visualizar os recursos e as ações de alteração são negadas.
* Security Group com SSH e 8080 abertos só para o meu IP.
* Nenhuma chave de acesso dentro da instância. A API Key do Datadog e o arquivo `.pem` **não** estão neste repositório (veja `.gitignore`).
* IDs de conta e endereços IP foram removidos dos prints e dos exemplos.

## Limitações e próximos passos

Limitações deste laboratório:

* Uma instância só, sem alta disponibilidade, criada pelo console.
* O usuário IAM do dia a dia (`Ester-admin`) tem permissão de administrador. Está mitigado com MFA e com um usuário de leitura separado, mas em produção eu usaria perfis por função.
* A API Key do Datadog fica em arquivo de configuração.
* CloudWatch básico, com resolução de 5 minutos, e sem métrica de memória nativa.

O que faria diferente em produção, ou como próximos passos:

* Recriar tudo com **Terraform**, para ser reprodutível.
* Monitors de CPU e de latência no Datadog, para comparar o tempo de detecção com o do CloudWatch (o trial encerrou antes do teste de CPU).
* **Secrets Manager** para a API Key do Datadog.
* **IAM Identity Center (SSO)** e permissões por perfil, no lugar de usuários IAM com senha.
* **CloudWatch Agent** para memória e disco, e um alarme de `StatusCheckFailed`.
* VPC própria com sub-redes, em vez da VPC padrão.

## Sobre o projeto

Vim de uma rotina de operação e monitoramento (NOC), em que o trabalho é reagir a alertas. Este laboratório me fez construir o outro lado: a cadeia que gera o alerta, desde a métrica, passando pelo alarme e a notificação, até a medição do tempo de detecção. Há também uma versão on-premise em outro repositório (Prometheus, Grafana, Loki e Alertmanager), e este projeto leva as mesmas ideias para a nuvem.

## Estrutura do repositório

```
.
├── README.md
├── .gitignore
├── app/
│   └── app.py
├── docs/
│   ├── gerar\_topologia.py
│   ├── post-mortem-cpu-alta.md
│   └── img/
└── runbooks/
    └── cpu-alta.md
```

