---
title: Home
template: home.html
hide: [navigation, toc]
home:
  text: Geometry that streams
  tagline: Typed, streaming geometry for Python. Tile, clip and measure shapes without loading them all.
  actions:
    - { text: Get started, link: getting-started/, primary: true }
    - { text: API reference, link: reference/ }
---

<div class="rdt-showcase" markdown>

```python
from tessellate import Grid, read_shapes

grid = Grid(cell=250.0)
for shape in read_shapes("parcels.geojson"):
    for tile, part in grid.clip(shape):
        print(tile, round(part.area, 1))
```

</div>

<div class="rdt-install" markdown>

=== "pip"

    ```sh
    pip install tessellate
    ```

=== "uv"

    ```sh
    uv add tessellate
    ```

</div>

## Features

<div class="grid cards" markdown>

- :lucide-waves:{ .lg }

    **Streaming**

    Shapes are read and clipped one at a time, so memory stays flat on files larger than your RAM.

- :lucide-braces:{ .lg }

    **Fully typed**

    Every public function has precise type hints, checked in CI, so your editor completes and checks calls.

- :lucide-grid-3x3:{ .lg }

    **Any grid**

    Square, hexagonal and custom grids share one interface, and switching between them is a one-line change.

- :lucide-package:{ .lg }

    **No native build**

    Pure Python wheels with no compiler and no system libraries, on every platform Python supports.

</div>
