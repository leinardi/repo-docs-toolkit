<h1 align="center">tessellate</h1>

<p align="center"><strong>Typed, streaming geometry for Python. Tile, clip and measure shapes without loading them all.</strong></p>

<p align="center">
  <a href="https://github.com/example/tessellate/actions/workflows/ci.yaml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/example/tessellate/ci.yaml?style=flat-square"></a>
  <a href="https://pypi.org/project/tessellate/"><img alt="PyPI" src="https://img.shields.io/pypi/v/tessellate?style=flat-square"></a>
  <a href="https://example.github.io/tessellate/"><img alt="Documentation" src="https://img.shields.io/badge/docs-site-blue?style=flat-square"></a>
  <a href="https://github.com/example/tessellate/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/example/tessellate?style=flat-square"></a>
</p>

<p align="center"><a href="https://example.github.io/tessellate/">Documentation</a> · <a href="#-installation">Install</a> · <a href="CONTRIBUTING.md">Contributing</a></p>

tessellate reads shapes one at a time and clips them to a grid, so files larger than memory work
as well as small ones.

## ✨ Features

- **Streaming:** shapes are read and clipped one at a time, so memory stays flat.
- **Fully typed:** every public function has precise type hints, checked in CI.
- **Any grid:** square, hexagonal and custom grids share one interface.
- **No native build:** pure Python wheels, with no compiler and no system libraries.

## 📦 Installation

```sh
pip install tessellate
```

It supports the Python versions listed on [PyPI](https://pypi.org/project/tessellate/); `uv add
tessellate` works too.

## 🚀 Quick start

```python
from tessellate import Grid, read_shapes

grid = Grid(cell=250.0)
for shape in read_shapes("parcels.geojson"):
    for tile, part in grid.clip(shape):
        print(tile, round(part.area, 1))
```

The [documentation][docs] explains grids, clipping and the readers, and its API reference lists
every function.

## 🛠️ Development

CONTRIBUTING.md explains how to set up a development environment, run the tests and the other
checks a pull request must pass.

## 🤝 Contributing

Bug reports and pull requests are welcome; read [CONTRIBUTING.md](CONTRIBUTING.md) first.

## 📝 License

Licensed under the [MIT License](https://github.com/example/tessellate/blob/main/LICENSE).

[docs]: https://example.github.io/tessellate/
