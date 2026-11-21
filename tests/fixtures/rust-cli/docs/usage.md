# Usage

Run `make build` (from the included file) or `make test`. `make deploy` does not exist.

Set `RCLI_CONFIG` or `RUST_LOG=debug`. The `--verbose` flag was removed.

See [the force flag](#the---force-flag), [a broken anchor](#no-such-section) and the
[contributing guide](../CONTRIBUTING.md). The [README](../README.md) is outside the site.

![Screenshot](images/missing.png)

## The `--force` flag

Overwrites files.

~~~text
[ignored](nowhere.md)
~~~
