import unittest
import socket
from datetime import datetime
from pathlib import Path

import iso8583_common as common
import rules_engine as rules
import tcp_framing


ASCII_SPEC = common.load_spec("specs/ascii.json")
BINARY_SPEC = common.load_spec("specs/binary-bitmap.json")
NIBSS_SPEC = common.load_spec("specs/nibss-v1.16.json")
ENGINE = rules.ResponseEngine("rules/rules.json")
NIBSS_ENGINE = rules.ResponseEngine("rules/nibss-rules.json")


class Iso8583LabTests(unittest.TestCase):
    def test_binary_two_byte_framing_is_separate_from_parser(self):
        sender, receiver = socket.socketpair()
        try:
            tcp_framing.send_frame(sender, b"0100PAYLOAD", "binary-2")
            self.assertEqual(tcp_framing.recv_frame(receiver, "binary-2"), b"0100PAYLOAD")
        finally:
            sender.close()
            receiver.close()

    def test_ascii_four_digit_framing_is_separate_from_parser(self):
        sender, receiver = socket.socketpair()
        try:
            tcp_framing.send_frame(sender, b"0800", "ascii-4")
            self.assertEqual(tcp_framing.recv_frame(receiver, "ascii-4"), b"0800")
        finally:
            sender.close()
            receiver.close()

    def test_message_date_expressions(self):
        message = common.load_message(
            "messages/authorization-approved.json",
            now=datetime(2026, 9, 23, 14, 5, 6),
        )
        self.assertEqual(message["7"], "0923140506")
        self.assertEqual(message["12"], "140506")
        self.assertEqual(message["13"], "0923")

    def test_raw_log_uses_printable_ascii_and_hex_escapes(self):
        raw = b"ABC\\\x00\x1f\x7f\x80~"
        self.assertEqual(common.escape_raw(raw), r"ABC\\\x00\x1F\x7F\x80~")

    def test_encode_decode_roundtrip(self):
        message = common.load_message("messages/authorization-approved.json")
        decoded = common.decode_message(common.encode_message(message, ASCII_SPEC), ASCII_SPEC)
        self.assertEqual(decoded["t"], "0100")
        self.assertEqual(decoded["2"], "4111111111111111")
        self.assertEqual(decoded["4"], "000000002500")
        self.assertEqual(decoded["11"], "100001")

    def test_binary_bitmap_roundtrip(self):
        message = common.load_message("messages/authorization-approved.json")
        raw = common.encode_message(message, BINARY_SPEC)
        decoded = common.decode_message(raw, BINARY_SPEC)
        self.assertEqual(decoded["12"], message["12"])
        self.assertEqual(decoded["13"], message["13"])
        self.assertLess(len(raw), len(common.encode_message(message, ASCII_SPEC)))

    def test_nibss_profile_definitions(self):
        self.assertEqual(NIBSS_SPEC["p"]["data_enc"], "ascii")
        self.assertEqual(NIBSS_SPEC["63"]["len_type"], 4)
        self.assertEqual(NIBSS_SPEC["63"]["max_len"], 9999)
        self.assertEqual(NIBSS_SPEC["123"]["len_type"], 3)
        self.assertEqual(NIBSS_SPEC["123"]["max_len"], 15)
        self.assertEqual(NIBSS_SPEC["128"]["max_len"], 64)

    def test_nibss_two_bitmap_roundtrip(self):
        message = {
            "t": "0200",
            "2": "4111111111111111",
            "3": "000000",
            "4": "000000001000",
            "7": "1104123456",
            "11": "123456",
            "41": "TERM0001",
            "42": "DEMO MERCHANT  ",
            "49": "566",
            "123": "510101511344101",
            "128": "0" * 64,
        }
        raw = common.encode_message(message, NIBSS_SPEC)
        decoded = common.decode_message(raw, NIBSS_SPEC)
        self.assertEqual(decoded["123"], message["123"])
        self.assertEqual(decoded["128"], message["128"])
        self.assertEqual(len(decoded["p"]), 16)
        self.assertEqual(len(decoded["1"]), 16)

    def test_nibss_rules_reject_missing_mandatory_fields_before_business_rules(self):
        request = common.load_message("messages/authorization-approved.json")
        response, rule, _ = NIBSS_ENGINE.respond(request)
        self.assertEqual(response["t"], "0110")
        self.assertEqual(response["39"], "30")
        self.assertIn("missing DE14", rule)
        self.assertIn("missing DE128", rule)

    def test_complete_nibss_authorization_reaches_business_rules(self):
        request = common.load_message("messages/authorization-approved.json")
        request.update({
            "14": "2912", "18": "5999", "22": "051", "25": "00",
            "28": "C00000000", "32": "111111", "43": "DEMO MERCHANT           LAGOS       NG",
            "123": "510101511344101", "128": "0" * 64,
        })
        response, rule, _ = NIBSS_ENGINE.respond(request)
        self.assertEqual(response["39"], "00")
        self.assertEqual(rule, "approve authorization")

    def test_nibss_profile_does_not_claim_generic_0600_support(self):
        request = common.load_message("messages/administrative-request.json")
        response, rule, _ = NIBSS_ENGINE.respond(request)
        self.assertIsNone(response)
        self.assertEqual(rule, "no rules for MTI")

    def test_every_included_spec_roundtrip(self):
        messages = (
            "messages/authorization-approved.json",
            "messages/financial-advice.json",
            "messages/reversal-request.json",
            "messages/reversal.json",
            "messages/administrative-request.json",
            "messages/network-sign-on.json",
        )
        spec_paths = sorted(Path("specs").glob("*.json"))
        self.assertEqual(len(spec_paths), 9)
        for spec_path in spec_paths:
            spec = common.load_spec(spec_path)
            for message_path in messages:
                with self.subTest(spec=spec_path.name, message=message_path):
                    message = common.load_message(message_path)
                    decoded = common.decode_message(common.encode_message(message, spec), spec)
                    self.assertEqual(decoded["t"], message["t"])
                    self.assertEqual(decoded["11"], message["11"])
                    self.assertEqual(decoded.get("90"), message.get("90"))

    def test_approved_response(self):
        request = common.load_message("messages/authorization-approved.json")
        response, rule, _ = ENGINE.respond(request)
        self.assertEqual(response["t"], "0110")
        self.assertEqual(response["39"], "00")
        self.assertEqual(response["44"], "PAN4=1111,STAN=100001")
        self.assertEqual(rule, "approve authorization")
        self.assertNotIn("2", response)

    def test_declined_by_pan(self):
        request = common.load_message("messages/authorization-declined.json")
        response, rule, _ = ENGINE.respond(request)
        self.assertEqual(response["39"], "05")
        self.assertEqual(rule, "decline PAN ending in 0000")

    def test_declined_by_invalid_luhn_checksum(self):
        request = common.load_message("messages/authorization-invalid-luhn.json")
        response, rule, _ = ENGINE.respond(request)
        self.assertEqual(response["39"], "14")
        self.assertEqual(rule, "decline invalid PAN checksum")

    def test_luhn_validation(self):
        self.assertTrue(rules.luhn_valid("4111111111111111"))
        self.assertFalse(rules.luhn_valid("4111111111111112"))
        self.assertFalse(rules.luhn_valid("not-a-pan"))

    def test_authorization_falls_back_to_default_rejection(self):
        request = common.load_message("messages/authorization-approved.json")
        request["2"] = "not-a-pan"
        response, rule, _ = ENGINE.respond(request)
        self.assertEqual(response["t"], "0110")
        self.assertEqual(response["39"], "96")
        self.assertEqual(rule, "default")

    def test_invalid_date_is_rejected(self):
        request = common.load_message("messages/authorization-invalid-date.json")
        response, rule, _ = ENGINE.respond(request)
        self.assertEqual(response["39"], "30")
        self.assertEqual(rule, "reject invalid or stale DE13")

    def test_reversal_response(self):
        request = common.load_message("messages/reversal.json")
        original = request["90"]
        response, rule, _ = ENGINE.respond(request)
        self.assertEqual(response["t"], "0430")
        self.assertEqual(response["90"], original)
        self.assertEqual(rule, "approve reversal with current dates")

    def test_financial_advice_response(self):
        request = common.load_message("messages/financial-advice.json")
        self.assertEqual(request["42"], "DEMO MERCHANT  ")
        self.assertEqual(len(request["42"]), 15)
        response, rule, _ = ENGINE.respond(request)
        self.assertEqual(response["t"], "0230")
        self.assertEqual(response["39"], "00")
        self.assertEqual(response["11"], request["11"])
        self.assertEqual(rule, "acknowledge financial advice with current dates")

    def test_administrative_response(self):
        request = common.load_message("messages/administrative-request.json")
        response, rule, _ = ENGINE.respond(request)
        self.assertEqual(response["t"], "0610")
        self.assertEqual(response["39"], "00")
        self.assertEqual(response["60"], "PARAMETER-STATUS")
        self.assertEqual(rule, "acknowledge administrative request")

    def test_network_sign_on_response_uses_secondary_bitmap(self):
        request = common.load_message("messages/network-sign-on.json")
        decoded_request = common.decode_message(
            common.encode_message(request, ASCII_SPEC), ASCII_SPEC
        )
        self.assertIn("1", decoded_request)
        self.assertEqual(decoded_request["70"], "001")

        response, rule, _ = ENGINE.respond(request)
        self.assertEqual(response["t"], "0810")
        self.assertEqual(response["39"], "00")
        self.assertEqual(response["70"], "001")
        self.assertEqual(rule, "acknowledge network sign-on")

    def test_reversal_request_response(self):
        request = common.load_message("messages/reversal-request.json")
        original = request["90"]
        response, rule, template = ENGINE.respond(request)
        self.assertEqual(response["t"], "0410")
        self.assertEqual(response["39"], "00")
        self.assertEqual(response["90"], original)
        self.assertEqual(rule, "approve reversal with current dates")
        self.assertEqual(template.name, "reversal-request-approved.json")

    def test_reversal_uses_primary_and_secondary_bitmaps(self):
        request = common.load_message("messages/reversal.json")
        decoded_request = common.decode_message(
            common.encode_message(request, ASCII_SPEC), ASCII_SPEC
        )
        self.assertIn("p", decoded_request)
        self.assertIn("1", decoded_request)
        self.assertEqual(decoded_request["90"], request["90"])

        response, _, _ = ENGINE.respond(request)
        decoded_response = common.decode_message(
            common.encode_message(response, ASCII_SPEC), ASCII_SPEC
        )
        self.assertIn("p", decoded_response)
        self.assertIn("1", decoded_response)
        self.assertEqual(decoded_response["90"], request["90"])

    def test_three_leg_client_flow(self):
        flow = rules.ClientFlowEngine("client-rules/three-leg-authorization.json")
        first_action = flow.start()
        self.assertTrue(first_action.expect_response)
        leg1 = common.load_message(first_action.message_path, registers=flow.registers)
        self.assertEqual(leg1["t"], "0100")

        leg2, _, _ = ENGINE.respond(leg1)
        self.assertEqual(leg2["t"], "0110")
        third_action, client_rule = flow.next(leg2)
        self.assertEqual(client_rule, "approved - send final confirmation")
        self.assertFalse(third_action.expect_response)

        leg3 = common.load_message(third_action.message_path, registers=flow.registers)
        self.assertEqual(leg3["t"], "0120")
        self.assertEqual(leg3["11"], leg2["11"])
        self.assertEqual(leg3["37"], leg2["37"])
        fourth_leg, server_rule, _ = ENGINE.respond(leg3)
        self.assertIsNone(fourth_leg)
        self.assertEqual(server_rule, "default: no response")

    def test_undefined_register_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "undefined"):
            rules.render_response({"t": "0100"}, {"39": "//$missing/"})

    def test_substitution_capture_group(self):
        response = rules.render_response(
            {"t": "0100", "41": "TERM0001"},
            {"41": "/^TERM([0-9]{4})$/RESP-$1/"},
        )
        self.assertEqual(response["41"], "RESP-0001")

    def test_escaped_separators_in_template(self):
        response = rules.render_response(
            {"t": "0100", "44": "old"},
            {"44": r"/old/path\/part\;one/"},
        )
        self.assertEqual(response["44"], "path/part;one")


if __name__ == "__main__":
    unittest.main()
