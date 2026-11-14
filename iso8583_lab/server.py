#!/usr/bin/env python3
"""ISO 8583 command-line server."""

import argparse
import socket
import socketserver
import threading
import time

from iso8583_common import (
    DEFAULT_RULES_PATH,
    MessageLogger,
    add_connection_arguments,
    add_format_arguments,
    decode_message,
    encode_message,
    load_spec,
    make_logger,
)
from rules_engine import ResponseEngine
from tcp_framing import add_framing_argument, recv_frame, send_frame


class IsoRequestHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server: IsoServer = self.server  # type: ignore[assignment]
        self.request.settimeout(server.socket_timeout)
        try:
            leg = 1
            while True:
                try:
                    raw_request = recv_frame(self.request, server.framing)
                except ConnectionError:
                    server.logger.status("SERVER: client closed the connection")
                    return
                except socket.timeout:
                    server.logger.status(f"SERVER: idle timeout after {server.socket_timeout:.0f}s")
                    return
                try:
                    request = decode_message(raw_request, server.spec)
                except (ValueError, TypeError, LookupError) as exc:
                    response, rule_name, template_path = server.engine.respond_malformed(raw_request, str(exc))
                    server.logger.status(f"RULE: {rule_name}; template={template_path}", error=True)
                    if response is not None:
                        raw_response = encode_message(response, server.spec)
                        send_frame(self.request, raw_response, server.framing)
                        server.logger.message("SERVER SENT MALFORMED RESPONSE", response, raw_response)
                    continue
                server.logger.message(
                    f"SERVER RECEIVED LEG {leg} from {self.client_address[0]}",
                    request,
                    raw_request,
                )
                if server.response_delay:
                    time.sleep(server.response_delay)
                if server.drop_response:
                    server.logger.status("SERVER: response intentionally dropped; connection remains open")
                    continue
                response, rule_name, template_path = server.engine.respond(request)
                server.logger.status(f"RULE: {rule_name}; template={template_path}")
                if response is None:
                    server.logger.status("SERVER: MTI/rule configured without a response; connection remains open")
                    continue
                raw_response = encode_message(response, server.spec)
                send_frame(self.request, raw_response, server.framing)
                leg += 1
                server.logger.message(f"SERVER SENT LEG {leg}", response, raw_response)
                leg += 1
        except Exception as exc:
            server.logger.status(f"SERVER ERROR: {exc}", error=True)
        finally:
            if server.once:
                threading.Thread(target=server.shutdown, daemon=True).start()


class IsoServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, *, args, spec: dict, logger: MessageLogger) -> None:
        super().__init__(address, IsoRequestHandler)
        self.response_delay = args.response_delay
        self.drop_response = args.drop_response
        self.socket_timeout = args.timeout
        self.framing = args.framing
        self.once = args.once
        self.spec = spec
        self.logger = logger
        self.engine = ResponseEngine(args.rules)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ISO 8583 TCP server")
    add_connection_arguments(parser)
    parser.set_defaults(timeout=300.0)
    add_format_arguments(parser)
    add_framing_argument(parser)
    parser.add_argument("--rules", default=str(DEFAULT_RULES_PATH))
    parser.add_argument("--response-delay", type=float, default=0.0)
    parser.add_argument("--drop-response", action="store_true")
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> None:
    args = make_parser().parse_args()
    spec = load_spec(args.spec)
    logger = make_logger(args, "server")
    server = IsoServer((args.host, args.port), args=args, spec=spec, logger=logger)
    logger.status(f"ISO 8583 server listening on {args.host}:{args.port}; spec={args.spec}")
    logger.status(f"Rules loaded from {args.rules}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
