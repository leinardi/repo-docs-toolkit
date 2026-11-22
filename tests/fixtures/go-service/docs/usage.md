# Usage

```sh
svc --listen :9000 --verbose
svc --port 9000
make lint
make release
make -C . build
SVC_TOKEN=secret svc
./scripts/smoke.sh
```

Set the `SVC_TIMEOUT` environment variable to change the timeout. `RUST_LOG` is not read here.

The service has 3 subcommands. The `--listen` flag is available
since v2.0.
