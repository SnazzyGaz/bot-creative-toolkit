// Parametric phone stand: a base, a back rest tilted back at `angle`, a support wedge,
// a front lip that holds the phone, and a cable slot. All sizes in mm.
// Built as one side profile (Y = front to back, Z = up) extruded across the width.

width       = 80;    // [50:140] stand width
depth       = 90;    // [60:140] base depth, front to back
angle       = 65;    // [50:80] back rest angle from horizontal, degrees
rest_length = 100;   // [60:160] length of the back rest
thickness   = 6;     // [4:12] plate thickness
phone_depth = 12;    // [6:20] gap between lip and back rest (phone + case)
lip_height  = 14;    // [6:25] lip height above the base
cable_slot  = 12;    // [0:20] cable slot width, 0 for none

foot = thickness + phone_depth;              // where the back rest meets the base
dir  = [cos(angle), sin(angle)];             // up the back rest
nrm  = [sin(angle), -cos(angle)];            // through the back rest, towards the back
top  = [foot, 0] + rest_length * dir;

assert(top[0] + thickness < depth, "back rest overhangs the base: raise depth or angle");

module profile() {
    square([depth, thickness]);                                   // base
    square([thickness, thickness + lip_height]);                  // front lip
    polygon([[foot, 0], top, top + thickness * nrm,               // back rest
             [foot + thickness / sin(angle), 0]]);
    s = [foot, 0] + 0.6 * rest_length * dir;                      // support wedge
    polygon([[foot, 0], s, [depth, thickness], [depth, 0]]);
}

difference() {
    rotate([90, 0, 90]) linear_extrude(width) profile();
    if (cable_slot > 0) {
        translate([(width - cable_slot) / 2, -1, thickness / 2])  // groove in the base
            cube([cable_slot, foot + 1, thickness]);
        translate([(width - cable_slot) / 2, -1, -1])             // cut through the lip
            cube([cable_slot, thickness + 2, lip_height + thickness + 2]);
    }
}
