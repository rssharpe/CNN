"""Small helpers for the ATO load-cell amplifier's Modbus RTU data."""


def modbus_crc16(data):
    """Return the Modbus RTU CRC-16 value for a byte sequence."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def has_valid_modbus_crc(frame):
    """Check a complete RTU frame whose CRC is transmitted low byte first."""
    if len(frame) < 4:
        return False
    expected_crc = modbus_crc16(frame[:-2])
    return frame[-2:] == bytes((expected_crc & 0xFF, expected_crc >> 8))


def build_net_weight_request(slave_id):
    """Build a function-03 request for the signed net-weight value at register 0."""
    if type(slave_id) is not int or not 1 <= slave_id <= 128:
        raise ValueError('Slave ID must be an integer from 1 through 128')
    request = bytes((slave_id, 0x03, 0x00, 0x00, 0x00, 0x02))
    crc = modbus_crc16(request)
    return request + bytes((crc & 0xFF, crc >> 8))


def parse_net_weight_response(frame, slave_id):
    """Validate a two-register response and return its signed 32-bit value."""
    if len(frame) != 9:
        raise ValueError('Net-weight response must be exactly 9 bytes')
    if frame[0] != slave_id:
        raise ValueError('Response slave ID does not match the request')
    if frame[1] != 0x03:
        raise ValueError('Response is not a function-03 read response')
    if frame[2] != 4:
        raise ValueError('Response must contain exactly two registers')
    if not has_valid_modbus_crc(frame):
        raise ValueError('Response CRC is invalid')

    value = int.from_bytes(frame[3:7], byteorder='big', signed=True)
    return value
