#!/usr/bin/env python3
"""
gen_array_tb.py — array testbench generator (node-aware), called by run_array.sh.

Extends the validated column TB (gen_col_tb.py) to array_X<S>_<R>x<C> cells:
rows and cols are read from the extracted netlist's port list, all C columns
are stimulated together (one word per op), and the data pattern is controlled
by --toggle-rate so one run yields the four dataset energies at a chosen
write-toggle activity.

Stimulus (10 ns/op cadence, identical intra-op edge timing to the column TB):

   t(ns)  0-3     idle       precharge ON, all BL/BL_bar at VDD
   3-13   WR1i    write 1    all columns (initializes cells — energy reported
                             but not a dataset target: prior state unknown)
  13-23   RD11    read       all cells hold 1 -> READ ENERGY (precharge 1->1):
                             the BL side stays at VDD, BL_bar discharges
  23-33   WRs     write 1    all columns rewrite their value, ZERO flips
                             -> SAME-VALUE WRITE ENERGY
  33-43   WRt     write      n_t = round(rate*C) columns flip 1->0, the other
                             C-n_t rewrite 1 -> TOGGLE WRITE ENERGY at the
                             requested toggle rate
  43-53   WR0f    write 0    all columns (flips the remaining C-n_t so the
                             final read is uniform; aux energy, reported)
  53-63   RD10    read       all cells hold 0 -> READ ENERGY (precharge 1->0):
                             the BL side discharges from VDD to 0
  63-100  idle               leakage window 90-99 ns (settled tail — measuring
                             earlier overstates leakage at large row counts)

Within a write op starting at T: pre_en release @T, write @T+1, wl pulse
@T+2..T+5, write off @T+6, precharge restore @T+7 — the restore recharge
current is part of that op's energy, so every op window is the full [T,T+10].
Within a read op: pre_en release @T, wl @T+1..T+6, sense @T+4..T+7, OUT
sampled @T+5.5, restore @T+8.

Toggling columns are data[0..n_t-1]; their data input falls at T+0.5 of the
toggle-write op so the write-driver input-inverter switching is attributed to
toggle-write energy (same convention as the column TB).  Non-toggling columns'
data falls at T+0.5 of the WR0f op instead.

Measurement locations: every DUT power sink (write drivers, sense amps,
output buffers, precharge PMOS, cell pull-ups, all columns) hangs off the
single VDD port, so per-op energy = INTEG of -v(VDD)*i(VVDD) over the op
window and leakage = AVG of the same in the quiet tail.  Functional samples:
v(OUT[c]) for every column at both read sample points, plus BL/BL_bar level
checks during the write ops.  Only wl[0] is exercised; wl[1..R-1] are tied
to ground in the DUT port list — the idle rows still load the bitlines,
which is the row-count scaling being measured.

Read/write delay (all at the far column C-1 — it sees the wordline last
through the post-layout WL RC, so it is the worst case):
  t_rd_wl_out  wl[0] 50% rise -> OUT[C-1] 50% fall in the RD(1->0) op —
               the read access time (stored 0, output leaves precharge-1).
               When the bitline path alone is slow the fixed sen_en at
               wl+3ns bounds this number (see t_rd_sense).
  t_rd_bl_dev  wl[0] 50% rise -> |BL_bar - BL| differential reaching
               0.1*VDD — the schedule-independent array-speed component
               (bitline cap x cell read current).
  t_rd_sense   sen_en 50% rise -> OUT[C-1] 50% fall.  NEGATIVE when the
               cell discharged the bitline past the buffer threshold before
               the sense amp fired (small arrays) — then the sense amp only
               assists and t_rd_wl_out is schedule-free.
  t_wr_bl      write 50% rise -> BL[C-1] falling to 0.1*VDD — the
               write-driver bitline drive time (what WD sizing controls).
  t_wr_cell    wl[0] 50% rise -> cell internal Q falling through 50% —
               the true write event: the moment the cell's feedback has
               flipped and WL could close.  Q is auto-located from the
               extracted netlist (names like N32 change every extraction):
               it is the non-bitline channel terminal of the access
               transistor whose gate is wl[0] and whose other terminal is
               BL[C-1]; probed as v(Xdut.<node>).
  t_wr_total   t_wr_bl + t_wr_cell — conservative self-timed write time
               (the TB fires WD 1 ns before WL, so the phases are cleanly
               sequential; a real macro may overlap them).
Write delay is measured on a real 1->0 flip: in WRtoggle when all columns
toggle (n_t = C), otherwise in WR0fill where column C-1 flips.  WRsame has
no flip (write delay undefined there) and WR1init starts from an unknown
power-up state.  The bitline re-settle after the cell's back-injection bump
is NOT used as the write criterion: with a strong WD the bump is millivolts
and thresholding it is numerically fragile — the Q flip is the event.

Usage (normally via run_array.sh):
  gen_array_tb.py <extracted.sp> --cellname A --vdd V --temp T --node NAME \
                  [--toggle-rate 1.0] [--ba <cell>.spef] [--hdl <va>] -o tb.sp
"""
import argparse
import re
import sys

SHARED = {"write", "VSS", "VDD", "pre_en", "sen_en", "sen_en_bar"}
PER_COL = ("data", "OUT", "BL", "BL_bar")


def die(msg):
    sys.exit("gen_array_tb: error: %s" % msg)


def parse_ports(sp_path, cellname):
    text = re.sub(r"\n\+", " ", open(sp_path).read())
    for line in text.splitlines():
        t = line.split()
        if t and t[0].upper() == ".SUBCKT" and t[1] == cellname:
            return t[2:]
    die("no .SUBCKT %s in %s" % (cellname, sp_path))


def find_q_node(sp_path, cellname, col):
    """Internal storage node Q of the cell at (row 0, col <col>).

    The extracted netlist is flat with anonymized internal names (N32, ...)
    that change every extraction, but the access transistor is unambiguous:
    it is the only device whose gate is wl[0] and whose channel touches
    BL[<col>] — its other channel terminal is Q.  (The write-driver pass
    gates on BL are gated by 'write', precharge by 'pre_en', and the sense
    pair by the opposite bitline, so the gate==wl[0] filter is exact.)"""
    text = re.sub(r"\n\+", " ", open(sp_path).read())
    bl = "BL[%d]" % col
    inside = False
    hits = []
    for line in text.splitlines():
        t = line.split()
        if not t:
            continue
        u = t[0].upper()
        if u == ".SUBCKT":
            inside = (len(t) > 1 and t[1] == cellname)
        elif u == ".ENDS":
            inside = False
        elif inside and u[0] == "M" and len(t) >= 5:
            d, g, s = t[1], t[2], t[3]
            if g == "wl[0]":
                if d == bl and s != bl:
                    hits.append(s)
                elif s == bl and d != bl:
                    hits.append(d)
    if len(hits) != 1:
        die("cannot locate storage node Q of (row 0, col %d): access "
            "transistor gate=wl[0] channel=%s matched %s" % (col, bl, hits))
    return hits[0]


def indexed(ports, base):
    """Sorted indices of ports named base[i]; die unless contiguous from 0."""
    idx = sorted(int(m.group(1)) for m in
                 (re.fullmatch(re.escape(base) + r"\[(\d+)\]", p)
                  for p in ports) if m)
    if not idx or idx != list(range(len(idx))):
        die("%s[*] ports not contiguous from 0: %s" % (base, idx))
    return len(idx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sp")
    ap.add_argument("--cellname", required=True)
    ap.add_argument("--vdd", type=float, required=True)
    ap.add_argument("--temp", type=float, required=True)
    ap.add_argument("--node", required=True)
    ap.add_argument("--toggle-rate", type=float, default=1.0,
                    help="fraction of columns that flip 1->0 in the "
                         "toggle-write op (default 1.0 = whole word flips)")
    ap.add_argument("--ba", default="")
    ap.add_argument("--hdl", default="")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    ports = parse_ports(a.sp, a.cellname)
    rows = indexed(ports, "wl")
    cols = indexed(ports, "data")
    for base in PER_COL[1:]:
        n = indexed(ports, base)
        if n != cols:
            die("%s[*] count %d != data[*] count %d" % (base, n, cols))
    known = set(SHARED)
    bad = [p for p in ports if p not in known
           and not re.fullmatch(r"(wl|data|OUT|BL|BL_bar)\[\d+\]", p)]
    if bad:
        die("unknown DUT ports: %s" % bad)

    if not (0.0 <= a.toggle_rate <= 1.0):
        die("--toggle-rate must be in [0,1] (got %g)" % a.toggle_rate)
    n_t = int(round(a.toggle_rate * cols))
    rate = n_t / float(cols)

    # TB net per DUT port; unused wordlines go straight to ground
    def net(p):
        if re.fullmatch(r"wl\[\d+\]", p) and p != "wl[0]":
            return "0"
        return p
    xdut = ""
    line = "Xdut"
    for n in [net(p) for p in ports] + [a.cellname]:
        if len(line) + 1 + len(n) > 80:
            xdut += line + "\n"
            line = "+"
        line += " " + n
    xdut += line

    V = a.vdd
    hdl = ".hdl './models/%s'" % a.hdl if a.hdl else \
        "* (native .model card — no Verilog-A to load)"
    ba = ".option ba_file='./%s'" % a.ba if a.ba else \
        "* pre-layout run — no parasitic back-annotation"

    def pwl(pairs):
        return "PWL(\n" + "\n".join("+ %gn %g" % (t, v) for t, v in pairs) \
               + " )"

    def edges(times_up_down, v_hi, v0=0.0, tend=100.0):
        pts = [(0.0, v0)]
        for tr, tf in times_up_down:
            pts += [(tr, v0), (tr + 0.01, v_hi), (tf, v_hi), (tf + 0.01, v0)]
        pts.append((tend, v0))
        return pwl(pts)

    # op start times
    WR = [3.0, 23.0, 33.0, 43.0]   # WR1i, WRsame, WRtoggle, WR0fill
    RD = [13.0, 53.0]              # RD 1->1, RD 1->0
    src = {
        "pre_en": edges(sorted([(t, t + 7) for t in WR]
                               + [(t, t + 8) for t in RD]), V),
        "write": edges([(t + 1, t + 6) for t in WR], V),
        "wl[0]": edges(sorted([(t + 2, t + 5) for t in WR]
                              + [(t + 1, t + 6) for t in RD]), V),
        "sen_en": edges([(t + 4, t + 7) for t in RD], V),
        "sen_en_bar": edges([(t + 4, t + 7) for t in RD], 0.0, v0=V),
    }
    ctrl = "\n\n".join("V%s %s 0 %s" % (name.replace("[0]", "0"), name, w)
                       for name, w in src.items())

    # data[c]: 1 from t=0; toggling columns fall inside the toggle-write
    # window (33.5), the rest inside the fill-write window (43.5)
    data_src = []
    for c in range(cols):
        t_fall = 33.5 if c < n_t else 43.5
        role = "TOGGLES 1->0 in WRt" if c < n_t else "holds 1 until WR0f"
        data_src.append("* data[%d]: %s\nVdata%d data[%d] 0 %s"
                        % (c, role, c, c,
                           pwl([(0, V), (t_fall, V), (t_fall + 0.01, 0),
                                (100, 0)])))

    ic = " ".join("v(BL[%d])=%g v(BL_bar[%d])=%g" % (c, V, c, V)
                  for c in range(cols))
    ic_lines = ".ic"
    out_ic = ""
    for tok in ic.split():
        if len(ic_lines) + 1 + len(tok) > 78:
            out_ic += ic_lines + "\n"
            ic_lines = "+"
        ic_lines += " " + tok
    out_ic += ic_lines

    ops = [("wr1_init", 3, "write 1 all cols (init — prior state unknown)"),
           ("rd_1to1", 13, "READ, precharge 1->1 (all cells read 1)"),
           ("wr_same", 23, "WRITE same value, zero flips"),
           ("wr_toggle", 33, "WRITE, %d/%d cols flip 1->0" % (n_t, cols)),
           ("wr0_fill", 43, "write 0 all cols (aux; flips remaining %d)"
            % (cols - n_t)),
           ("rd_1to0", 53, "READ, precharge 1->0 (all cells read 0)")]
    emeas = "\n".join(
        ".measure tran e_%s_J INTEG par('-v(VDD)*i(VVDD)') "
        "from=%dn to=%dn  $ %s" % (name, t, t + 10, desc)
        for name, t, desc in ops)

    # per-column functional samples at both read points
    fmeas = "\n".join(
        ".measure tran out_rd1_c%d find v(OUT[%d]) at=18.5n  $ expect ~VDD\n"
        ".measure tran out_rd0_c%d find v(OUT[%d]) at=58.5n  $ expect ~0"
        % (c, c, c, c) for c in range(cols))
    # BL-side write checks: same-write pulls BL_bar low everywhere; in the
    # toggle op a flipping column pulls BL low, a holding column BL_bar low
    blm = [".measure tran blb_wrs_c0 find v(BL_bar[0]) at=27.9n"
           "  $ WD held BL_bar low (same-write)"]
    if n_t:
        blm.append(".measure tran bl_wrt_c0 find v(BL[0]) at=37.9n"
                   "  $ toggling col: WD held BL low")
    if n_t < cols:
        blm.append(".measure tran blb_wrt_c%d find v(BL_bar[%d]) at=37.9n"
                   "  $ holding col: WD held BL_bar low"
                   % (cols - 1, cols - 1))
    blmeas = "\n".join(blm)

    # -- read/write delay measures, all at the far column (worst-case WL RC)
    cf = cols - 1
    q_far = find_q_node(a.sp, a.cellname, cf)
    half = "0.5*%g" % V
    tenth = "0.1*%g" % V
    # write delay needs a real 1->0 flip at col C-1: WRtoggle only when the
    # whole word toggles, otherwise WR0fill (which flips cols n_t..C-1)
    wr_w = 33.0 if n_t == cols else 43.0
    wr_op = "WRtoggle" if n_t == cols else "WR0fill"
    dm = [
        "* read: RD(1->0) op @53n at col %d — stored 0, OUT leaves "
        "precharge-1" % cf,
        ".measure tran t_rd_wl_out trig v(wl[0]) val='%s' rise=1 td=53n\n"
        "+ targ v(OUT[%d]) val='%s' fall=1 td=53n  $ read access time"
        % (half, cf, half),
        ".measure tran t_rd_bl_dev trig v(wl[0]) val='%s' rise=1 td=53n\n"
        "+ targ par('v(BL_bar[%d])-v(BL[%d])') val='%s' rise=1 td=53n"
        "  $ BL development" % (half, cf, cf, tenth),
        ".measure tran t_rd_sense trig v(sen_en) val='%s' rise=1 td=53n\n"
        "+ targ v(OUT[%d]) val='%s' fall=1 td=53n"
        "  $ <0: cell beat the sense amp" % (half, cf, half),
        "* write: 1->0 flip of cell (row 0, col %d) in %s @%gn;" % (cf, wr_op, wr_w),
        "* Q = Xdut.%s (channel terminal of the wl[0]/BL[%d] access xtor)"
        % (q_far, cf),
        ".measure tran t_wr_bl trig v(write) val='%s' rise=1 td=%gn\n"
        "+ targ v(BL[%d]) val='%s' fall=1 td=%gn  $ WD bitline drive"
        % (half, wr_w, cf, tenth, wr_w),
        ".measure tran t_wr_cell trig v(wl[0]) val='%s' rise=1 td=%gn\n"
        "+ targ v(Xdut.%s) val='%s' fall=1 td=%gn  $ cell feedback flip"
        % (half, wr_w, q_far, half, wr_w),
        ".measure tran t_wr_total param='t_wr_bl+t_wr_cell'"
        "  $ conservative self-timed write",
    ]
    dmeas = "\n".join(dm)

    probes = " ".join("v(OUT[%d])" % c for c in range(cols))
    extra = ["v(Xdut.%s)" % q_far]
    if cf != 0:
        extra = ["v(BL[%d])" % cf, "v(BL_bar[%d])" % cf] + extra
    probes += "\n+           " + " ".join(extra)

    tb = """* ============================================================
* Testbench: %s (%d rows x %d cols) — %s  VDD=%gV
* Generated by run_array.sh / gen_array_tb.py — do not edit directly.
* Sequence (10 ns/op): WR1init / RD(1->1) / WRsame / WRtoggle / WR0fill /
* RD(1->0); toggle rate %.4f (%d of %d columns flip in WRtoggle);
* leakage window 90-99 ns.  See gen_array_tb.py header for timing detail.
* ============================================================

.title %s array write/read test (%s, %d rows x %d cols, toggle %.2f)

%s
.include './models/nmos1.inc'
.include './models/pmos1.inc'

* -- Array netlist (bulk-tied copy) ------------------------------------
.include './%s.sp'

* -- Power supplies ----------------------------------------------------
VVDD VDD 0 %g
VVSS VSS 0 0

* -- Shared control sources --------------------------------------------
%s

* -- Per-column data sources -------------------------------------------
%s

* -- Initial conditions: all bitlines precharged -----------------------
%s

* -- DUT (nets in the cell's own port order; wl[1..%d] grounded) --------
%s

.tran 1p 100n

.probe tran v(BL[0]) v(BL_bar[0]) v(wl[0]) v(pre_en) v(write)
+           v(data[0]) v(sen_en) %s

* -- Energy per op window (J; sign: current OUT of VVDD is negative) ----
%s
.measure tran p_leak_W AVG par('-v(VDD)*i(VVDD)') from=90n to=99n

* -- Functional samples (OUT valid only while the sense amp is on) ------
%s
%s

* -- Read/write delay (far column %d — worst-case wordline RC) ----------
%s

.temp %g
%s
.option post ingold accurate numdgt=6

.end
""" % (a.cellname, rows, cols, a.node, V, rate, n_t, cols,
       a.cellname, a.node, rows, cols, rate,
       hdl, a.cellname, V, ctrl, "\n\n".join(data_src), out_ic,
       rows - 1, xdut, probes, emeas, fmeas, blmeas, cf, dmeas, a.temp, ba)

    with open(a.out, "w") as f:
        f.write(tb)
    print("gen_array_tb: %s  (%d rows x %d cols, toggle_rate=%.4f "
          "-> %d cols flip, VDD=%gV, %s)"
          % (a.out, rows, cols, rate, n_t, V,
             "PEX" if a.ba else "pre-layout"))
    # machine-readable line for run_array.sh's meta file
    print("META rows=%d cols=%d toggle_rate=%.6f n_toggle=%d"
          % (rows, cols, rate, n_t))


if __name__ == "__main__":
    main()
