#!/usr/bin/env python3
"""
gen_col_tb.py — column testbench generator (node-aware), called by run_col.sh.

Ports the verified 20nm column TB (array_spice 20_col_spice tb_template.sp)
to any node and any row count, keeping the original slow 10 ns/op cadence
(wide windows — BL swings and sensing settle fully at every size), and
extends the 4-op sequence to 6 ops so one run yields flip vs no-flip write
energy:

   t(ns)  0-3    idle      precharge ON, BL/BL_bar at VDD
   3-13   WR0    write 0   (initializes the cell — energy reported but
                            not a dataset target: prior state unknown)
  13-23   RD0    read 0    expect OUT low at the sample point
  23-33   WR1f   write 1   BIT-FLIP write (0 -> 1)
  33-43   RD1    read 1    expect OUT high
  43-53   WR1s   write 1   WRITE-SAME (no flip; 1 -> 1)
  53-63   RD1b   read 1    expect OUT high (cell survived the same-write)
  63-100  idle             leakage window 90 - 99 ns (the long idle matters:
                           at 512 rows the supply current needs ~25 ns after
                           the last restore to settle to true leakage —
                           measuring at 65 ns overstates it up to 12x)

Within a write op starting at T: pre_en release @T, write @T+1,
wl pulse @T+2..T+5, write off @T+6, precharge restore @T+7 — the restore
recharge current is part of that op's energy, so each op window is the
full [T, T+10].  Within a read op: pre_en release @T, wl @T+1..T+6,
sense window @T+4..T+7, OUT sampled @T+5.5, restore @T+8.

Energy test points: every DUT power sink (write driver, sense amp, output
buffer, precharge PMOS source, cell pull-ups) hangs off the single VDD
port, so per-op energy = INTEG of -v(VDD)*i(VVDD) over the op window and
leakage = AVG of the same in the quiet tail.  The data input flips at
T+0.5 of the flip-write op so the write driver's input-inverter switching
is attributed to flip-write energy.

Only wl[0] is exercised; all other wl[k] are tied to ground directly in
the DUT port list (no per-row source needed at 512 rows).  The other rows
still load BL/BL_bar with their pass-gate junctions — that is the row-count
scaling being measured.

Usage (normally via run_col.sh):
  gen_col_tb.py <extracted.sp> --cellname C --vdd V --temp T --node NAME \
                [--ba <cell>.spef] [--hdl <va-file>] -o tb.sp
"""
import argparse
import re
import sys

CANON = {"BL", "BL_bar", "data", "write", "VSS", "OUT", "VDD",
         "pre_en", "sen_en", "sen_en_bar"}


def die(msg):
    sys.exit(f"gen_col_tb: error: {msg}")


def parse_ports(sp_path, cellname):
    text = re.sub(r"\n\+", " ", open(sp_path).read())
    for line in text.splitlines():
        t = line.split()
        if t and t[0].upper() == ".SUBCKT" and t[1] == cellname:
            return t[2:]
    die(f"no .SUBCKT {cellname} in {sp_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sp")
    ap.add_argument("--cellname", required=True)
    ap.add_argument("--vdd", type=float, required=True)
    ap.add_argument("--temp", type=float, required=True)
    ap.add_argument("--node", required=True)
    ap.add_argument("--ba", default="")
    ap.add_argument("--hdl", default="")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    ports = parse_ports(a.sp, a.cellname)
    wl = sorted(int(m.group(1))
                for m in (re.fullmatch(r"wl\[(\d+)\]", p) for p in ports)
                if m)
    rows = len(wl)
    if not rows or wl != list(range(rows)):
        die(f"wl ports not contiguous from 0: {wl}")
    bad = [p for p in ports if p not in CANON
           and not re.fullmatch(r"wl\[\d+\]", p)]
    if bad:
        die(f"unknown DUT ports: {bad}")

    # TB net per DUT port; unused wordlines go straight to ground
    def net(p):
        if re.fullmatch(r"wl\[\d+\]", p) and p != "wl[0]":
            return "0"
        return p
    nets = [net(p) for p in ports]
    # wrap for HSPICE line-length limits (512-row columns have 500+ ports)
    xdut = ""
    line = "Xdut"
    for n in nets + [a.cellname]:
        if len(line) + 1 + len(n) > 80:
            xdut += line + "\n"
            line = "+"
        line += " " + n
    xdut += line

    V = a.vdd
    hdl = f".hdl './models/{a.hdl}'" if a.hdl else \
        "* (native .model card — no Verilog-A to load)"
    ba = f".option ba_file='./{a.ba}'" if a.ba else \
        "* pre-layout run — no parasitic back-annotation"

    def pwl(pairs):
        return "PWL(\n" + "\n".join(f"+ {t:g}n {v:g}" for t, v in pairs) \
               + " )"

    def edges(times_up_down, v_hi, v0=0.0, tend=100.0):
        """times_up_down = [(t_rise, t_fall), ...] pulses from v0 to v_hi."""
        pts = [(0.0, v0)]
        for tr, tf in times_up_down:
            pts += [(tr, v0), (tr + 0.01, v_hi), (tf, v_hi), (tf + 0.01, v0)]
        pts.append((tend, v0))
        return pwl(pts)

    # op start times: WR0 3, RD0 13, WR1f 23, RD1 33, WR1s 43, RD1b 53
    WR = [3.0, 23.0, 43.0]
    RD = [13.0, 33.0, 53.0]
    pre_pulses = [(t, t + 7) for t in WR] + [(t, t + 8) for t in RD]
    src = {
        "pre_en": edges(sorted(pre_pulses), V),
        "write": edges([(t + 1, t + 6) for t in WR], V),
        "wl[0]": edges(sorted([(t + 2, t + 5) for t in WR]
                              + [(t + 1, t + 6) for t in RD]), V),
        "sen_en": edges([(t + 4, t + 7) for t in RD], V),
        # data: 0 through WR0/RD0, flips inside the flip-write window
        "data": pwl([(0, 0), (23.5, 0), (23.51, V), (100, V)]),
    }
    # active-low sense enable = complement of sen_en
    src["sen_en_bar"] = edges([(t + 4, t + 7) for t in RD], 0.0, v0=V)

    ops = [("wr0", 3, "write 0 (init — prior state unknown)"),
           ("rd0", 13, "read 0"),
           ("wr1_flip", 23, "write 1, bit-flip 0->1"),
           ("rd1", 33, "read 1"),
           ("wr1_same", 43, "write 1, no flip 1->1"),
           ("rd1b", 53, "read 1 (after same-write)")]
    emeas = "\n".join(
        f".measure tran e_{name}_J INTEG par('-v(VDD)*i(VVDD)') "
        f"from={t}n to={t + 10}n  $ {desc}"
        for name, t, desc in ops)

    tb = f"""* ============================================================
* Testbench: {a.cellname} column ({rows} rows) — {a.node}  VDD={V}V
* Generated by run_col.sh / gen_col_tb.py — do not edit directly.
* Sequence (10 ns/op): WR0 / RD0 / WR1(flip) / RD1 / WR1(same) / RD1b,
* leakage window 90-99 ns.  See gen_col_tb.py header for timing detail.
* ============================================================

.title {a.cellname} column write/read test ({a.node}, {rows} rows)

{hdl}
.include './models/nmos1.inc'
.include './models/pmos1.inc'

* -- Cell netlist (bulk-tied copy) ------------------------------------
.include './{a.cellname}.sp'

* -- Power supplies ----------------------------------------------------
VVDD VDD 0 {V}
VVSS VSS 0 0

* -- Control / data sources -------------------------------------------
Vpre_en pre_en 0 {src['pre_en']}

Vwrite write 0 {src['write']}

Vdata data 0 {src['data']}

Vwl0 wl[0] 0 {src['wl[0]']}

Vsen_en sen_en 0 {src['sen_en']}

Vsen_en_bar sen_en_bar 0 {src['sen_en_bar']}

* -- Initial conditions: bitlines precharged --------------------------
.ic v(BL)={V} v(BL_bar)={V}

* -- DUT (nets in the cell's own port order; wl[1..{rows - 1}] grounded) --
{xdut}

.tran 1p 100n

.probe tran v(BL) v(BL_bar) v(OUT) v(wl[0]) v(pre_en) v(write)
+           v(data) v(sen_en) v(sen_en_bar)

* -- Energy per op window (J; sign: current OUT of VVDD is negative) --
{emeas}
.measure tran p_leak_W AVG par('-v(VDD)*i(VVDD)') from=90n to=99n

* -- Functional samples (OUT valid only while the sense amp is on) ----
.measure tran out_rd0  find v(OUT) at=18.5n  $ expect ~0
.measure tran out_rd1  find v(OUT) at=38.5n  $ expect ~VDD
.measure tran out_rd1b find v(OUT) at=58.5n  $ expect ~VDD
.measure tran bl_wr0   find v(BL)     at=7.9n   $ WD held BL low thru wl pulse
.measure tran blb_wr1  find v(BL_bar) at=27.9n  $ WD held BL_bar low
.measure tran bl_dev_rd0 find v(BL) at=17n  $ BL developed at sense fire (RD0)

* -- WD drive check: BL(_bar) discharge time under full column load ----
.measure tran t_bl_fall_wr0  trig v(write)  val='{V / 2}' rise=1 td=3n
+                            targ v(BL)     val='{0.1 * V}' fall=1 td=3n
.measure tran t_blb_fall_wr1 trig v(write)  val='{V / 2}' rise=1 td=23n
+                            targ v(BL_bar) val='{0.1 * V}' fall=1 td=23n

.temp {a.temp:g}
{ba}
.option post ingold accurate numdgt=6

.end
"""
    with open(a.out, "w") as f:
        f.write(tb)
    print(f"gen_col_tb: {a.out}  ({rows} rows, VDD={V}V, "
          f"{'PEX' if a.ba else 'pre-layout'})")


if __name__ == "__main__":
    main()
