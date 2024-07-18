import os
import pika
import json
from dotenv import load_dotenv

load_dotenv('local.env')

class RabbitMQService:
    def __init__(self):
        self.host = os.getenv('RABBITMQ_HOST')
        self.port = int(os.getenv('RABBITMQ_PORT'))
        self.username = os.getenv('RABBITMQ_USERNAME')
        self.password = os.getenv('RABBITMQ_PASSWORD')
        self.exchange = os.getenv('RABBITMQ_EXCHANGE')

        credentials = pika.PlainCredentials(self.username, self.password)
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.host, port=self.port, credentials=credentials))
        self.channel = self.connection.channel()
        self.channel.exchange_declare(exchange=self.exchange, exchange_type='topic')

    def send_message(self, data, event):
        message = {
            'data': data,
            'event': event
        }
        self.channel.basic_publish(exchange=self.exchange, body=json.dumps(message))

    def close_connection(self):
        self.connection.close()