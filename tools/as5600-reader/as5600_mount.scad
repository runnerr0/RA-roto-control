// as5600_mount.scad — AS5600 encoder mount for the roto shaft. NESTED / self-spacing design.
//
// The two printed parts SET THE GAP BY NESTING TOGETHER — no external reference:
//   - MAGNET CARRIER grips the shaft, holds the 5x2 diametric magnet on-axis on a raised PILOT,
//     and has a SHOULDER (the step where the pilot meets the wider body).
//   - SENSOR HOLDER cups over the pilot (bore = running clearance) and its hub bottom SEATS ON the
//     shoulder. That seat is the spacer: it fixes the board exactly `air_gap` above the magnet.
//     The carrier spins under it; they rub at the seat (slow roto -> fine; a thrust washer/bearing
//     can drop onto the pilot later). The board rides on the holder because the holder rides the
//     carrier, so the gap stays constant even if the shaft wobbles.
//
// The L-BRACKET only stops the holder from spinning (anti-rotation ear) — use any spare bracket.
//
// Frame: shaft axis = Z; magnet TOP face = z 0; carrier shoulder = z -pilot_h; board face = z air_gap.

part = "assembly";        // "carrier" | "holder" | "gauge" | "assembly"

/* ---------- the gap (set by the nested seat) ---------- */
air_gap       = 2.5;      // magnet top -> board chip-side face. Chip body pokes ~1.5mm in -> die ~1.3mm off.

/* ---------- shaft (rotating) ---------- */
shaft_d       = 12.7;     // [MEASURE] 1/2" tip
shaft_engage  = 16;
shaft_fit     = 0.35;
wall          = 3.2;
set_screw_d   = 3.2;      // M3 grub
set_screw_z   = 8;

/* ---------- magnet (5 x 2 DIAMETRIC) ---------- */
magnet_d      = 5.0;
magnet_th     = 2.0;
magnet_fit    = 0.15;
magnet_recess = 0.3;

/* ---------- register pilot + shoulder (the spacer interface) ---------- */
pilot_d       = 11.0;     // pilot the holder cups over (> magnet, gives a clean register)
pilot_h       = 7.0;      // pilot height above the shoulder (magnet pocket + register length)
hub_fit       = 0.4;      // radial running clearance: holder bore over pilot
hub_wall      = 2.6;      // holder hub wall

/* ---------- AS5600 board (23 x 23, chip centered, holes 16mm c-c, 3.5mm) ---------- */
board_sz      = 23.0;
board_th      = 1.6;
board_hole_sp = 16.0;     // corner mounting-hole spacing
board_hole_d  = 3.5;
boss_screw_d  = 2.9;      // self-tap M3 into the board bosses

/* ---------- anti-rotation ear (to a spare L-bracket) ---------- */
ear_len       = 26;
ear_w         = 12;
ear_th        = 5;
ear_hole_d    = 5.4;      // M5 clearance

eps = 0.02;  $fn = 96;
carrier_od = shaft_d + 2*wall;
body_h     = shaft_engage;                 // native carrier body height (grips the shaft)
carrier_h  = body_h + pilot_h;             // native total
hub_bore   = pilot_d + 2*hub_fit;
hub_od     = pilot_d + 2*hub_fit + 2*hub_wall;
hs         = board_hole_sp/2;
plate_d    = board_sz*sqrt(2)*0.5 + 3;     // disc big enough to reach the corner bosses
plate_th   = 3.0;

// ================= MAGNET CARRIER (native: base z 0, pilot up) ================= //
module magnet_carrier() {
  difference() {
    union() {
      cylinder(d = carrier_od, h = body_h);                       // body (shoulder = top face)
      translate([0,0,body_h]) cylinder(d = pilot_d, h = pilot_h); // register pilot
    }
    translate([0,0,-eps]) cylinder(d = shaft_d + shaft_fit, h = shaft_engage + eps);         // shaft bore
    translate([0,0, carrier_h - magnet_th - magnet_recess])
      cylinder(d = magnet_d + magnet_fit, h = magnet_th + magnet_recess + eps);              // magnet pocket
    translate([0,0,set_screw_z]) rotate([0,90,0]) cylinder(d = set_screw_d, h = carrier_od/2 + eps); // set screw
  }
}

// ================= SENSOR HOLDER (assembly coords: seats at z -pilot_h) ================= //
module sensor_holder() {
  hub_bot = -pilot_h;                       // hub bottom rests on the carrier shoulder
  plate_bot = air_gap - plate_th;
  // hub tube (open bore so the chip sees the magnet)
  translate([0,0,hub_bot]) difference() {
    cylinder(d = hub_od, h = plate_bot - hub_bot + eps);
    translate([0,0,-eps]) cylinder(d = hub_bore, h = plate_bot - hub_bot + 3*eps);
  }
  // board plate: disc + central window + 4 corner bosses (board sits chip-down at z air_gap)
  difference() {
    union() {
      translate([0,0,plate_bot]) cylinder(d = plate_d, h = plate_th);
      for (dx=[-1,1], dy=[-1,1]) translate([dx*hs, dy*hs, plate_bot]) cylinder(d = 6.5, h = plate_th);
    }
    translate([0,0,plate_bot-eps]) cylinder(d = hub_bore, h = plate_th + 2*eps);             // chip window
    for (dx=[-1,1], dy=[-1,1]) translate([dx*hs, dy*hs, air_gap-4]) cylinder(d = boss_screw_d, h = 4+eps); // board screws
  }
  // anti-rotation ear out to a spare L-bracket (retention only, NOT the gap)
  difference() {
    hull() {
      translate([plate_d/2-2, -ear_w/2, plate_bot]) cube([eps, ear_w, plate_th]);
      translate([plate_d/2-2+ear_len, -ear_w/2, plate_bot]) cube([ear_th, ear_w, plate_th]);
    }
    translate([plate_d/2-2+ear_len-ear_th/2, 0, plate_bot-eps]) cylinder(d = ear_hole_d, h = plate_th + 2*eps);
  }
}

module gap_gauge() {  // shim to confirm the seated gap
  gw = pilot_d + 10;
  difference() {
    translate([-gw/2,-gw/2,0]) cube([gw, gw, air_gap]);
    translate([0,0,-eps]) cylinder(d = pilot_d + 0.6, h = air_gap + 2*eps);
    translate([-1.5,0,-eps]) cube([3, gw, air_gap + 2*eps]);
  }
}

// ---- preview ghosts ----
module ghost_magnet() { color("red")   translate([0,0,-magnet_th]) cylinder(d=magnet_d, h=magnet_th); }
module ghost_shaft()  { color("silver")translate([0,0,-carrier_h-20]) cylinder(d=shaft_d, h=carrier_h+20); }
module ghost_board()  { color("green") translate([-board_sz/2,-board_sz/2, air_gap]) cube([board_sz,board_sz,board_th]); }

if (part == "carrier")      magnet_carrier();                              // print: shaft-bore down, pilot up
else if (part == "holder")  rotate([180,0,0]) translate([0,0,-air_gap]) sensor_holder();  // print: board-plate flat down, hub up
else if (part == "gauge")   gap_gauge();                                   // print: flat
else {
  translate([0,0,-carrier_h]) magnet_carrier();   // magnet top -> z 0
  ghost_magnet(); %ghost_shaft(); %ghost_board();
  sensor_holder();
}
