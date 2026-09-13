import socket
import struct
import unittest

from turbodash.protocol import (
    ActionSpace, DiscreteAction, Handshake, Message, ProtocolError, encode_step,
)
from turbodash.transport import receive_frame, send_frame


class ProtocolTests(unittest.TestCase):
    def test_handshake_success_and_mismatch_rejection(self):
        hello = Handshake(1, 1, 2, 236, ActionSpace.DISCRETE, 0.01, 0.05, 3)
        hello.validate(3, ActionSpace.DISCRETE)
        with self.assertRaises(ProtocolError):
            hello.validate(4, ActionSpace.DISCRETE)

    def test_discrete_wire_mapping(self):
        self.assertEqual(struct.unpack("<Bi", encode_step(DiscreteAction.LEFT, ActionSpace.DISCRETE)), (Message.STEP, 0))
        self.assertEqual(struct.unpack("<Bi", encode_step(DiscreteAction.NONE, ActionSpace.DISCRETE)), (Message.STEP, 1))
        self.assertEqual(struct.unpack("<Bi", encode_step(DiscreteAction.RIGHT, ActionSpace.DISCRETE)), (Message.STEP, 2))

    def test_length_prefixed_transport(self):
        left, right = socket.socketpair()
        try:
            payload = bytes(range(128))
            send_frame(left, payload)
            self.assertEqual(receive_frame(right), payload)
        finally:
            left.close()
            right.close()


if __name__ == "__main__":
    unittest.main()
