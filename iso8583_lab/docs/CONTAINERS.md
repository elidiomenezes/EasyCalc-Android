# Interactive Docker Laboratory

The Docker image is deliberately neutral. It does not automatically start a
client, server, demo, or test. Starting it gives you one Bash terminal with the
complete project and its Python dependencies installed.

Inside that terminal, build any topology you want: one server and one client,
multiple servers, several clients, background processes, different specs, or
the included demonstrations.

## Requirements

- Docker Engine or Docker Desktop
- Docker Compose v2 (`docker compose`, with a space)

Run the following commands from the `iso8583_lab` directory.

## Open the laboratory terminal

```bash
docker compose build lab
docker compose run --rm --service-ports lab
```

The prompt you see is inside the container, in `/app`. Nothing starts until
you issue a command.

## Build and export the image in one command

```bash
./build_container_image.sh
```

This creates both:

- Local Docker image `iso8583-lab:local`.
- Transportable file `iso8583-lab-image.tar`.

Copy the tar file to another machine and load it with:

```bash
docker load -i iso8583-lab-image.tar
```

Customize the tag or output path when needed:

```bash
IMAGE_NAME=company/iso8583-lab:1.0 \
OUTPUT_IMAGE=dist/iso8583-lab-1.0.tar \
./build_container_image.sh
```

## Start a server and client inside the same container

At the container prompt:

```bash
python3 server.py --host 0.0.0.0 --port 8583 &
python3 client.py \
  --host 127.0.0.1 \
  --port 8583 \
  --rules client-rules/authorization-approved.json
```

The `&` leaves the server in the background and returns the terminal to you.
Use `jobs` to see background processes and `kill %1` to stop job 1.

## Build your own topology

Start two servers on different ports:

```bash
python3 server.py --host 0.0.0.0 --port 8583 \
  --spec specs/ascii.json --color always &

python3 server.py --host 0.0.0.0 --port 8584 \
  --spec specs/packed-bcd-numeric.json --color always &
```

Then point clients at either endpoint:

```bash
python3 client.py --host 127.0.0.1 --port 8583 \
  --spec specs/ascii.json \
  --rules client-rules/financial.json

python3 client.py --host 127.0.0.1 --port 8584 \
  --spec specs/packed-bcd-numeric.json \
  --rules client-rules/three-leg-authorization.json
```

The image exposes container ports `8500` through `8599`. Compose publishes the
same range on the host, so an external program can connect to any server you
start in that range.

## Change the host-side port range

The host range and container range must contain the same number of ports. For
example, publish host ports `9500–9599` onto container ports `8500–8599`:

```bash
ISO8583_PORT_RANGE=9500-9599 \
  docker compose run --rm --service-ports lab
```

Inside the container you still listen on ports `8500–8599`; outside Docker,
clients use `9500–9599`.

## Included shortcuts

From the container terminal:

```bash
./demo.sh
./run_tests.sh
./run_all_specs.sh
```

`demo.sh` runs the interactive classroom presentation. `run_tests.sh` runs all
scenarios with one selected spec. `run_all_specs.sh` tests all nine specs.

## Automated container verification

From the host:

```bash
./container_smoke_test.sh
```

This builds the image and runs the complete test matrix inside one temporary
container. It does not leave a server running.

## Persist or replace laboratory files

The default container contains the project exactly as it was built. Changes
made inside disappear when the `--rm` container exits.

To use a host directory as a persistent workspace, mount it explicitly:

```bash
docker run --rm -it \
  -p 8500-8599:8500-8599 \
  -v "$PWD:/workspace" \
  iso8583-lab:local
```

The bundled project remains in `/app`; your host directory appears at
`/workspace`. Copy only what you want, or run scripts from either location.

## Exit

At the container prompt:

```bash
exit
```

Because the container was launched with `--rm`, Docker removes that container
after the shell exits. The built image remains available for the next session.
