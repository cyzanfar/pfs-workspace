import unittest
from unittest.mock import Mock, patch
import time
import json
from datetime import datetime
from message_broker import (
    MessageBroker,
    DeliveryGuarantee,
    MessageStatus,
    Message
)


class TestMessageBroker(unittest.TestCase):
    def setUp(self):
        self.broker = MessageBroker()
        self.test_topic = "test_topic"

    def test_topic_management(self):
        # Test topic creation
        self.broker.create_topic(self.test_topic)
        self.assertIn(self.test_topic, self.broker.topics)

        # Test duplicate topic creation
        with self.assertRaises(ValueError):
            self.broker.create_topic(self.test_topic)

        # Test topic deletion
        self.broker.delete_topic(self.test_topic)
        self.assertNotIn(self.test_topic, self.broker.topics)

    def test_subscription(self):
        self.broker.create_topic(self.test_topic)
        callback = Mock()

        # Test subscription creation
        sub_id = self.broker.subscribe(self.test_topic, callback)
        self.assertEqual(len(self.broker.topics[self.test_topic]), 1)

        # Test unsubscribe
        self.broker.unsubscribe(sub_id)
        self.assertEqual(len(self.broker.topics[self.test_topic]), 0)

    def test_message_delivery(self):
        self.broker.create_topic(self.test_topic)
        received_messages = []

        def callback(payload):
            received_messages.append(payload)

        self.broker.subscribe(self.test_topic, callback)

        # Test message publication
        test_payload = {"test": "data"}
        message_id = self.broker.publish(self.test_topic, test_payload)

        # Allow time for delivery
        time.sleep(0.1)

        self.assertEqual(len(received_messages), 1)
        self.assertEqual(received_messages[0], test_payload)

        # Verify message status
        status = self.broker.get_message_status(message_id)
        self.assertEqual(status['status'], MessageStatus.DELIVERED.value)

    def test_filtered_subscription(self):
        self.broker.create_topic(self.test_topic)
        received_messages = []

        def callback(payload):
            received_messages.append(payload)

        # Subscribe with filter
        self.broker.subscribe(
            self.test_topic,
            callback,
            filter_pattern="important"
        )

        # Test filtered messages
        self.broker.publish(self.test_topic, "important message")
        self.broker.publish(self.test_topic, "unimportant message")

        # Allow time for delivery
        time.sleep(0.1)

        self.assertEqual(len(received_messages), 1)
        self.assertEqual(received_messages[0], "important message")

    def test_exactly_once_delivery(self):
        self.broker.create_topic(self.test_topic)
        callback = Mock()

        self.broker.subscribe(self.test_topic, callback)

        # Publish with exactly-once guarantee
        message_id = self.broker.publish(
            self.test_topic,
            "test message",
            delivery_guarantee=DeliveryGuarantee.EXACTLY_ONCEx
        )

        # Allow time for delivery
        time.sleep(0.1)

        # Verify callback called once
        callback.assert_called_once_with("test message")