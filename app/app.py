from flask import Flask, jsonify
import random
import time
import logging

app = Flask(__name__)

# Configurar logging para gravar em arquivo
logging.basicConfig(
    filename='/home/ec2-user/app-monitorada/app.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s'
)
logger = logging.getLogger(__name__)

@app.route('/')
def home():
    logger.info("Endpoint / acessado")
    return "Aplicação de monitoramento está no ar! 🚀"

@app.route('/status')
def status():
    logger.info("Endpoint /status acessado")
    return jsonify({
        "status": "ok",
        "service": "app-monitorada",
        "version": "1.0"
    })

@app.route('/lenta')
def lenta():
    delay = random.uniform(0.5, 2.5)
    logger.warning(f"Endpoint /lenta acessado, delay de {delay:.2f}s")
    time.sleep(delay)
    return jsonify({"message": f"Resposta lenta de propósito, demorou {delay:.2f}s"})

@app.route('/erro')
def erro():
    logger.error("Endpoint /erro acessado - erro simulado sendo gerado")
    raise Exception("Erro simulado para teste de monitoramento")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
