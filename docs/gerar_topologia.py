from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.storage import S3
from diagrams.aws.security import IAMRole
from diagrams.aws.integration import SNS
from diagrams.aws.management import Cloudwatch, CloudwatchAlarm
from diagrams.aws.cost import Budgets
from diagrams.aws.devtools import CommandLineInterface
from diagrams.aws.general import User
from diagrams.onprem.client import Client
from diagrams.onprem.monitoring import Datadog
from diagrams.programming.framework import Flask

FONT = "DejaVu Sans"

graph_attr = {
    "fontname": FONT,
    "fontsize": "26",
    "labelloc": "t",
    "pad": "0.5",
    "nodesep": "0.9",
    "ranksep": "1.5",
    "bgcolor": "white",
    "dpi": "150",
    "splines": "spline",
}
node_attr = {"fontname": FONT, "fontsize": "13"}
edge_attr = {"fontname": FONT, "fontsize": "12", "color": "#4a4a4a", "penwidth": "1.6"}


def cluster_attr(label, fill, border, size="16"):
    return {
        "label": label,
        "fontname": FONT,
        "fontsize": size,
        "style": "rounded,filled",
        "bgcolor": fill,
        "pencolor": border,
        "penwidth": "1.8",
        "labeljust": "l",
        "margin": "22",
    }


with Diagram(
    "Laboratório de observabilidade AWS + Datadog",
    filename="docs/img/topologia_lab_observabilidade",
    outformat=["png", "svg"],
    show=False,
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    with Cluster("Fora da AWS", graph_attr=cluster_attr("Ambiente local", "#F1F1EC", "#8a8a80")):
        pc = Client("Seu PC (Windows)\nSSH 22 e HTTP 8080")

    with Cluster("AWS", graph_attr=cluster_attr("AWS Cloud  ·  região us-east-2 (Ohio)", "#EAF6F2", "#1D9E75", "20")):
        with Cluster("sg", graph_attr=cluster_attr("Security Group: SSH e 8080 só do seu IP", "#FFFFFF", "#B4B2A9", "14")):
            with Cluster("ec2", graph_attr=cluster_attr("EC2 t3.micro  ·  Amazon Linux 2023", "#F7FBF9", "#1D9E75", "15")):
                ec2 = EC2("Instância\nLab-Monitoramento EC2")
                app = Flask("App Flask\nporta 8080 + ddtrace")
                cron = CommandLineInterface("Cron + AWS CLI\nenvia app.log (1 h)")
                agent = Datadog("Datadog Agent 7\nmétricas, APM e logs")

        role = IAMRole("Role IAM\nLab-EC2-S3-Role")
        bucket = S3("Bucket S3\nlogs/ · expira em 30 dias")

        cw = Cloudwatch("CloudWatch\nCPUUtilization (5 min)")
        alarm = CloudwatchAlarm("Alarme Lab-EC2-CPU-Alta\nCPU > 80%, 2 de 2 pontos")
        sns = SNS("SNS\ntópico Lab-Alertas")

        budget = Budgets("AWS Budgets\nalerta em US$ 5 por mês")

    email = User("Você (e-mail)\nalarme e recuperação")

    with Cluster("Datadog", graph_attr={**cluster_attr("Datadog  ·  datadoghq.com", "#EFEDFB", "#534AB7", "20"), "margin": "45"}):
        dd = Datadog("Plataforma\nmétricas · APM · logs")
        dash = Datadog("Dashboard e monitor\nde taxa de erro")

    pc >> Edge(label="SSH / HTTP", color="#185FA5") >> ec2

    app >> Edge(label="app.log", style="dashed", color="#888780") >> cron
    app >> Edge(label="traces e logs", style="dashed", color="#888780") >> agent

    cron >> Edge(label="credenciais\ntemporárias", color="#0F6E56") >> role
    role >> Edge(label="PutObject\nem logs/", color="#0F6E56") >> bucket

    ec2 >> Edge(label="métrica de CPU", color="#BA7517") >> cw
    cw >> Edge(color="#BA7517") >> alarm
    alarm >> Edge(label="Em alarme / OK", color="#BA7517") >> sns
    sns >> Edge(label="e-mail", color="#BA7517") >> email

    agent >> Edge(label="HTTPS", color="#534AB7") >> dd
    dd >> Edge(color="#534AB7") >> dash

    budget
