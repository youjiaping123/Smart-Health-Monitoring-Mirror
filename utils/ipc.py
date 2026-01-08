import json
import zmq


class ZmqPublisher:
    """ZeroMQ Publisher for inter-process communication"""

    def __init__(self, endpoint):
        self._ctx = zmq.Context.instance()
        self._socket = self._ctx.socket(zmq.PUB)
        self._socket.bind(endpoint)

    def publish(self, topic, payload):
        """Publish message with topic and payload"""
        msg = {"topic": topic, "payload": payload}
        self._socket.send_string(json.dumps(msg))

    def close(self):
        self._socket.close(linger=0)


class ZmqSubscriber:
    """ZeroMQ Subscriber for inter-process communication"""

    def __init__(self, endpoint, topics=None):
        self._ctx = zmq.Context.instance()
        self._socket = self._ctx.socket(zmq.SUB)
        self._socket.connect(endpoint)
        if not topics:
            self._socket.setsockopt_string(zmq.SUBSCRIBE, "")
        else:
            for topic in topics:
                self._socket.setsockopt_string(zmq.SUBSCRIBE, topic)

    def recv(self, timeout_ms=None):
        """Receive message with optional timeout"""
        if timeout_ms is not None:
            poller = zmq.Poller()
            poller.register(self._socket, zmq.POLLIN)
            items = dict(poller.poll(timeout_ms))
            if self._socket not in items:
                return None
        data = self._socket.recv_string()
        return json.loads(data)

    def close(self):
        self._socket.close(linger=0)
