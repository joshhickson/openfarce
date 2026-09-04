// blade.scad — the 8-lane reference rig blade. Addendum A2.5.
//
// A vertical blade holding N USB card readers in a row: cards face up so they
// can be swapped without dismantling anything, plugs face down into a hub
// sitting in a tray at the base, and the sides are open so a fan on one end can
// blow along the whole row.
//
// ---------------------------------------------------------------------------
// MEASURE YOUR READERS FIRST.
//
// The defaults below are nominal for a generic single-slot USB 3.0 MicroSD
// reader, and generic is exactly the problem: these are commodity parts with no
// standard body. Two readers from the same listing can differ by a millimetre.
// Take calipers to the readers you actually bought, put those numbers at the
// top of this file, and regenerate. A printed blade that does not fit is four
// hours and a spool of filament; measuring is two minutes.
//
// This is why the .scad is the deliverable and the .stl is a convenience.
// ---------------------------------------------------------------------------
//
//   openscad -o blade_8.stl     -D 'part="blade"'     blade.scad
//   openscad -o hub_tray.stl    -D 'part="tray"'      blade.scad
//   openscad -o fan_shroud.stl  -D 'part="shroud"'    blade.scad
//   openscad -o blade_4.stl     -D 'part="blade"' -D 'lanes=4' blade.scad

/* [What to render] */
part = "blade";          // ["blade", "tray", "shroud", "all"]

/* [Array] */
lanes = 8;               // [1:16] 8 is the reference rig; 4 and 10 also fit a hub

/* [Reader body — MEASURE THESE] */
reader_l = 32.0;         // along the blade, plug end to card end
reader_w = 14.5;         // across, the dimension that sets lane pitch
reader_h = 6.0;          // thickness
plug_l   = 12.0;         // USB-A plug sticking out of the body
plug_w   = 12.2;
plug_h   = 4.8;

/* [Fit] */
tol      = 0.35;         // added to every reader pocket dimension, per side
wall     = 2.0;          // structural wall thickness
floor_t  = 2.4;          // blade floor under the readers
lane_gap = 3.0;          // rib between lanes; airflow lives here

/* [Hub tray — MEASURE YOURS] */
hub_l    = 100.0;
hub_w    = 45.0;
hub_h    = 22.0;
tray_lip = 6.0;          // how far the tray walls come up the hub

/* [Fan] */
fan_size = 40;           // [40, 50, 60] mm
fan_screw_pitch = 32;    // 40 mm fans are 32 mm between mounting holes
fan_screw_d = 3.4;       // M3 clearance

/* [Stacking] */
peg_d    = 5.0;          // five blades stack into the 40-lane campaign photo
peg_h    = 3.0;
peg_tol  = 0.25;

/* [Labels] */
label_w  = 10.0;         // recessed slot for a numbered sticker, one per bay
label_h  = 6.0;
label_d  = 0.8;

$fn = 48;

// ---------------------------------------------------------------- derived ---

pocket_l = reader_l + 2 * tol;
pocket_w = reader_w + 2 * tol;
pocket_h = reader_h + 2 * tol;

pitch    = pocket_w + lane_gap;
blade_w  = lanes * pitch + 2 * wall;
blade_l  = pocket_l + 2 * wall;
blade_h  = pocket_h + floor_t + 4;      // 4 mm of shoulder above the reader

// The plug end hangs below the floor so it can reach a hub underneath.
plug_drop = plug_l + 2;

// ------------------------------------------------------------------ blade ---

module lane_pocket(i) {
    x = wall + i * pitch;
    // Reader body.
    translate([x - tol, wall - tol, floor_t])
        cube([pocket_w, pocket_l, pocket_h + 10]);   // +10 opens the top
    // Plug slot through the floor.
    translate([x + (pocket_w - plug_w) / 2 - tol, wall - tol, -plug_drop])
        cube([plug_w + 2 * tol, plug_h + 2 * tol + 2, plug_drop + floor_t + 1]);
    // Finger cutout on the card end so a card can be pinched out without tools.
    translate([x + pocket_w / 2 - tol, wall + pocket_l - 6, floor_t - 1])
        cylinder(d = 9, h = pocket_h + 12);
}

module label_recess(i) {
    x = wall + i * pitch + (pocket_w - label_w) / 2;
    translate([x, -0.01, blade_h - label_h - 2])
        cube([label_w, label_d, label_h]);
}

// Open lattice: the sides are mostly absent, which is the point. A closed box
// of eight readers under sustained write throttles within minutes (A2.1.2).
module side_lattice() {
    n = floor(blade_l / 12);
    for (j = [0 : n - 1])
        translate([-1, wall + 4 + j * 12, floor_t + 3])
            cube([blade_w + 2, 7, blade_h]);
}

module stack_pegs(negative = false) {
    d = negative ? peg_d + 2 * peg_tol : peg_d;
    for (x = [blade_w * 0.2, blade_w * 0.8])
        for (y = [blade_l * 0.25, blade_l * 0.75])
            translate([x, y, negative ? -0.01 : blade_h])
                cylinder(d = d, h = peg_h + (negative ? 0.02 : 0));
}

module fan_mount() {
    // On the plug end, blowing along the row of readers.
    off = (fan_size - fan_screw_pitch) / 2;
    translate([blade_w / 2 - fan_size / 2, -wall, blade_h / 2 - fan_size / 2])
        for (a = [[off, off], [fan_size - off, off],
                  [off, fan_size - off], [fan_size - off, fan_size - off]])
            translate([a[0], wall + 1, a[1]])
                rotate([90, 0, 0]) cylinder(d = fan_screw_d, h = wall + 2);
}

module blade() {
    difference() {
        union() {
            cube([blade_w, blade_l, blade_h]);
            stack_pegs();
        }
        for (i = [0 : lanes - 1]) { lane_pocket(i); label_recess(i); }
        side_lattice();
        stack_pegs(negative = true);
        fan_mount();
    }
}

// -------------------------------------------------------------------- tray ---

module tray() {
    difference() {
        cube([hub_l + 2 * wall, hub_w + 2 * wall, tray_lip + wall]);
        translate([wall, wall, wall])
            cube([hub_l, hub_w, tray_lip + 1]);
        // Cable exits, both ends.
        for (y = [-1, hub_w + 2 * wall - 11])
            translate([-1, y + 6, wall + 2]) cube([hub_l + 2 * wall + 2, 12, tray_lip]);
        // Drain the tray floor: nothing here needs to be solid.
        for (x = [0 : 5]) for (y = [0 : 2])
            translate([wall + 8 + x * 15, wall + 8 + y * 14, -1])
                cylinder(d = 9, h = wall + 2);
    }
    // Sockets the blade's pegs drop into.
    for (x = [blade_w * 0.2, blade_w * 0.8])
        for (y = [blade_l * 0.25, blade_l * 0.75])
            translate([x + wall, y + wall, wall])
                difference() {
                    cylinder(d = peg_d + 2 * wall, h = peg_h + 1);
                    translate([0, 0, -0.01])
                        cylinder(d = peg_d + 2 * peg_tol, h = peg_h + 1.02);
                }
}

// ------------------------------------------------------------------ shroud ---

module shroud() {
    off = (fan_size - fan_screw_pitch) / 2;
    difference() {
        cube([fan_size, wall * 2, fan_size]);
        translate([fan_size / 2, -1, fan_size / 2])
            rotate([-90, 0, 0]) cylinder(d = fan_size - 6, h = wall * 2 + 2);
        for (a = [[off, off], [fan_size - off, off],
                  [off, fan_size - off], [fan_size - off, fan_size - off]])
            translate([a[0], -1, a[1]])
                rotate([-90, 0, 0]) cylinder(d = fan_screw_d, h = wall * 2 + 2);
    }
}

// -------------------------------------------------------------------- main ---

if (part == "blade")  blade();
else if (part == "tray")   tray();
else if (part == "shroud") shroud();
else {
    blade();
    translate([0, 0, -40]) tray();
    translate([blade_w + 10, 0, 0]) shroud();
}

// Print notes (A2.5.1): PETG, 0.2 mm layers, 3 walls, 15% infill. The lattice
// and the pockets are designed to print without supports in this orientation —
// blade floor down, pockets opening upward. PETG rather than PLA because the
// reader bodies get warm and a PLA blade will creep.
