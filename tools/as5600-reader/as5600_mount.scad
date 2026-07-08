// as5600_mount.scad — parametric mount for the AS5600 encoder on the roto motor shaft.
//
// The AIR GAP IS A FIXED PRINTED DIMENSION — the sensor cradle is printed at a set
// height above the L-bracket mounting face, so bolting the holder to FIXED holes puts
// the board exactly `air_gap` above the magnet. No sliding/tensioning to set it.
//
// Three printed parts:
//   1) MAGNET CARRIER — a cap that grips the shaft tip (set screw) and holds the
//      diametric magnet centered on the axis, on the shaft end face.
//   2) SENSOR HOLDER  — a rigid bracket: fixed bolt holes to the L-bracket at the
//      bottom, board cradle (chip-down) printed at the exact gap height at the top.
//   3) GAP GAUGE      — a throwaway shim exactly `air_gap` thick: on assembly, set the
//      magnet-to-sensor gap against it to confirm the print is accurate, then remove.
//
// Frame: shaft axis = Z. L-bracket mounting face (foot bottom) = z 0. Magnet top face
// = z `mount_rise`. Board bottom = z `mount_rise + air_gap`.
//
// >>> MEASURE the [MEASURE] values against your parts, especially `mount_rise`. <<<

part = "assembly";        // "carrier" | "holder" | "gauge" | "assembly"

/* ---------- the fixed geometry that defines the gap ---------- */
mount_rise    = 22;       // [MEASURE] L-bracket face -> magnet top face, along the shaft axis
air_gap       = 1.8;      // target magnet-top -> board-bottom (chip sits ~1mm under the board;
                          //   effective magnet->die ~ air_gap - 1mm; AS5600 likes ~0.5-3mm)

/* ---------- shaft (rotating) ---------- */
shaft_d       = 12.7;     // [MEASURE] 1/2" tip diameter
shaft_engage  = 16;       // carrier grip depth on the shaft
shaft_fit     = 0.35;     // bore clearance (tune to your printer)

/* ---------- magnet (MUST be diametric) ---------- */
magnet_d      = 6.0;      // [MEASURE]
magnet_th     = 2.5;      // [MEASURE]
magnet_fit    = 0.15;
magnet_floor  = 1.0;      // plastic between shaft end and magnet (field passes through)
magnet_recess = 0.3;      // recess the magnet below the carrier top face

/* ---------- carrier body ---------- */
wall          = 3.2;
set_screw_d   = 3.2;      // M3 grub screw (self-taps into printed hole)
set_screw_z   = 8;

/* ---------- AS5600 board ---------- */
board_l       = 15.0;     // [MEASURE]
board_w       = 11.0;     // [MEASURE]
board_th      = 1.6;
board_fit     = 0.35;
chip_win      = 8;        // center window under the chip (open to the magnet), < board_w

/* ---------- sensor holder frame + column + L-bracket foot ---------- */
fr_wall       = 3.0;      // cradle wall around the board
lip           = 1.2;      // retaining lip over the board edges
col_w         = 12;       // column (vertical arm) cross-section
col_d         = 10;
foot_l        = 30;       // mounting foot footprint (against the L-bracket)
foot_w        = 22;
foot_th       = 5;
foot_hole_d   = 5.4;      // M5 clearance, FIXED holes (no slot)
foot_hole_sp  = 18;       // spacing between the two fixed holes

eps = 0.02;
$fn = 96;
carrier_h  = shaft_engage + magnet_floor + magnet_th;
board_bz   = mount_rise + air_gap;           // board bottom height above the foot
tip_z      = mount_rise - (magnet_th + magnet_floor) + magnet_recess;

// ===================================================================== //
module magnet_carrier() {
  difference() {
    cylinder(d = shaft_d + 2*wall, h = carrier_h);
    translate([0,0,-eps]) cylinder(d = shaft_d + shaft_fit, h = shaft_engage + eps);
    translate([0,0, carrier_h - magnet_th - magnet_recess])
      cylinder(d = magnet_d + magnet_fit, h = magnet_th + magnet_recess + eps);
    translate([0,0,set_screw_z]) rotate([0,90,0])
      cylinder(d = set_screw_d, h = shaft_d/2 + wall + eps);
  }
}

// board cradle, chip-down, bottom at z = board_bz (fixed = exact gap)
module board_cradle() {
  ol = board_l + 2*fr_wall;  ow = board_w + 2*fr_wall;
  translate([0,0,board_bz])
  difference() {
    translate([-ol/2,-ow/2,0]) cube([ol, ow, board_th + lip]);
    translate([-(board_l+board_fit)/2, -(board_w+board_fit)/2, -eps])
      cube([board_l+board_fit, board_w+board_fit, board_th + eps]);         // board pocket
    translate([-chip_win/2, -chip_win/2, -eps])
      cube([chip_win, chip_win, board_th + lip + 2*eps]);                   // window to magnet
    translate([-(board_l-2)/2, -(board_w-2)/2, board_th])
      cube([board_l-2, board_w-2, lip + eps]);                             // insertion relief
  }
}

module sensor_holder() {
  board_cradle();
  // vertical column from the foot up to the cradle (rigid — fixes the gap)
  hull() {
    translate([-(board_l/2+fr_wall), -col_w/2, board_bz]) cube([eps, col_w, board_th+lip]);
    translate([-(board_l/2+fr_wall)-6, -foot_w/2, 0]) cube([eps, foot_w, foot_th]);
  }
  translate([-(board_l/2+fr_wall)-6-col_d, 0, 0])
    linear_extrude(board_bz+board_th+lip) hull(){        // spine wall for stiffness
      translate([0,-col_w/2]) square([col_d, col_w]);
      translate([col_d, -col_w/4]) square([eps, col_w/2]); }
  // mounting foot with TWO FIXED holes (no slot)
  difference() {
    translate([-(board_l/2+fr_wall)-6-col_d-foot_l, -foot_w/2, 0]) cube([foot_l, foot_w, foot_th]);
    for (dy=[-foot_hole_sp/2, foot_hole_sp/2])
      translate([-(board_l/2+fr_wall)-6-col_d-foot_l/2, dy, -eps])
        cylinder(d = foot_hole_d, h = foot_th + 2*eps);
  }
}

// gap gauge: a shim exactly air_gap thick, with a slot to slip over the shaft/magnet
module gap_gauge() {
  gw = magnet_d + 10;
  difference() {
    translate([-gw/2, -gw/2, 0]) cube([gw, gw, air_gap]);
    translate([0,0,-eps]) cylinder(d = magnet_d + 1, h = air_gap + 2*eps);
    translate([-1.5, 0, -eps]) cube([3, gw, air_gap + 2*eps]);   // open slot to slide in
  }
}

// ---- reference-only preview geometry ----
module ghost_shaft()  { color("silver") translate([0,0, tip_z - 30]) cylinder(d = shaft_d, h = 30); }
module ghost_magnet() { color("red")    translate([0,0, mount_rise - magnet_th]) cylinder(d = magnet_d, h = magnet_th); }
module ghost_board()  { color("green")  translate([-board_l/2,-board_w/2, board_bz]) cube([board_l,board_w,board_th]); }
module ghost_bracket(){ color("#888")   translate([-(board_l/2+fr_wall)-6-col_d-foot_l-3, -foot_w/2-2, -6]) cube([foot_l+6, foot_w+4, 6]); }

if (part == "carrier")      translate([0,0,carrier_h]) rotate([180,0,0]) magnet_carrier();
else if (part == "holder")  sensor_holder();
else if (part == "gauge")   gap_gauge();
else {
  translate([0,0, mount_rise - (carrier_h - magnet_recess)]) magnet_carrier();
  ghost_magnet(); %ghost_shaft(); %ghost_board(); %ghost_bracket();
  sensor_holder();
}
