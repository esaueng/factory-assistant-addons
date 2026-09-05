"""Exercise MQTT Last Will and reconnect behavior against a local Mosquitto."""
from __future__ import annotations

import json
import os
import select
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import unittest

import paho.mqtt.client as mqtt

from test_availability import MEASUREMENTS, MODBUS, OPCUA

MOSQUITTO = os.environ.get("MOSQUITTO_BIN") or shutil.which("mosquitto")


class WithheldPubackProxy:
    """Forward MQTT but withhold first-connection PUBACKs to force retransmission."""

    def __init__(self, broker_port):
        self.broker_port = broker_port
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.listener.settimeout(0.1)
        self.port = self.listener.getsockname()[1]
        self.stopping = threading.Event()
        self.drop = threading.Event()
        self.reconnected = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def close(self):
        self.stopping.set()
        self.thread.join(timeout=5)
        self.listener.close()
        if self.thread.is_alive():
            raise RuntimeError("MQTT proxy did not stop")

    def run(self):
        connections = 0
        while not self.stopping.is_set():
            try:
                client, _ = self.listener.accept()
            except socket.timeout:
                continue
            connections += 1
            with client, socket.create_connection(("127.0.0.1", self.broker_port)) as upstream:
                self.drop.clear()
                if connections > 1:
                    self.reconnected.set()
                buffered = b""
                while not self.stopping.is_set() and not self.drop.is_set():
                    try:
                        readable, _, _ = select.select([client, upstream], [], [], 0.05)
                        closed = False
                        for source in readable:
                            data = source.recv(65536)
                            if not data:
                                closed = True
                                break
                            if source is client:
                                upstream.sendall(data)
                                continue
                            buffered += data
                            while len(buffered) >= 2:
                                remaining = 0
                                multiplier = 1
                                offset = 1
                                while offset < len(buffered):
                                    byte = buffered[offset]
                                    remaining += (byte & 127) * multiplier
                                    offset += 1
                                    if byte < 128:
                                        break
                                    multiplier *= 128
                                else:
                                    break
                                size = offset + remaining
                                if len(buffered) < size:
                                    break
                                packet, buffered = buffered[:size], buffered[size:]
                                if connections > 1 or packet[0] >> 4 != 4:
                                    client.sendall(packet)
                        if closed:
                            break
                    except OSError:
                        break


@unittest.skipUnless(MOSQUITTO, "install mosquitto or set MOSQUITTO_BIN for broker tests")
class BrokerTests(unittest.TestCase):
    def setUp(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        self.broker = subprocess.Popen(
            [MOSQUITTO, "-p", str(self.port)], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(self.stop_broker)
        self.wait_for(self.broker_ready)
        self.messages = []
        self.condition = threading.Condition()
        self.observer = mqtt.Client(client_id="availability-test-observer")
        self.observer.on_connect = lambda client, *_: client.subscribe("#", qos=1)

        def receive(client, userdata, message):
            with self.condition:
                self.messages.append((message.topic, message.payload.decode()))
                self.condition.notify_all()

        subscribed = threading.Event()
        self.observer.on_subscribe = lambda *_: subscribed.set()
        self.observer.on_message = receive
        self.observer.connect("127.0.0.1", self.port)
        self.observer.loop_start()
        self.addCleanup(self.stop_observer)
        self.assertTrue(subscribed.wait(5))

    def stop_broker(self):
        self.broker.terminate()
        self.broker.wait(timeout=5)

    def stop_observer(self):
        self.observer.disconnect()
        self.observer.loop_stop()

    def broker_ready(self):
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=0.1):
                return True
        except OSError:
            return False

    def wait_for(self, predicate):
        deadline = time.monotonic() + 10
        while not predicate():
            if time.monotonic() > deadline:
                self.fail("Timed out waiting for MQTT transition")
            time.sleep(0.01)

    def wait_message(self, topic, payload, start=0):
        with self.condition:
            self.assertTrue(self.condition.wait_for(
                lambda: (topic, payload) in self.messages[start:], timeout=10,
            ), f"Missing {topic}={payload}")

    def test_disconnect_reconnect_requires_new_samples(self):
        for module, bridge in [(OPCUA, "_bridge"), (MODBUS, "_plc_gateway")]:
            with self.subTest(module=module.__name__):
                publisher = module.MqttPublisher(
                    {"host": "127.0.0.1", "port": self.port}, "reconnect", MEASUREMENTS,
                )
                publisher.connect()
                try:
                    bridge_topic = f"fa/reconnect/{bridge}/status"
                    device_topic = "fa/reconnect/line1/press03/status"
                    self.wait_message(bridge_topic, "online")
                    for item in MEASUREMENTS:
                        publisher.publish_value(item, 1)
                    self.wait_message(device_topic, "online")
                    start = len(self.messages)
                    publisher._client.socket().shutdown(socket.SHUT_RDWR)
                    self.wait_message(bridge_topic, "offline", start)
                    self.wait_message(bridge_topic, "online", start)
                    with self.condition:
                        latest = dict(self.messages)
                    self.assertEqual(latest[device_topic], "offline")
                    publisher.publish_value(MEASUREMENTS[0], 2)
                    start = len(self.messages)
                    self.wait_message(device_topic, "offline", start - 1)
                    with self.condition:
                        self.assertEqual(dict(self.messages)[device_topic], "offline")
                    publisher.publish_value(MEASUREMENTS[1], 3)
                    self.wait_message(device_topic, "online", start)
                    start = len(self.messages)
                    publisher.disconnect()
                    self.wait_message(bridge_topic, "offline", start)
                finally:
                    publisher.disconnect()

    def test_unacknowledged_status_cannot_restore_online_after_reconnect(self):
        for module, bridge in [(OPCUA, "_bridge"), (MODBUS, "_plc_gateway")]:
            with self.subTest(module=module.__name__):
                proxy = WithheldPubackProxy(self.port)
                publisher = module.MqttPublisher(
                    {"host": "127.0.0.1", "port": proxy.port}, "unacked", MEASUREMENTS,
                )
                start = len(self.messages)
                publisher.connect()
                try:
                    bridge_topic = f"fa/unacked/{bridge}/status"
                    device_topic = "fa/unacked/line1/press03/status"
                    self.wait_message(bridge_topic, "online", start)
                    for item in MEASUREMENTS:
                        publisher.publish_value(item, 1)
                    self.wait_message(device_topic, "online", start)
                    # The broker delivered online, but its PUBACK cannot reach Paho.
                    start = len(self.messages)
                    proxy.drop.set()
                    self.wait_message(bridge_topic, "offline", start)
                    self.assertTrue(proxy.reconnected.wait(10))
                    self.wait_message(bridge_topic, "online", start)
                    # Drain retransmitted state messages through a broker round-trip.
                    marker = publisher._client.publish("test/drained", "marker", qos=1)
                    marker.wait_for_publish(timeout=5)
                    self.wait_message("test/drained", "marker", start)
                    with self.condition:
                        self.assertEqual(dict(self.messages)[device_topic], "offline")
                        self.assertNotIn((device_topic, "online"), self.messages[start:])
                    publisher.publish_value(MEASUREMENTS[0], 2)
                    publisher.publish_value(MEASUREMENTS[1], 3)
                    self.wait_message(device_topic, "online", start)
                finally:
                    publisher.disconnect()
                    proxy.close()

    def test_killed_publisher_marks_discovered_entities_unavailable(self):
        script = '''
import sys, time
sys.path.insert(0, sys.argv[1])
from test_availability import OPCUA, MODBUS, MEASUREMENTS
module = OPCUA if sys.argv[2] == "opcua" else MODBUS
publisher = module.MqttPublisher({"host": "127.0.0.1", "port": int(sys.argv[3])}, "killed", MEASUREMENTS)
publisher.connect()
while not publisher._client.is_connected():
    time.sleep(0.01)
for item in MEASUREMENTS:
    publisher.publish_discovery(item)
    publisher.publish_value(item, 1)
while True:
    time.sleep(1)
'''
        for name, bridge in [("opcua", "_bridge"), ("modbus", "_plc_gateway")]:
            with self.subTest(publisher=name):
                child = subprocess.Popen([
                    sys.executable, "-c", script, str(Path(__file__).parent), name, str(self.port),
                ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                try:
                    bridge_topic = f"fa/killed/{bridge}/status"
                    device_topic = "fa/killed/line1/press03/status"
                    start = len(self.messages)
                    self.wait_message(bridge_topic, "online", start)
                    self.wait_message(device_topic, "online", start)
                    config_topic = "homeassistant/sensor/line1_press03_temperature/config"
                    with self.condition:
                        config = json.loads(dict(self.messages)[config_topic])
                    self.assertEqual(config["availability_mode"], "all")
                    self.assertIn({"topic": bridge_topic}, config["availability"])
                    start = len(self.messages)
                    child.kill()
                    child.wait(timeout=5)
                    self.wait_message(bridge_topic, "offline", start)
                    with self.condition:
                        latest = dict(self.messages)
                    self.assertEqual(latest[device_topic], "online")
                    self.assertFalse(all(latest.get(item["topic"]) == "online"
                                         for item in config["availability"]))
                finally:
                    if child.poll() is None:
                        child.kill()
                        child.wait(timeout=5)
                    child.stderr.close()


if __name__ == "__main__":
    unittest.main()
