from typing import Dict, List, Set, Callable, Optional, Any
import threading
import queue
import logging
import json
import uuid
import time
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import argparse
import re


class DeliveryGuarantee(Enum):
    AT_LEAST_ONCE = "at_least_once"
    AT_MOST_ONCE = "at_most_once"
    EXACTLY_ONCE = "exactly_once"


class MessageStatus(Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    ACKNOWLEDGED = "acknowledged"


@dataclass
class Message:
    id: str
    topic: str
    payload: Any
    timestamp: datetime
    delivery_guarantee: DeliveryGuarantee
    status: MessageStatus = MessageStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class Subscription:
    id: str
    topic: str
    callback: Callable
    filter_pattern: Optional[str] = None


class BrokerMetrics:
    def __init__(self):
        self.messages_published = 0
        self.messages_delivered = 0
        self.messages_failed = 0
        self.active_subscribers = 0
        self.message_latency: List[float] = []
        self.retry_counts: Dict[str, int] = {}

    def record_message(self, message: Message, latency: float = 0.0):
        if message.status == MessageStatus.DELIVERED:
            self.messages_delivered += 1
        elif message.status == MessageStatus.FAILED:
            self.messages_failed += 1

        if message.retry_count > 0:
            self.retry_counts[message.id] = message.retry_count

        if latency > 0:
            self.message_latency.append(latency)


class MessageBroker:
    def __init__(self):
        self.topics: Dict[str, Set[Subscription]] = {}
        self.messages: Dict[str, Message] = {}
        self.message_queue = queue.PriorityQueue()
        self.metrics = BrokerMetrics()
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

        # Start worker threads
        self.worker_thread = threading.Thread(target=self._message_worker)
        self.worker_thread.daemon = True
        self.worker_thread.start()

        self._setup_logging()

    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[
                logging.FileHandler('broker.log'),
                logging.StreamHandler()
            ]
        )

    def create_topic(self, topic: str) -> bool:
        """Create a new topic."""
        with self.lock:
            if topic in self.topics:
                raise ValueError(f"Topic {topic} already exists")

            self.topics[topic] = set()
            self.logger.info(f"Created topic: {topic}")
            return True

    def delete_topic(self, topic: str) -> bool:
        """Delete a topic and all its subscriptions."""
        with self.lock:
            if topic not in self.topics:
                raise ValueError(f"Topic {topic} does not exist")

            del self.topics[topic]
            self.logger.info(f"Deleted topic: {topic}")
            return True

    def subscribe(self, topic: str, callback: Callable,
                  filter_pattern: Optional[str] = None) -> str:
        """Subscribe to a topic with optional message filtering."""
        with self.lock:
            if topic not in self.topics:
                raise ValueError(f"Topic {topic} does not exist")

            subscription_id = str(uuid.uuid4())
            subscription = Subscription(
                id=subscription_id,
                topic=topic,
                callback=callback,
                filter_pattern=filter_pattern
            )

            self.topics[topic].add(subscription)
            self.metrics.active_subscribers += 1
            self.logger.info(f"New subscription to topic {topic}: {subscription_id}")

            return subscription_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from a topic."""
        with self.lock:
            for topic, subscriptions in self.topics.items():
                for subscription in subscriptions:
                    if subscription.id == subscription_id:
                        subscriptions.remove(subscription)
                        self.metrics.active_subscribers -= 1
                        self.logger.info(f"Removed subscription: {subscription_id}")
                        return True

            raise ValueError(f"Subscription {subscription_id} not found")

    def publish(self, topic: str, payload: Any,
                delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_LEAST_ONCE) -> str:
        """Publish a message to a topic."""
        with self.lock:
            if topic not in self.topics:
                raise ValueError(f"Topic {topic} does not exist")

            message_id = str(uuid.uuid4())
            message = Message(
                id=message_id,
                topic=topic,
                payload=payload,
                timestamp=datetime.now(),
                delivery_guarantee=delivery_guarantee
            )

            self.messages[message_id] = message
            self.message_queue.put((message.timestamp.timestamp(), message_id))
            self.metrics.messages_published += 1

            self.logger.info(f"Published message to topic {topic}: {message_id}")
            return message_id

    def _message_worker(self):
        """Background worker for processing messages."""
        while True:
            try:
                _, message_id = self.message_queue.get()
                message = self.messages[message_id]

                if message.status == MessageStatus.DELIVERED:
                    continue

                start_time = time.time()
                success = self._deliver_message(message)
                latency = time.time() - start_time

                if success:
                    message.status = MessageStatus.DELIVERED
                    self.metrics.record_message(message, latency)
                else:
                    message.retry_count += 1
                    if message.retry_count < message.max_retries:
                        self.message_queue.put((time.time(), message_id))
                    else:
                        message.status = MessageStatus.FAILED
                        self.metrics.record_message(message)
                        self.logger.error(f"Message delivery failed after retries: {message_id}")

            except Exception as e:
                self.logger.error(f"Error in message worker: {str(e)}")
                continue

    def _deliver_message(self, message: Message) -> bool:
        """Deliver message to all matching subscribers."""
        if message.topic not in self.topics:
            return False

        delivered = False
        for subscription in self.topics[message.topic]:
            try:
                if subscription.filter_pattern:
                    if not re.search(subscription.filter_pattern, str(message.payload)):
                        continue

                subscription.callback(message.payload)
                delivered = True

            except Exception as e:
                self.logger.error(f"Error delivering to subscription {subscription.id}: {str(e)}")
                continue

        return delivered

    def acknowledge_message(self, message_id: str):
        """Acknowledge message delivery for exactly-once delivery."""
        if message_id not in self.messages:
            raise ValueError(f"Message {message_id} not found")

        message = self.messages[message_id]
        if message.delivery_guarantee == DeliveryGuarantee.EXACTLY_ONCE:
            message.status = MessageStatus.ACKNOWLEDGED
            self.logger.info(f"Message acknowledged: {message_id}")

    def get_message_status(self, message_id: str) -> Dict:
        """Get status of a specific message."""
        if message_id not in self.messages:
            raise ValueError(f"Message {message_id} not found")

        message = self.messages[message_id]
        return {
            'id': message.id,
            'topic': message.topic,
            'timestamp': message.timestamp.isoformat(),
            'status': message.status.value,
            'retry_count': message.retry_count,
            'delivery_guarantee': message.delivery_guarantee.value
        }

    def list_topics(self) -> List[Dict]:
        """List all topics and their subscription counts."""
        return [
            {
                'name': topic,
                'subscribers': len(subscriptions)
            }
            for topic, subscriptions in self.topics.items()
        ]

    def get_metrics(self) -> Dict:
        """Get broker metrics."""
        avg_latency = (
            sum(self.metrics.message_latency) / len(self.metrics.message_latency)
            if self.metrics.message_latency else 0
        )

        return {
            'messages_published': self.metrics.messages_published,
            'messages_delivered': self.metrics.messages_delivered,
            'messages_failed': self.metrics.messages_failed,
            'active_subscribers': self.metrics.active_subscribers,
            'average_latency': avg_latency,
            'retry_counts': self.metrics.retry_counts
        }


def main():
    """CLI entry point for the MessageBroker."""
    parser = argparse.ArgumentParser(description='Message Broker CLI')
    parser.add_argument('command', choices=['create-topic', 'delete-topic', 'list-topics',
                                            'message-status', 'metrics'])
    parser.add_argument('--topic', help='Topic name')
    parser.add_argument('--message-id', help='Message ID')
    args = parser.parse_args()

    broker = MessageBroker()

    try:
        if args.command == 'create-topic' and args.topic:
            broker.create_topic(args.topic)
            print(json.dumps({'message': f'Created topic: {args.topic}'}, indent=2))

        elif args.command == 'delete-topic' and args.topic:
            broker.delete_topic(args.topic)
            print(json.dumps({'message': f'Deleted topic: {args.topic}'}, indent=2))

        elif args.command == 'list-topics':
            topics = broker.list_topics()
            print(json.dumps({'topics': topics}, indent=2))

        elif args.command == 'message-status' and args.message_id:
            status = broker.get_message_status(args.message_id)
            print(json.dumps(status, indent=2))

        elif args.command == 'metrics':
            print(json.dumps(broker.get_metrics(), indent=2))

    except Exception as e:
        print(json.dumps({'error': str(e)}, indent=2))
        exit(1)


if __name__ == '__main__':
    main()