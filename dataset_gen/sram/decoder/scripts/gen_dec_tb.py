#!/usr/bin/env python3
"""
gen_dec_tb.py -- decoder testbench generator, called by run_decoder.sh.

The DUT is the flat transistor netlist extracted from the PnR'd decoder
(dec_<R>x<C>).  Every wl[i] output carries a pi model of the array wordline
RC (from wl_load.py: the array-PEX wl[0] cap/res) -- this books the WL CV^2
energy on the decoder side; the array TB drives its wordline with an ideal
PWL, so nothing is double-counted.  wlf[i] is the far end of the pi load
(worst-case for delay/slew).

Stimulus (10 ns/op, matching the array cadence; clk rises at T, wlen pulses
T+2..T+5 -- the same WL window the array TB uses):

   t(ns)  0-10    settle    en rises at 5; addr=0, no clock
  10-20   ACTf    addr 0    first activation of wl[0] (prior state unknown)
  20-30   ACTs    addr 0    same address again -> zero addr-register toggles
  30-40   ACTx    addr R-1  every address bit flips -> max decode toggling
  40-50   ACTs2   addr R-1  same address again
  50-60   ACTb    addr 0    every address bit flips back
  60-70   IDLE    en=0      clk still toggles, wlen low -> clock/idle energy
  70-150  quiet             leakage window 90-149 ns (long settled tail: the
                            59 ns AVG window keeps pW-level leakage above the
                            transient-integrator noise floor)

Energies: INTEG -v(VDD)*i(VVDD) over each [T,T+10] window.
Delays (measured on the ACTx op, far node wlf[R-1]):
  t_clk_wl    clk 50% rise -> wlf 50% rise (register+decode+driver+WL RC;
              lower-bounded by the wlen gate at T+2, i.e. >= 2 ns + drive)
  t_wlen_wl   wlen 50% rise -> wlf 50% rise (driver + WL RC only -- add to
              the array's wl->OUT for the serial read path)
  t_wl_rise   wlf 10% -> 90% rise (feed back into the array TB PWL slope)
Functional checks: correct one-hot wl at 13.5/33.5 ns, exclusivity, wl low
in the IDLE op.

Waveform output (.tr0) is limited to the .probe list via .option probe —
without it HSPICE dumps every internal node of the flat extracted netlist,
which is what made the 512-row decoder tr0 ~385 MB.  The full 0-100 ns of
the probed ports is recorded.

Usage (normally via run_decoder.sh):
  gen_dec_tb.py <extracted.sp> --cellname dec_RxC --vdd V --temp T
                --node NAME --wl-cap-ff C --wl-res-ohm R [--ba <spef>]
                [--hdl <va>] -o tb.sp
"""
import argparse
import re
import sys


def die(msg):
    sys.exit("gen_dec_tb: error: %s" % msg)


def parse_ports(sp_path, cellname):
    text = re.sub(r"\n\+", " ", open(sp_path).read())
    for line in text.splitlines():
        t = line.split()
        if t and t[0].upper() == ".SUBCKT" and t[1] == cellname:
            return t[2:]
    die("no .SUBCKT %s in %s" % (cellname, sp_path))


def indexed(ports, base):
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
    ap.add_argument("--wl-cap-ff", type=float, required=True)
    ap.add_argument("--wl-res-ohm", type=float, required=True)
    ap.add_argument("--ba", default="")
    ap.add_argument("--hdl", default="")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    ports = parse_ports(a.sp, a.cellname)
    rows = indexed(ports, "wl")
    abits = indexed(ports, "addr")
    if (1 << abits) != rows:
        die("addr width %d does not decode %d rows" % (abits, rows))
    known = {"clk", "en", "wlen", "VDD", "VSS"}
    bad = [p for p in ports if p not in known
           and not re.fullmatch(r"(wl|addr)\[\d+\]", p)]
    if bad:
        die("unknown DUT ports: %s" % bad)

    V = a.vdd
    hdl = ".hdl './models/%s'" % a.hdl if a.hdl else \
        "* (native .model card -- no Verilog-A to load)"
    ba = ".option ba_file='./%s'" % a.ba if a.ba else \
        "* pre-layout run -- no parasitic back-annotation"

    def pwl(pairs):
        return "PWL(\n" + "\n".join("+ %gn %g" % (t, v) for t, v in pairs) \
               + " )"

    def edges(times_up_down, v_hi, v0=0.0, tend=100.0):
        pts = [(0.0, v0)]
        for tr, tf in times_up_down:
            pts += [(tr, v0), (tr + 0.01, v_hi), (tf, v_hi), (tf + 0.01, v0)]
        pts.append((tend, v0))
        return pwl(pts)

    OPS = [10.0, 20.0, 30.0, 40.0, 50.0]      # active ops (wlen pulses)
    ALL = OPS + [60.0]                        # + idle-clock op
    src = {
        "clk": edges([(t, t + 5) for t in ALL], V),
        "en": edges([(5, 58)], V),
        "wlen": edges([(t + 2, t + 5) for t in OPS], V),
    }
    ctrl = "\n\n".join("V%s %s 0 %s" % (n, n, w) for n, w in src.items())

    # addr: 0 -> R-1 at 29 ns -> 0 at 49 ns (1 ns setup before the clk edge)
    hi_bits = rows - 1                        # address R-1 = all ones
    addr_src = []
    for b in range(abits):
        if hi_bits >> b & 1:
            w = pwl([(0, 0), (29, 0), (29.01, V), (49, V), (49.01, 0),
                     (100, 0)])
        else:
            w = pwl([(0, 0), (100, 0)])
        addr_src.append("Vaddr%d addr[%d] 0 %s" % (b, b, w))

    # pi loads: decoder pin -- R -- wlf[i] with C/2 at each end
    ch = a.wl_cap_ff / 2.0
    loads = "\n".join(
        "Cwln%d wl[%d] 0 %.5ff\nRwl%d wl[%d] wlf[%d] %.3f\n"
        "Cwlf%d wlf[%d] 0 %.5ff"
        % (i, i, ch, i, i, i, a.wl_res_ohm, i, i, ch) for i in range(rows))

    xdut = ""
    line = "Xdut"
    for n in list(ports) + [a.cellname]:
        if len(line) + 1 + len(n) > 80:
            xdut += line + "\n"
            line = "+"
        line += " " + n
    xdut += line

    ops = [("act_first", 10, "addr 0, first activation (aux)"),
           ("act_same", 20, "addr 0 again -- zero addr toggles"),
           ("act_flip", 30, "addr 0->%d -- all %d addr bits flip"
            % (rows - 1, abits)),
           ("act_same2", 40, "addr %d again" % (rows - 1)),
           ("act_back", 50, "addr %d->0 -- all bits flip back" % (rows - 1)),
           ("idle_clk", 60, "en=0, clk toggles, no WL -- idle-cycle energy")]
    emeas = "\n".join(
        ".measure tran e_%s_J INTEG par('-v(VDD)*i(VVDD)') "
        "from=%dn to=%dn  $ %s" % (name, t, t + 10, desc)
        for name, t, desc in ops)

    wf = "wlf[%d]" % (rows - 1)
    half = "0.5*%g" % V
    dmeas = "\n".join([
        ".measure tran t_clk_wl trig v(clk) val='%s' rise=1 td=29.5n\n"
        "+ targ v(%s) val='%s' rise=1 td=29.5n"
        "  $ clk->WL far node (includes the 2 ns wlen gate)" % (half, wf, half),
        ".measure tran t_wlen_wl trig v(wlen) val='%s' rise=1 td=31n\n"
        "+ targ v(%s) val='%s' rise=1 td=31n"
        "  $ WL driver + wordline RC" % (half, wf, half),
        ".measure tran t_wl_rise trig v(%s) val='0.1*%g' rise=1 td=31n\n"
        "+ targ v(%s) val='0.9*%g' rise=1 td=31n"
        "  $ WL 10-90%% rise at the far end" % (wf, V, wf, V),
    ])

    fmeas = "\n".join([
        ".measure tran wl0_act    find v(wlf[0]) at=13.5n   $ expect ~VDD",
        ".measure tran wl0_off    find v(wlf[0]) at=33.5n   $ expect ~0",
        ".measure tran wllast_act find v(%s) at=33.5n   $ expect ~VDD" % wf,
        ".measure tran wllast_off find v(%s) at=13.5n   $ expect ~0" % wf,
        ".measure tran wl_idle    find v(wlf[0]) at=63.5n   $ en=0: expect ~0",
    ])

    probes = ("v(clk) v(en) v(wlen) v(wl[0]) v(wlf[0]) v(wl[%d]) v(%s)"
              % (rows - 1, wf))

    tb = """* ============================================================
* Testbench: %s (%d rows, %d addr bits) -- %s  VDD=%gV
* Generated by run_decoder.sh / gen_dec_tb.py -- do not edit directly.
* WL pi load per output: %.4f fF / %.2f ohm (from array PEX wl[0]).
* Sequence (10 ns/op): ACTfirst/ACTsame/ACTflip/ACTsame2/ACTback/IDLEclk;
* leakage window 90-149 ns.  See gen_dec_tb.py header for timing detail.
* ============================================================

.title %s decoder activation test (%s, %d rows)

%s
.include './models/nmos1.inc'
.include './models/pmos1.inc'

* -- Decoder netlist (bulk-tied copy) ----------------------------------
.include './%s.sp'

* -- Power supplies ----------------------------------------------------
VVDD VDD 0 %g
VVSS VSS 0 0

* -- Control sources ---------------------------------------------------
%s

* -- Address sources ---------------------------------------------------
%s

* -- Wordline RC loads (array wl[0] extracted cap/res, pi model) --------
%s

* -- DUT (nets in the cell's own port order) ----------------------------
%s

.tran 1p 150n

.probe tran %s

* -- Energy per op window (J; current OUT of VVDD is negative) ----------
%s
.measure tran p_leak_W AVG par('-v(VDD)*i(VVDD)') from=90n to=149n

* -- Delays (ACTx op, far WL node) --------------------------------------
%s

* -- Functional samples -------------------------------------------------
%s

.temp %g
%s
* probe: tr0 holds only the .probe list, not every internal node
.option post probe ingold accurate numdgt=6

.end
""" % (a.cellname, rows, abits, a.node, V, a.wl_cap_ff, a.wl_res_ohm,
       a.cellname, a.node, rows,
       hdl, a.cellname, V, ctrl, "\n".join(addr_src), loads, xdut,
       probes, emeas, dmeas, fmeas, a.temp, ba)

    with open(a.out, "w") as f:
        f.write(tb)
    print("gen_dec_tb: %s (%d rows, %d addr bits, WL load %.4f fF/%.2f ohm,"
          " VDD=%gV, %s)" % (a.out, rows, abits, a.wl_cap_ff, a.wl_res_ohm,
                             V, "PEX" if a.ba else "pre-layout"))
    print("META rows=%d abits=%d" % (rows, abits))


if __name__ == "__main__":
    main()
