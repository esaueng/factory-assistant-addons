"""Regression tests for MQTT and protocol availability transitions."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

ROOT = Path(os.environ.get("ADDON_SOURCE_ROOT", Path(__file__).resolve().parents[1]))


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OPCUA = load_module("opcua_bridge", "opcua-mqtt-bridge/bridge.py")
MODBUS = load_module("modbus_gateway", "plc-gateway-helper/gateway_helper.py")
MEASUREMENTS = [
    {"area": "line1", "device": "press03", "measurement": "temperature",
     "node_id": "ns=2;s=temperature", "address": 0, "function_code": 3},
    {"area": "line1", "device": "press03", "measurement": "pressure",
     "node_id": "ns=2;s=pressure", "address": 1, "function_code": 4},
]


class FakeMqtt:
    def __init__(self):
        self.retained = {}
        self.messages = []
        self.events = []
        self.will = None
        self.on_connect = None
        self.on_disconnect = None

    def will_set(self, topic, payload, qos, retain):
        self.will = (topic, payload, qos, retain)

    def connect(self, *args, **kwargs):
        self.events.append("connect")

    def loop_start(self):
        if self.on_connect is not None:
            self.on_connect(self, None, {}, 0)

    def publish(self, topic, payload, qos, retain):
        self.messages.append((topic, payload, qos, retain))
        if retain:
            self.retained[topic] = payload
        return Mock(wait_for_publish=lambda **kwargs: self.events.append("ack"))

    def disconnect(self):
        self.events.append("disconnect")
        if self.on_disconnect is not None:
            self.on_disconnect(self, None, 0)

    def loop_stop(self):
        self.events.append("loop_stop")

    def lose_connection(self):
        topic, payload, qos, retain = self.will
        self.publish(topic, payload, qos, retain)
        self.on_disconnect(self, None, 1)


def discovered_available(config, retained):
    return all(retained.get(item["topic"]) == "online" for item in config["availability"])


class PublisherTests(unittest.TestCase):
    def test_both_publishers_availability_lifecycle(self):
        for module, bridge_topic in [
            (OPCUA, "factory/test/_bridge/status"),
            (MODBUS, "factory/test/_plc_gateway/status"),
        ]:
            with self.subTest(module=module.__name__):
                mqtt = FakeMqtt()
                with patch.object(module.mqtt, "Client", return_value=mqtt):
                    publisher = module.MqttPublisher({"base_topic": "/factory/"}, "test", MEASUREMENTS)
                publisher.connect()
                for measurement in MEASUREMENTS:
                    publisher.publish_discovery(measurement)
                config = json.loads(mqtt.retained["homeassistant/sensor/line1_press03_temperature/config"])
                self.assertEqual(config["availability_mode"], "all")
                self.assertEqual(config["availability"], [
                    {"topic": bridge_topic}, {"topic": "factory/test/line1/press03/status"},
                ])
                self.assertNotIn("availability_topic", config)
                self.assertEqual(config["unique_id"], "line1_press03_temperature")
                self.assertEqual(config["object_id"], "line1_press03_temperature")
                self.assertEqual(config["device"]["identifiers"], ["line1_press03"])
                self.assertEqual(config["state_topic"], "factory/test/line1/press03/temperature")
                self.assertEqual(mqtt.will, (bridge_topic, "offline", 1, True))
                self.assertFalse(discovered_available(config, mqtt.retained))

                publisher.publish_value(MEASUREMENTS[0], 12.5)
                self.assertFalse(discovered_available(config, mqtt.retained))
                publisher.publish_value(MEASUREMENTS[1], 3)
                self.assertTrue(discovered_available(config, mqtt.retained))
                self.assertIn((config["state_topic"], "12.5", 1, False), mqtt.messages)

                # A successful sibling cannot undo the failed measurement.
                publisher.publish_unavailable(MEASUREMENTS[0])
                publisher.publish_value(MEASUREMENTS[1], 4)
                self.assertFalse(discovered_available(config, mqtt.retained))
                publisher.publish_value(MEASUREMENTS[0], 13)
                self.assertTrue(discovered_available(config, mqtt.retained))

                mqtt.lose_connection()
                self.assertFalse(discovered_available(config, mqtt.retained))
                count = len(mqtt.messages)
                publisher.publish_value(MEASUREMENTS[0], 99)
                self.assertEqual(len(mqtt.messages), count)
                mqtt.on_connect(mqtt, None, {}, 0)
                self.assertEqual(mqtt.retained[bridge_topic], "online")
                self.assertFalse(discovered_available(config, mqtt.retained))
                publisher.publish_value(MEASUREMENTS[0], 14)
                self.assertFalse(discovered_available(config, mqtt.retained))
                publisher.publish_value(MEASUREMENTS[1], 5)
                self.assertTrue(discovered_available(config, mqtt.retained))

                publisher.disconnect()
                self.assertFalse(discovered_available(config, mqtt.retained))
                self.assertEqual(mqtt.events[-3:], ["ack", "disconnect", "loop_stop"])

    def test_online_requires_successful_connack(self):
        for module in (OPCUA, MODBUS):
            with self.subTest(module=module.__name__):
                mqtt = FakeMqtt()
                mqtt.loop_start = Mock()
                with patch.object(module.mqtt, "Client", return_value=mqtt):
                    publisher = module.MqttPublisher({}, "test", MEASUREMENTS)
                publisher.connect()
                self.assertEqual(mqtt.messages, [])
                mqtt.on_connect(mqtt, None, {}, 5)
                publisher.publish_value(MEASUREMENTS[0], 1)
                self.assertEqual(mqtt.messages, [])
                mqtt.on_connect(mqtt, None, {}, 0)
                self.assertTrue(mqtt.messages)

    def test_devices_are_independent_when_discovery_is_disabled(self):
        other = dict(MEASUREMENTS[0], device="press04")
        for module in (OPCUA, MODBUS):
            with self.subTest(module=module.__name__):
                mqtt = FakeMqtt()
                with patch.object(module.mqtt, "Client", return_value=mqtt):
                    publisher = module.MqttPublisher({"discovery": False}, "test", [*MEASUREMENTS, other])
                publisher.connect()
                publisher.publish_discovery(other)
                publisher.publish_value(other, 1)
                self.assertEqual(mqtt.retained[publisher.status_topic(other)], "online")
                self.assertEqual(mqtt.retained[publisher.status_topic(MEASUREMENTS[0])], "offline")
                self.assertFalse(any(topic.startswith("homeassistant/") for topic in mqtt.retained))


class PollingTests(unittest.TestCase):
    def test_modbus_reconnect_failure_invalidates_all_devices(self):
        for connect_result in (False, OSError("connection refused")):
            with self.subTest(connect_result=repr(connect_result)):
                other = dict(MEASUREMENTS[0], device="press04")
                registers = [*MEASUREMENTS, other]
                mqtt = FakeMqtt()
                client = Mock(connected=True)
                client.connect.side_effect = [connect_result]
                stop = {}
                sleeps = 0

                def on_sleep(interval):
                    nonlocal sleeps
                    sleeps += 1
                    expected = "online" if sleeps == 1 else "offline"
                    for device in ("press03", "press04"):
                        self.assertEqual(mqtt.retained[f"fa/test/line1/{device}/status"], expected)
                    if sleeps == 1:
                        client.connected = False
                    else:
                        stop["handler"]()

                options = {"site": "test", "mqtt": {}, "registers": registers,
                           "modbus": {"host": "plc", "allowed_function_codes": [3, 4],
                                      "write_functions_allowed": False, "safety_controller_allowed": False}}
                with patch.object(MODBUS.mqtt, "Client", return_value=mqtt), \
                     patch.object(MODBUS, "ModbusTcpClient", return_value=client), \
                     patch.object(MODBUS, "read_register", return_value=12), \
                     patch.object(MODBUS.signal, "signal", side_effect=lambda sig, handler: stop.update(handler=handler)), \
                     patch.object(MODBUS.time, "sleep", side_effect=on_sleep):
                    MODBUS.run(options)
                self.assertEqual(sleeps, 2)
                client.close.assert_called_once()
                self.assertEqual(mqtt.retained["fa/test/_plc_gateway/status"], "offline")

    def test_opcua_mixed_reads_remain_offline_and_cleanup_on_connection_error(self):
        async def exercise(fail_connect):
            mqtt = FakeMqtt()
            stop = {}

            class UaNode:
                def __init__(self, node_id):
                    self.node_id = node_id

                async def get_value(self):
                    if "temperature" in self.node_id:
                        raise OSError("read failed")
                    stop["handler"]()
                    return 3

            class UaClient:
                async def __aenter__(self):
                    if fail_connect:
                        raise OSError("connection refused")
                    return self

                async def __aexit__(self, *args):
                    return False

                def get_node(self, node_id):
                    return UaNode(node_id)

            options = {"site": "test", "mqtt": {}, "nodes": MEASUREMENTS,
                       "opcua": {"endpoint": "opc.tcp://plc", "write_nodes_allowed": False}}
            with patch.object(OPCUA.mqtt, "Client", return_value=mqtt), \
                 patch.object(OPCUA, "Client", return_value=UaClient()), \
                 patch.object(asyncio.get_running_loop(), "add_signal_handler",
                              side_effect=lambda sig, handler: stop.update(handler=handler)):
                if fail_connect:
                    with self.assertRaisesRegex(OSError, "connection refused"):
                        await OPCUA.run(options)
                else:
                    await OPCUA.run(options)
            statuses = [payload for topic, payload, _, _ in mqtt.messages
                        if topic == "fa/test/line1/press03/status"]
            self.assertTrue(statuses)
            self.assertNotIn("online", statuses)
            self.assertEqual(mqtt.retained["fa/test/_bridge/status"], "offline")
            self.assertEqual(mqtt.events[-3:], ["ack", "disconnect", "loop_stop"])

        for fail_connect in (False, True):
            with self.subTest(fail_connect=fail_connect):
                asyncio.run(exercise(fail_connect))


if __name__ == "__main__":
    unittest.main()
