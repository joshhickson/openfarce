# The 8-lane blade

A printed rack that holds eight USB MicroSD readers in a row, cards facing up,
plugs facing down into a hub in a tray at the base. Addendum A2.5.

**Source:** `blade.scad`. **STLs:** not yet exported — see below.

## Measure your readers before you print

The dimensions at the top of `blade.scad` are nominal for a generic single-slot
USB 3.0 reader, and *generic* is the whole problem: these are commodity parts
with no standard body, and two readers from the same listing can differ by a
millimetre. Put calipers on the readers you actually bought, edit the six
numbers under `[Reader body]`, and regenerate.

A blade that does not fit costs four hours of printer time and a length of
filament. Measuring costs two minutes. This is why the `.scad` is the
deliverable and an `.stl` is only a convenience.

```
reader_l   along the blade, plug end to card end
reader_w   across — this one sets the lane pitch, so get it right
reader_h   thickness
plug_l     how far the USB-A plug sticks out of the body
plug_w     plug width
plug_h     plug thickness
```

`tol` adds clearance per side and starts at 0.35 mm, which suits most FDM
printers. If the pockets come out tight, raise it before changing anything else.

## Rendering

```bash
openscad -o blade_8.stl    -D 'part="blade"'  blade.scad
openscad -o hub_tray.stl   -D 'part="tray"'   blade.scad
openscad -o fan_shroud.stl -D 'part="shroud"' blade.scad
```

Other lane counts work: `-D 'lanes=4'`. Four and ten both fit a common hub.

## Print settings

PETG, 0.2 mm layers, 3 walls, 15% infill, **no supports**. The lattice and the
pockets are designed to print unsupported in the default orientation — blade
floor down, pockets opening upward.

PETG rather than PLA because the reader bodies get warm under sustained writes
and a PLA blade will creep. If PLA is what you have, print it and keep a fan on
the array; it will be fine at room temperature and will sag if the room is not.

## Airflow is not optional

The sides are an open lattice on purpose. Eight readers side by side in a closed
enclosure throttle within minutes of sustained writing (A2.1.2), and a throttled
card drops from around 104 MB/s to under 10 MB/s. The fan mount on the plug end
takes a 40 mm 5 V fan and blows along the row. Nothing here should be boxed in.

## Stacking

Pegs on the top of the blade and sockets in the tray let five blades stack into
a 40-lane tower for the campaign photograph. **The stack is not electrically
real** — five blades is forty readers, which is well past what one Pi and one
hub can power. It is a photograph, and any caption on the site says so.

## Status

- [x] `blade.scad`, parametric, all inputs at the top
- [ ] STLs exported — needs OpenSCAD, which is not installed on the machine that
      wrote this
- [ ] Test fit (H-A2.2): readers seat, plugs reach the hub, cards eject cleanly,
      nothing rubs
- [ ] v2 incorporating the fit notes

Nothing here has been printed. The geometry is untested against real hardware
and the first print should be treated as a fit check, not a finished part.
