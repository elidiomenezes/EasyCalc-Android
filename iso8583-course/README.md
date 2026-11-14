# ISO 8583 course development environment

This folder is independent of the Android calculator application.

## Tools and libraries
Ubuntu 24.04, GCC/G++, CMake, Make, Ninja, GDB, Git, Boost.Asio, SQLite3, OpenSSL, Python 3, pyiso8583, pkg-config, ncat, netcat-openbsd, curl, jq and xxd.

## Local setup
1. Install Docker, Visual Studio Code, and the **Dev Containers** extension.
2. Clone this repository and switch to the `iso8583-course-devcontainer` branch.
3. Open the `iso8583-course` folder in VS Code.
4. Run **Dev Containers: Reopen in Container** (requires the GHCR image to be published and accessible).
5. In the container terminal run `bash scripts/verify_environment.sh`.

For a local build without GHCR, from this folder run `docker build -t iso8583-course:test .` and then `docker run --rm -v "$PWD:/workspaces/iso8583-course" -w /workspaces/iso8583-course iso8583-course:test bash scripts/verify_environment.sh` (POSIX shell).

The workspace is bind-mounted from the host and persists when the container is rebuilt. The C++ check compiles and links against Boost.Asio, SQLite3, and OpenSSL. The Python check imports pyiso8583. This does **not** include the existing ISO 8583 simulator; it must be integrated separately.

The image is intended for AMD64 and ARM64. For students: create your own GitHub repository and clone it into persistent host storage.
