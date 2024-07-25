import os
import json
import aio_pika
from dotenv import load_dotenv

load_dotenv('local.env')

class RabbitMQService:
    def __init__(self):
        self.host = os.getenv('RABBITMQ_HOST')
        self.port = int(os.getenv('RABBITMQ_PORT'))
        self.username = os.getenv('RABBITMQ_USERNAME')
        self.password = os.getenv('RABBITMQ_PASSWORD')
        self.exchange = os.getenv('RABBITMQ_EXCHANGE')
        self.routing_key = os.getenv('RABBITMQ_ROUTING_KEY')
        self.connection = None
        self.channel = None

    async def connect(self):
        self.connection = await aio_pika.connect_robust(
            f"amqp://{self.username}:{self.password}@{self.host}:{self.port}/"
        )
        self.channel = await self.connection.channel()
        await self.channel.declare_exchange(self.exchange, aio_pika.ExchangeType.TOPIC, durable=True)

    async def send_message(self, data, event):
        if not self.connection or self.connection.is_closed:
            await self.connect()
        
        message = {
            'data': data,
            'event': event
        }
        await self.channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(message).encode()),
            routing_key=self.routing_key
        )

    async def close_connection(self):
        if self.connection and not self.connection.is_closed:
            await self.connection.close()