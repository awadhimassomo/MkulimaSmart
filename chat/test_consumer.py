from channels.generic.websocket import WebsocketConsumer
import json
import logging

logger = logging.getLogger(__name__)

class TestConsumer(WebsocketConsumer):
    def connect(self):
        logger.info("TestConsumer: Connection attempt received")
        try:
            self.accept()
            logger.info("TestConsumer: Connection accepted")
            # Send an immediate message to confirm connection is working
            self.send(text_data=json.dumps({
                'message': 'Connected to test WebSocket!'
            }))
        except Exception as e:
            logger.error(f"Error in connect: {str(e)}")

    def disconnect(self, close_code):
        logger.info(f"TestConsumer: Disconnected with code {close_code}")

    def receive(self, text_data):
        logger.info(f"TestConsumer: Received message: {text_data}")
        try:
            self.send(text_data=json.dumps({
                'message': 'Echo: ' + text_data
            }))
            logger.info("Message sent back to client")
        except Exception as e:
            logger.error(f"Error in receive: {str(e)}")
