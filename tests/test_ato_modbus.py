import unittest

from ato_modbus import (
    build_net_weight_request,
    has_valid_modbus_crc,
    modbus_crc16,
    parse_net_weight_response,
)


class AtoModbusTests(unittest.TestCase):
    def test_builds_read_request_with_little_endian_crc(self):
        request = build_net_weight_request(1)

        self.assertEqual(request, bytes((1, 3, 0, 0, 0, 2, 0xC4, 0x0B)))
        self.assertTrue(has_valid_modbus_crc(request))

    def test_rejects_invalid_slave_id(self):
        for slave_id in (0, 129, True, 1.0):
            with self.subTest(slave_id=slave_id):
                with self.assertRaises(ValueError):
                    build_net_weight_request(slave_id)

    def test_decodes_positive_and_negative_net_weight(self):
        for raw_value in (123456, -123456):
            with self.subTest(raw_value=raw_value):
                payload = (
                    bytes((1, 3, 4))
                    + raw_value.to_bytes(4, byteorder='big', signed=True)
                )
                crc = modbus_crc16(payload)
                response = payload + bytes((crc & 0xFF, crc >> 8))

                self.assertEqual(parse_net_weight_response(response, 1), raw_value)

    def test_rejects_wrong_slave_or_bad_crc(self):
        payload = bytes((1, 3, 4, 0, 0, 0, 1))
        crc = modbus_crc16(payload)
        response = payload + bytes((crc & 0xFF, crc >> 8))

        with self.assertRaisesRegex(ValueError, 'slave ID'):
            parse_net_weight_response(response, 2)
        with self.assertRaisesRegex(ValueError, 'CRC'):
            parse_net_weight_response(response[:-1] + b'\x00', 1)


if __name__ == '__main__':
    unittest.main()
