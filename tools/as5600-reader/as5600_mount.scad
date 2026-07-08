// as5600_mount.scad — parametric mount for the AS5600 encoder on the roto motor shaft.
//
// THE AIR GAP IS BUILT INTO THE SENSOR HOLDER, not the L-bracket. Four standoff bosses
// (matching the board's 4 corner holes) hold the AS5600 chip-side-down at exactly `air_gap`
// above the magnet, center open (no plastic between chip and magnet). The L-bracket only
// RETAINS the holder (fixed holes) — it never sets the gap.
//
// Three printed parts:
//   1) MAGNET CARRIER — set-screw cap; holds the 5x2 diametric magnet on the shaft end, on-axis.
//   2) SENSOR HOLDER  — ring + 4 standoff bosses at the board height (built-in gap) + arm to a
//      fixed-hole L-bracket foot.
//   3) GAP GAUGE      — shim exactly `air_gap` thick to confirm the gap on assembly.
//
// Frame: shaft axis = Z; magnet TOP face = z 0; board bottom (chip) = z `air_gap`;
//        L-bracket mounting face = z `-mount_rise`.
//
// >>> [MEASURE]: mount_rise, board_hole_sp, magnet is DIAMETRIC (poles across the dia). <<<

part = "assembly";        // "carrier" | "holder" | "gauge" | "assembly"

/* ---------- the gap (built into the holder bosses) ---------- */
air_gap       = 1.2;      // magnet top -> board bottom (chip). AS5600 + 5mm magnet: keep ~1-1.5mm.
mount_rise    = 22;       // [MEASURE] L-bracket face -> magnet plane, along the shaft axis

/* ---------- shaft (rotating) ---------- */
shaft_d       = 12.7;     // [MEASURE] 1/2" tip
shaft_engage  = 16;
shaft_fit     = 0.35;

/* ---------- magnet (5 x 2, MUST be diametric) ---------- */
magnet_d      = 5.0;
magnet_th     = 2.0;
magnet_fit    = 0.15;
magnet_floor  = 1.0;
magnet_recess = 0.3;

/* ---------- carrier body ---------- */
wall          = 3.2;
set_screw_d   = 3.2;
set_screw_z   = 8;

/* ---------- AS5600 board (23 x 23, chip centered, 4 corner holes) ---------- */
board_sz      = 23.0;
board_th      = 1.6;
board_hole_sp = 16.5;     // [MEASURE] corner mounting-hole spacing (square, both axes)
board_hole_d  = 3.2;      // board mounting-hole diameter
chip_win      = 12;       // central open window (chip sees magnet) — clears the SOIC-8

/* ---------- standoffs / ring / arm / foot ---------- */
boss_d        = 6.5;      // standoff boss OD at each corner hole
boss_screw_d  = 2.9;      // self-tap for M3 (or clearance for a nut)
ring_th       = 3.0;      // ring thickness (below the magnet plane, around the carrier)
carrier_clear = 1.2;      // radial clearance so the carrier spins free in the ring
arm_w         = 12;
arm_th        = 6;
foot_l        = 30;
foot_w        = 22;
foot_th       = 5;
foot_hole_d   = 5.4;      // M5 clearance, FIXED holes
foot_hole_sp  = 18;

eps = 0.02;  $fn = 96;
carrier_h  = shaft_engage + magnet_floor + magnet_th;
carrier_od = shaft_d + 2*wall;
ring_bore  = carrier_od + 2*carrier_clear;
hs         = board_hole_sp/2;
tip_z      = -(magnet_th + magnet_floor) + magnet_recess;

// ===================================================================== //
module magnet_carrier() {
  difference() {
    cylinder(d = carrier_od, h = carrier_h);
    translate([0,0,-eps]) cylinder(d = shaft_d + shaft_fit, h = shaft_engage + eps);
    translate([0,0, carrier_h - magnet_th - magnet_recess])
      cylinder(d = magnet_d + magnet_fit, h = magnet_th + magnet_recess + eps);
    translate([0,0,set_screw_z]) rotate([0,90,0])
      cylinder(d = set_screw_d, h = shaft_d/2 + wall + eps);
  }
}

module sensor_holder() {
  // ring around the carrier top, at/just below the magnet plane
  translate([0,0,-ring_th]) difference() {
    hull() for (dx=[-1,1], dy=[-1,1]) translate([dx*hs, dy*hs, 0]) cylinder(d = boss_d, h = ring_th);
    translate([0,0,-eps]) cylinder(d = ring_bore, h = ring_th + 2*eps);
  }
  // four standoff bosses: the BUILT-IN gap. Top at z = air_gap (board bottom, chip-down)
  for (dx=[-1,1], dy=[-1,1]) translate([dx*hs, dy*hs, -ring_th]) difference() {
    cylinder(d = boss_d, h = ring_th + air_gap);
    translate([0,0, ring_th + air_gap - 5]) cylinder(d = boss_screw_d, h = 5 + eps);   // screw pocket
  }
  // arm + fixed-hole foot down to the L-bracket (retention only)
  ax = hs + boss_d/2;
  hull() {
    translate([-ax, -arm_w/2, air_gap-arm_th]) cube([eps, arm_w, arm_th]);
    translate([-ax-6, -arm_w/2, -mount_rise]) cube([eps, arm_w, arm_th]);
  }
  translate([-ax-6-arm_th, 0, 0]) linear_extrude(air_gap+eps) hull(){        // brace to the ring
    translate([0,-arm_w/2]) square([arm_th, arm_w]);
    translate([arm_th, -arm_w/4]) square([eps, arm_w/2]); }
  difference() {
    translate([-ax-6-foot_l, -foot_w/2, -mount_rise]) cube([foot_l, foot_w, foot_th]);
    for (dy=[-foot_hole_sp/2, foot_hole_sp/2])
      translate([-ax-6-foot_l/2, dy, -mount_rise-eps]) cylinder(d = foot_hole_d, h = foot_th + 2*eps);
  }
}

module gap_gauge() {
  gw = magnet_d + 12;
  difference() {
    translate([-gw/2,-gw/2,0]) cube([gw, gw, air_gap]);
    translate([0,0,-eps]) cylinder(d = magnet_d + 1, h = air_gap + 2*eps);
    translate([-1.5,0,-eps]) cube([3, gw, air_gap + 2*eps]);
  }
}

// ---- reference-only preview geometry ----
module ghost_shaft()  { color("silver") translate([0,0, tip_z-30]) cylinder(d=shaft_d, h=30); }
module ghost_magnet() { color("red")    translate([0,0,-magnet_th]) cylinder(d=magnet_d, h=magnet_th); }
module ghost_board()  { color("green")  translate([-board_sz/2,-board_sz/2, air_gap]) cube([board_sz,board_sz,board_th]); }
module ghost_brk()    { color("#888")   translate([-hs-boss_d/2-6-foot_l-3, -foot_w/2-2, -mount_rise-6]) cube([foot_l+6, foot_w+4, 6]); }

if (part == "carrier")      translate([0,0,carrier_h]) rotate([180,0,0]) magnet_carrier();
else if (part == "holder")  sensor_holder();
else if (part == "gauge")   gap_gauge();
else {
  translate([0,0, -(carrier_h - magnet_recess)]) magnet_carrier();
  ghost_magnet(); %ghost_shaft(); %ghost_board(); %ghost_brk();
  sensor_holder();
}
