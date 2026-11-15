# Week 10 — Day 2: Reference TCP Gateway

This is the complete and documented reference implementation students may
use on Day 3 if they did not finish Day 2.

## Directories

```
day02_reference/
  CMakeLists.txt        C++17 build definition
  README.md             Build, execution and architecture
  src/gateway.cpp       Commented Boost.Asio implementation
  tests/public/         Original Day 2 public tests
```

## Build

Requires Linux / WSL2 / course Dev Container, C++17, CMake, Boost.Asio,
Boost.System and POSIX threads.

```bash
cmake -S . -B build
cmake --build build -j
```

## Run

Start the Python authorizer on port 8600, then run:

```bash
./build/gateway 0.0.0.0:8500 127.0.0.1:8600
```

The first argument is where clients connect; the second is where the Python
authorizer is listening. Both are mandatory `IPv4:port` addresses.

## Architecture, step by step

1. `main()` parses both endpoints, creates a `tcp::acceptor`, and waits for a
   client using `accept()`.
2. A new `std::thread` runs `serve_client()` for that client. Other clients
   continue to be accepted, even while this one is idle.
3. `serve_client()` creates an independent `asio::io_context`, and a `Session`
   with **two sockets**: one client, one outgoing authorizer connection.
4. `Session::read_client()` and `read_authorizer()` post asynchronous reads
   in opposite directions. When bytes arrive, `asio::async_write()` forwards
   exactly that many bytes (even if TCP needs several partial writes).
5. Each direction has a separate 16 KiB buffer. A new read only starts when
   the preceding write finishes: memory is bounded and backpressure works.
6. On EOF, the other socket's sending half is shut down. After both EOFs, the
   sockets close. On network error, only that session terminates.

## Important C++ concepts

- **RAII:** sockets are objects that close automatically when destroyed.
- **`std::shared_ptr`:** callbacks may run later. Capturing `self` keeps the
  Session and its buffers alive until the operation completes.
- **Callbacks:** asynchronous functions return immediately; the callback runs
  when the operation completes inside `io.run()`.
- **No ISO 8583 parsing:** TCP is a byte stream. The gateway forwards all bytes
  unchanged, including `\0` and partial ISO frames. Parsing starts on Day 3.
- **Logging:** a mutex only protects `std::cerr`; sockets are owned by their
  own worker, with no shared authorizer connection.

## Public tests

```bash
python3 tests/public/test_gateway.py --gateway-cmd './build/gateway {listen} {authorizer}'
```

The course grading harness expects the two `IPv4:port` arguments unchanged.
Public tests: P1 authorization, P2 persistent connection, P3 simultaneous
clients, P4 disconnect/reconnect, P5 preservation of binary bytes.

The public test file is copied unchanged from the original Day 2 course pack.
Instructor-only cases remain separate from this student-facing reference.

## Classroom limitations

One detached thread per connection is acceptable here, but a production
internet-facing service would need resource limits, timeouts and graceful
shutdown. This demo intentionally has no ISO 8583 validation or logging of
sensitive message contents.
