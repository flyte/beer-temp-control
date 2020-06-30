import asyncio
import json
import logging
import signal as signals
from hashlib import sha256

import yaml
from hbmqtt.client import ClientException, MQTTClient
from hbmqtt.mqtt.constants import QOS_1
from jinja2 import Template

from .control import Controller

_LOG = logging.getLogger(__name__)


class Server:
    def __init__(self, config):
        self.config = config
        self.mqtt = None
        self.loop = asyncio.get_event_loop()
        self.tasks = []
        self.unawaited_tasks = []
        self.controller = None

    def _init_controller(self):
        controller_config = self.config["controller"]
        setpoint = controller_config["setpoint"]
        kp = controller_config.get("kp", 1)
        ki = controller_config.get("ki", 0.1)
        kd = controller_config.get("kd", 0.05)
        power_mult = controller_config.get("power_mult", 30)
        self.controller = Controller(setpoint, kp, ki, kd, power_mult)

    async def _init_mqtt(self):
        mqtt_config = self.config["mqtt"]
        topic_prefix = mqtt_config["topic_prefix"]
        wort_temp_topic = mqtt_config["wort_temp_topic"]
        client_id = mqtt_config.get(
            "client_id",
            "beer-temp-ctrl-%s" % sha256(wort_temp_topic.encode("utf8")).hexdigest()[:8],
        )
        uri = "mqtt://"
        username = mqtt_config.get("username")
        password = mqtt_config.get("password")
        if username and password:
            uri += f"{username}:{password}@"
        uri += f"{mqtt_config['host']}:{mqtt_config['port']}"

        client_config = {}
        status_topic = mqtt_config.get("status_topic")
        if status_topic is not None:
            client_config["will"] = dict(
                retain=True,
                topic=f"{topic_prefix}/{status_topic}",
                message=mqtt_config.get("status_payload_dead", "dead").encode("utf8"),
                qos=1,
            )
        self.mqtt = MQTTClient(client_id=client_id, config=client_config, loop=self.loop)
        await self.mqtt.connect(uri)
        if status_topic is not None:
            await self.mqtt.publish(
                f"{topic_prefix}/{status_topic}",
                mqtt_config.get("status_payload_running", "running").encode("utf8"),
                qos=1,
                retain=True,
            )
        await self.mqtt.subscribe([(mqtt_config["wort_temp_topic"], QOS_1)])

    def _handle_mqtt_msg(self, topic, payload):
        _LOG.info("Message received on topic %s: %s", topic, payload)
        mqtt_config = self.config["mqtt"]
        if topic == mqtt_config["wort_temp_topic"]:
            template = Template(
                mqtt_config.get("wort_temp_value_template", "{{ value }}")
            )
            try:
                value_json = json.loads(payload)
            except ValueError:
                value_json = None
            val = template.render(value_json=value_json, value=payload)
            self.controller.current_temp = float(val)
            _LOG.info("Wort temp set to %s", val)
        else:
            _LOG.debug("Topic didn't match anything we want to handle")

    # Tasks

    async def _controller_loop(self):
        try:
            while True:
                _LOG.info(
                    "Controller wants %s at %s power",
                    self.controller.direction,
                    self.controller.power_level,
                )
                await asyncio.sleep(10)
        except Exception as e:
            _LOG.exception("Exception in _controller_loop")
            raise

    async def _mqtt_rx_loop(self):
        try:
            while True:
                msg = await self.mqtt.deliver_message()
                topic = msg.publish_packet.variable_header.topic_name
                payload = msg.publish_packet.payload.data.decode("utf8")
                _LOG.info("Received message on topic %r: %r", topic, payload)
                try:
                    self._handle_mqtt_msg(topic, payload)
                except Exception:
                    _LOG.exception("Exception when handling MQTT message:")
        finally:
            await self.mqtt.publish(
                "%s/%s"
                % (
                    self.config["mqtt"]["topic_prefix"],
                    self.config["mqtt"]["status_topic"],
                ),
                self.config["mqtt"]
                .get("status_payload_stopped", "stopped")
                .encode("utf8"),
                qos=1,
                retain=True,
            )
            _LOG.info("Disconnecting from MQTT...")
            await self.mqtt.disconnect()
            _LOG.info("MQTT disconnected")

    async def _remove_finished_tasks(self):
        while True:
            await asyncio.sleep(1)
            finished_tasks = [x for x in self.unawaited_tasks if x.done()]
            if not finished_tasks:
                continue
            for task in finished_tasks:
                try:
                    await task
                except Exception as e:
                    _LOG.exception("Exception in task: %r:", task)
            self.unawaited_tasks = list(
                filter(lambda x: not x.done(), self.unawaited_tasks)
            )

    def run(self):
        for s in (signals.SIGHUP, signals.SIGTERM, signals.SIGINT):
            self.loop.add_signal_handler(
                s, lambda s=s: self.loop.create_task(self.shutdown(s))
            )

        _LOG.debug("Controller init")
        self._init_controller()

        # Get connected to the MQTT server
        _LOG.info("Connecting to MQTT...")
        self.loop.run_until_complete(self._init_mqtt())
        _LOG.info("MQTT connected")

        # This is where we add any other async tasks that we want to run, such as polling
        # inputs, sensor loops etc.
        self.tasks = [
            self.loop.create_task(coro)
            for coro in (
                self._controller_loop(),
                self._mqtt_rx_loop(),
                self._remove_finished_tasks(),
            )
        ]
        try:
            self.loop.run_forever()
        finally:
            self.loop.close()
            _LOG.debug("Loop closed")
        _LOG.debug("run() complete")

    async def shutdown(self, signal):
        _LOG.warning("Received exit signal %s", signal.name)

        # Cancel our main task first so we don't mess the MQTT library's connection
        for t in self.tasks:
            t.cancel()
        _LOG.info("Waiting for main task to complete...")
        all_done = False
        while not all_done:
            all_done = all(t.done() for t in self.tasks)
            await asyncio.sleep(0.1)

        current_task = asyncio.Task.current_task()
        tasks = [
            t
            for t in asyncio.Task.all_tasks(loop=self.loop)
            if not t.done() and t is not current_task
        ]
        _LOG.info("Cancelling %s remaining tasks", len(tasks))
        for t in tasks:
            t.cancel()
        _LOG.info("Waiting for %s remaining tasks to complete...", len(tasks))
        all_done = False
        while not all_done:
            all_done = all(t.done() for t in tasks)
            await asyncio.sleep(0.1)
        _LOG.debug("Tasks all finished. Stopping loop...")
        self.loop.stop()
        _LOG.debug("Loop stopped")
