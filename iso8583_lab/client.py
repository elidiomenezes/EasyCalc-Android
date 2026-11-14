#!/usr/bin/env python3
"""ISO 8583 command-line client."""

import argparse
import socket
import time
import select

from iso8583_common import (
    add_connection_arguments,
    add_format_arguments,
    decode_message,
    encode_message,
    load_message,
    load_spec,
    make_logger,
)
from rules_engine import ClientFlowEngine
from tcp_framing import add_framing_argument, recv_frame, send_frame


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ISO 8583 TCP client")
    add_connection_arguments(parser)
    add_format_arguments(parser)
    add_framing_argument(parser)
    parser.add_argument("--rules", required=True, help="path to the client flow rules JSON")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    args = make_parser().parse_args()
    logger = make_logger(args, "client")
    try:
        spec = load_spec(args.spec)
        engine = ClientFlowEngine(args.rules)
        action = engine.start()
        if args.dry_run:
            message = load_message(action.message_path, registers=engine.registers)
            raw_request = encode_message(message, spec)
            logger.message("CLIENT DRY RUN LEG 1", message, raw_request)
            return

        with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
            sock.settimeout(args.timeout)
            leg = 1
            while action is not None:
                message = load_message(action.message_path, registers=engine.registers)
                raw_request = encode_message(message, spec)
                send_frame(sock, raw_request, args.framing)
                logger.message(f"CLIENT SENT LEG {leg}", message, raw_request)
                if not action.expect_response:
                    logger.status(f"FLOW COMPLETE after leg {leg}; no response expected")
                    break

                raw_response = recv_frame(sock, args.framing)
                leg += 1
                response = decode_message(raw_response, spec)
                logger.message(f"CLIENT RECEIVED LEG {leg}", response, raw_response)
                action, rule_name = engine.next(response)
                logger.status(f"CLIENT RULE: {rule_name}")
                if action is None:
                    logger.status(f"FLOW COMPLETE after leg {leg}")
                    break
            if engine.heartbeat_enabled:
                logger.status(f"CLIENT: connection remains open; heartbeat every {engine.heartbeat_interval:g}s; Ctrl+C to close")
                next_heartbeat = time.monotonic() + engine.heartbeat_interval
                while True:
                    remaining = max(0.0, next_heartbeat - time.monotonic())
                    ready, _, _ = select.select([sock], [], [], remaining)
                    if ready:
                        # A peer close or unsolicited frame is handled explicitly.
                        raw_inbound = recv_frame(sock, args.framing)
                        inbound = decode_message(raw_inbound, spec)
                        logger.message("CLIENT RECEIVED UNSOLICITED", inbound, raw_inbound)
                        continue
                    heartbeat = engine.heartbeat_action
                    heartbeat_message = load_message(heartbeat.message_path, registers=engine.registers)
                    raw_heartbeat = encode_message(heartbeat_message, spec)
                    send_frame(sock, raw_heartbeat, args.framing)
                    logger.message("CLIENT SENT HEARTBEAT", heartbeat_message, raw_heartbeat)
                    next_heartbeat = time.monotonic() + engine.heartbeat_interval
                    if heartbeat.expect_response:
                        raw_heartbeat_reply = recv_frame(sock, args.framing)
                        heartbeat_reply = decode_message(raw_heartbeat_reply, spec)
                        logger.message("CLIENT RECEIVED HEARTBEAT RESPONSE", heartbeat_reply, raw_heartbeat_reply)
                leg += 1
    except KeyboardInterrupt:
        logger.status("CLIENT: stopped by user; socket closed")
        return
    except socket.timeout:
        logger.status(f"CLIENT TIMEOUT after {args.timeout:.1f}s", error=True)
        raise SystemExit(2)
    except (OSError, ConnectionError) as exc:
        logger.status(f"CLIENT CONNECTION ERROR: {exc}", error=True)
        raise SystemExit(3)
    except (ValueError, KeyError, TypeError) as exc:
        logger.status(f"CLIENT MESSAGE ERROR: {exc}", error=True)
        raise SystemExit(4)


if __name__ == "__main__":
    main()
