# ISO 8583 course development environment

This folder is independent of the Android calculator application.

## Local setup

1. Install Docker, Visual Studio Code, and the **Dev Containers** extension.
2. Clone this repository and switch to the `iso8583-course-devcontainer` branch.
3. Open the `iso8583-course` folder in VS Code.
4. Run **Dev Containers: Reopen in Container**.
5. In the container terminal run `bash scripts/verify_environment.sh`.

The workspace is bind-mounted from the host and persists when the container is rebuilt. The provided C++ and Python checks verify the development toolchain. This does **not** include the existing ISO 8583 simulator; it must be integrated from its source repository before the assignment can use it.

On Apple Silicon, Docker builds a native ARM64 image; on x86-64, it builds AMD64.

For students: create your own GitHub repository and clone it into a persistent host-mounted folder. Do not store coursework solely in a disposable container filesystem.
