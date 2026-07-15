from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .float_model import FloatFormat, emit_add_vectors, emit_mac_vectors, emit_mul_vectors
from .int_model import emit_intadd_vectors, emit_intmac_vectors, emit_intmul_vectors
from .mxfp_model import acc_width_from_format, emit_mxfpmac_vectors, get_mxfp_format
from .storage_model import emit_fifo_vectors, emit_regfile_vectors


RTL_GEN_DIR = Path(__file__).resolve().parent
RTL_DIR = RTL_GEN_DIR / "rtl"
TEMPLATE_DIR = RTL_GEN_DIR / "templates"

# Default length of the TB power-stimulus phase (random vectors after the
# functional phase; see templates/_power_stim.sv.j2). Overridable at sim time
# with +nw_power_cycles=<n> without regenerating the RTL.
DEFAULT_POWER_CYCLES = 2000


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _render(template_name: str, context: dict[str, Any]) -> str:
    return _env().get_template(template_name).render(**context).rstrip() + "\n"


def _unit_dir(module_name: str, output_root: Path | None = None) -> Path:
    root = output_root or RTL_DIR
    unit_dir = root / module_name
    unit_dir.mkdir(parents=True, exist_ok=True)
    return unit_dir


def _write_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _common_context(module_name: str, exp_bits: int, mantissa_bits: int, pipeline_stages: int) -> dict[str, Any]:
    if exp_bits < 3:
        raise ValueError("exp_bits must be >= 3")
    if mantissa_bits < 2:
        raise ValueError("mantissa_bits must be >= 2")
    if pipeline_stages < 2 or pipeline_stages > 5:
        raise ValueError("pipeline_stages must be in [2, 5]")
    return {
        "module_name": module_name,
        "exp_bits": int(exp_bits),
        "mantissa_bits": int(mantissa_bits),
        "pipeline_stages": int(pipeline_stages),
        "fp_width": int(exp_bits) + int(mantissa_bits) + 1,
        "mac_latency": int(pipeline_stages) + 2,
        "power_cycles": DEFAULT_POWER_CYCLES,
    }


def _int_context(
    module_name: str,
    a_width: int,
    b_width: int,
    out_width: int,
    pipeline_stages: int,
    *,
    acc_width: int | None = None,
) -> dict[str, Any]:
    if a_width < 2 or b_width < 2 or out_width < 2:
        raise ValueError("integer widths must be >= 2")
    if pipeline_stages < 2 or pipeline_stages > 5:
        raise ValueError("pipeline_stages must be in [2, 5]")
    ctx = {
        "module_name": module_name,
        "a_width": int(a_width),
        "b_width": int(b_width),
        "out_width": int(out_width),
        "pipeline_stages": int(pipeline_stages),
        "int_latency": int(pipeline_stages),
        "power_cycles": DEFAULT_POWER_CYCLES,
    }
    if acc_width is not None:
        if acc_width < 2:
            raise ValueError("acc_width must be >= 2")
        ctx["acc_width"] = int(acc_width)
        ctx["mac_latency"] = int(pipeline_stages)
    return ctx


def _noc_context(module_name: str, **params: int) -> dict[str, Any]:
    ctx: dict[str, Any] = {"module_name": module_name, "power_cycles": DEFAULT_POWER_CYCLES}
    for name, value in params.items():
        if value < 1:
            raise ValueError(f"{name} must be >= 1")
        ctx[name] = int(value)
    return ctx


def _pow_int(base: int, exp: int) -> int:
    out = 1
    for _ in range(exp):
        out *= base
    return out


def _ratio_context(value: float) -> dict[str, int]:
    if value <= 0.0 or value > 1.0:
        raise ValueError("oversubscription must be in (0, 1]")
    ratio = Fraction(str(value)).limit_denominator(1024)
    return {
        "oversubscription_num": ratio.numerator,
        "oversubscription_den": ratio.denominator,
    }


def _decode_function(is_int: bool) -> str:
    if is_int:
        return """function automatic signed [DECODE_WIDTH-1:0] decode_elem(
        input logic [ELEM_WIDTH-1:0] elem,
        input logic [SCALE_EXP_BITS-1:0] scale
    );
        logic signed [ELEM_WIDTH-1:0] signed_elem;
        logic signed [DECODE_WIDTH-1:0] shifted;
        int shift_amt;
        begin
            signed_elem = elem;
            shifted = DECODE_WIDTH'(signed_elem);
            shift_amt = DECODE_FRAC_BITS;
            if (USE_SCALE != 0) begin
                shift_amt = shift_amt + int'(scale) - SCALE_BIAS;
            end
            if (shift_amt >= 0) begin
                decode_elem = shifted <<< shift_amt;
            end else begin
                decode_elem = shifted >>> (-shift_amt);
            end
        end
    endfunction"""
    return """function automatic signed [DECODE_WIDTH-1:0] decode_elem(
        input logic [ELEM_WIDTH-1:0] elem,
        input logic [SCALE_EXP_BITS-1:0] scale
    );
        logic sign;
        int exp_field;
        int mant_field;
        int shift_amt;
        logic signed [DECODE_WIDTH-1:0] mag;
        logic signed [DECODE_WIDTH-1:0] shifted;
        begin
            sign = elem[ELEM_WIDTH-1];
            exp_field = int'(elem[ELEM_MANT_BITS +: ELEM_EXP_BITS]);
            mant_field = int'(elem[0 +: ELEM_MANT_BITS]);
            if ((exp_field == 0) && (mant_field == 0)) begin
                decode_elem = '0;
            end else begin
                if (exp_field == 0) begin
                    mag = DECODE_WIDTH'(mant_field);
                    shift_amt = 1 - ELEM_BIAS - ELEM_MANT_BITS + DECODE_FRAC_BITS;
                end else begin
                    mag = DECODE_WIDTH'((1 << ELEM_MANT_BITS) | mant_field);
                    shift_amt = exp_field - ELEM_BIAS - ELEM_MANT_BITS + DECODE_FRAC_BITS;
                end
                if (USE_SCALE != 0) begin
                    shift_amt = shift_amt + int'(scale) - SCALE_BIAS;
                end
                if (shift_amt >= 0) begin
                    shifted = mag <<< shift_amt;
                end else begin
                    shifted = mag >>> (-shift_amt);
                end
                decode_elem = sign ? -shifted : shifted;
            end
        end
    endfunction"""


def _block_accum_code(num_blocks: int) -> str:
    if num_blocks == 1:
        return "mac_comb = block_sum[0];"
    return """mac_comb = '0;
            for (int block = 0; block < NUM_BLOCKS; block = block + 1) begin
                mac_comb = mac_comb + block_sum[block];
            end"""


def _storage_context(module_name: str, width: int, depth: int) -> dict[str, Any]:
    if width < 1:
        raise ValueError("width must be >= 1")
    if depth < 1:
        raise ValueError("depth must be >= 1")
    return {
        "module_name": module_name,
        "width": int(width),
        "depth": int(depth),
        "addr_width": max(1, (int(depth) - 1).bit_length()),
        "power_cycles": DEFAULT_POWER_CYCLES,
    }


def gen_fpadd(
    *,
    exp_bits: int = 8,
    mantissa_bits: int = 23,
    pipeline_stages: int = 2,
    output_root: Path | None = None,
) -> dict[str, Path]:
    context = _common_context("fpadd", exp_bits, mantissa_bits, pipeline_stages)
    fmt = FloatFormat(exp_bits=exp_bits, mantissa_bits=mantissa_bits)
    context["test_vectors"] = emit_add_vectors(fmt)
    unit_dir = _unit_dir("fpadd", output_root)
    return {
        "rtl": _write_text(unit_dir / "fpadd.sv", _render("fpadd.sv.j2", context)),
        "tb": _write_text(unit_dir / "fpadd_tb.sv", _render("fpadd_tb.sv.j2", context)),
    }


def gen_fpmul(
    *,
    exp_bits: int = 8,
    mantissa_bits: int = 23,
    pipeline_stages: int = 2,
    output_root: Path | None = None,
) -> dict[str, Path]:
    context = _common_context("fpmul", exp_bits, mantissa_bits, pipeline_stages)
    fmt = FloatFormat(exp_bits=exp_bits, mantissa_bits=mantissa_bits)
    context["test_vectors"] = emit_mul_vectors(fmt)
    unit_dir = _unit_dir("fpmul", output_root)
    return {
        "rtl": _write_text(unit_dir / "fpmul.sv", _render("fpmul.sv.j2", context)),
        "tb": _write_text(unit_dir / "fpmul_tb.sv", _render("fpmul_tb.sv.j2", context)),
    }


def gen_fpmac(
    *,
    exp_bits: int = 8,
    mantissa_bits: int = 23,
    pipeline_stages: int = 2,
    output_root: Path | None = None,
) -> dict[str, Path]:
    context = _common_context("fpmac", exp_bits, mantissa_bits, pipeline_stages)
    fmt = FloatFormat(exp_bits=exp_bits, mantissa_bits=mantissa_bits)
    context["test_vectors"] = emit_mac_vectors(fmt)
    context["embedded_fpmul"] = _render(
        "fpmul.sv.j2",
        _common_context("fpmul", exp_bits, mantissa_bits, 2),
    )
    context["embedded_fpadd"] = _render(
        "fpadd.sv.j2",
        _common_context("fpadd", exp_bits, mantissa_bits, 2),
    )
    unit_dir = _unit_dir("fpmac", output_root)
    return {
        "rtl": _write_text(unit_dir / "fpmac.sv", _render("fpmac.sv.j2", context)),
        "tb": _write_text(unit_dir / "fpmac_tb.sv", _render("fpmac_tb.sv.j2", context)),
    }


def gen_intadd(
    *,
    a_width: int = 8,
    b_width: int = 8,
    out_width: int = 16,
    pipeline_stages: int = 2,
    output_root: Path | None = None,
) -> dict[str, Path]:
    context = _int_context("intadd", a_width, b_width, out_width, pipeline_stages)
    context["test_vectors"] = emit_intadd_vectors(a_width, b_width, out_width)
    unit_dir = _unit_dir("intadd", output_root)
    return {
        "rtl": _write_text(unit_dir / "intadd.sv", _render("intadd.sv.j2", context)),
        "tb": _write_text(unit_dir / "intadd_tb.sv", _render("intadd_tb.sv.j2", context)),
    }


def gen_intmul(
    *,
    a_width: int = 8,
    b_width: int = 8,
    out_width: int = 16,
    pipeline_stages: int = 2,
    output_root: Path | None = None,
) -> dict[str, Path]:
    context = _int_context("intmul", a_width, b_width, out_width, pipeline_stages)
    context["test_vectors"] = emit_intmul_vectors(a_width, b_width, out_width)
    unit_dir = _unit_dir("intmul", output_root)
    return {
        "rtl": _write_text(unit_dir / "intmul.sv", _render("intmul.sv.j2", context)),
        "tb": _write_text(unit_dir / "intmul_tb.sv", _render("intmul_tb.sv.j2", context)),
    }


def gen_intmac(
    *,
    a_width: int = 8,
    b_width: int = 8,
    out_width: int = 16,
    acc_width: int = 24,
    pipeline_stages: int = 2,
    output_root: Path | None = None,
) -> dict[str, Path]:
    context = _int_context(
        "intmac",
        a_width,
        b_width,
        out_width,
        pipeline_stages,
        acc_width=acc_width,
    )
    context["test_vectors"] = emit_intmac_vectors(a_width, b_width, acc_width, out_width)
    unit_dir = _unit_dir("intmac", output_root)
    return {
        "rtl": _write_text(unit_dir / "intmac.sv", _render("intmac.sv.j2", context)),
        "tb": _write_text(unit_dir / "intmac_tb.sv", _render("intmac_tb.sv.j2", context)),
    }


def gen_simplemux(
    *,
    data_width: int = 32,
    num_inputs: int = 4,
    output_root: Path | None = None,
) -> dict[str, Path]:
    context = _noc_context("simplemux", data_width=data_width, num_inputs=num_inputs)
    unit_dir = _unit_dir("simplemux", output_root)
    return {
        "rtl": _write_text(unit_dir / "simplemux.sv", _render("simplemux.sv.j2", context)),
        "tb": _write_text(unit_dir / "simplemux_tb.sv", _render("simplemux_tb.sv.j2", context)),
    }


def gen_crossbar(
    *,
    data_width: int = 32,
    num_inputs: int = 4,
    num_outputs: int = 4,
    output_root: Path | None = None,
) -> dict[str, Path]:
    context = _noc_context(
        "crossbar",
        data_width=data_width,
        num_inputs=num_inputs,
        num_outputs=num_outputs,
    )
    unit_dir = _unit_dir("crossbar", output_root)
    return {
        "rtl": _write_text(unit_dir / "crossbar.sv", _render("crossbar.sv.j2", context)),
        "tb": _write_text(unit_dir / "crossbar_tb.sv", _render("crossbar_tb.sv.j2", context)),
    }


def gen_fattree(
    *,
    data_width: int = 32,
    radix: int = 2,
    num_levels: int = 3,
    oversubscription: float = 1.0,
    output_root: Path | None = None,
) -> dict[str, Path]:
    if radix < 2:
        raise ValueError("radix must be >= 2")
    context = _noc_context(
        "fattree",
        data_width=data_width,
        radix=radix,
        num_levels=num_levels,
    )
    context.update(_ratio_context(oversubscription))
    context["num_nodes"] = _pow_int(radix, num_levels)
    unit_dir = _unit_dir("fattree", output_root)
    return {
        "rtl": _write_text(unit_dir / "fattree.sv", _render("fattree.sv.j2", context)),
        "tb": _write_text(unit_dir / "fattree_tb.sv", _render("fattree_tb.sv.j2", context)),
    }


def gen_foldedclos(
    *,
    data_width: int = 32,
    terminals_per_leaf: int = 4,
    num_leaves: int = 4,
    num_spines: int = 4,
    switch_radix: int | None = None,
    oversubscription: float = 1.0,
    output_root: Path | None = None,
) -> dict[str, Path]:
    ratio = _ratio_context(oversubscription)
    active_spines = max(1, min(num_spines, (terminals_per_leaf * ratio["oversubscription_num"] + ratio["oversubscription_den"] - 1) // ratio["oversubscription_den"]))
    switch_radix = switch_radix or terminals_per_leaf + active_spines
    if switch_radix < terminals_per_leaf + active_spines:
        raise ValueError("switch_radix must cover leaf downlinks plus active uplinks")
    context = _noc_context(
        "foldedclos",
        data_width=data_width,
        terminals_per_leaf=terminals_per_leaf,
        num_leaves=num_leaves,
        num_spines=num_spines,
        switch_radix=switch_radix,
    )
    context.update(ratio)
    context["num_nodes"] = terminals_per_leaf * num_leaves
    unit_dir = _unit_dir("foldedclos", output_root)
    return {
        "rtl": _write_text(unit_dir / "foldedclos.sv", _render("foldedclos.sv.j2", context)),
        "tb": _write_text(unit_dir / "foldedclos_tb.sv", _render("foldedclos_tb.sv.j2", context)),
    }


def gen_mxfpmac(
    *,
    block_elems: int = 32,
    num_blocks: int = 2,
    input_format: str = "mxfp8_e4m3",
    elem_width: int | None = None,
    elem_exp_bits: int | None = None,
    elem_mant_bits: int | None = None,
    elem_bias: int | None = None,
    custom_is_int: bool = False,
    custom_use_scale: bool = True,
    scale_exp_bits: int = 8,
    scale_bias: int | None = None,
    acc_format: str = "fp32",
    acc_width: int | None = None,
    decode_width: int = 24,
    decode_frac_bits: int = 8,
    output_root: Path | None = None,
) -> dict[str, Path]:
    if block_elems < 1:
        raise ValueError("block_elems must be >= 1")
    if num_blocks < 1:
        raise ValueError("num_blocks must be >= 1")
    if scale_exp_bits < 1:
        raise ValueError("scale_exp_bits must be >= 1")
    if decode_width < 8:
        raise ValueError("decode_width must be >= 8")
    if decode_frac_bits < 0:
        raise ValueError("decode_frac_bits must be >= 0")

    fmt = get_mxfp_format(
        input_format,
        elem_width=elem_width,
        elem_exp_bits=elem_exp_bits,
        elem_mant_bits=elem_mant_bits,
        elem_bias=elem_bias,
        is_int=custom_is_int,
        use_scale=custom_use_scale,
    )
    acc_w = acc_width_from_format(acc_format, acc_width)
    scale_b = scale_bias if scale_bias is not None else (1 << (scale_exp_bits - 1)) - 1
    if scale_b < 0 or scale_b > (1 << scale_exp_bits) - 1:
        raise ValueError("scale_bias is outside scale_exp_bits range")

    context = {
        "module_name": "mxfpmac",
        "block_elems": int(block_elems),
        "num_blocks": int(num_blocks),
        "total_elems": int(block_elems) * int(num_blocks),
        "total_elem_bits": int(block_elems) * int(num_blocks) * fmt.elem_width,
        "input_format": fmt.name,
        "elem_width": fmt.elem_width,
        "elem_exp_bits": max(1, fmt.exp_bits),
        "elem_mant_bits": max(1, fmt.mant_bits),
        "elem_bias": fmt.bias,
        "scale_exp_bits": int(scale_exp_bits),
        "total_scale_bits": int(num_blocks) * int(scale_exp_bits),
        "scale_bias": int(scale_b),
        "use_scale": 1 if fmt.use_scale else 0,
        "acc_width": int(acc_w),
        "decode_width": int(decode_width),
        "decode_frac_bits": int(decode_frac_bits),
        "product_width": int(decode_width) * 2,
        "decode_function": _decode_function(fmt.is_int),
        "block_accum_code": _block_accum_code(int(num_blocks)),
        "power_cycles": DEFAULT_POWER_CYCLES,
    }
    context["test_vectors"] = emit_mxfpmac_vectors(
        fmt,
        block_elems=block_elems,
        num_blocks=num_blocks,
        scale_exp_bits=scale_exp_bits,
        scale_bias=scale_b,
        acc_width=acc_w,
        decode_frac_bits=decode_frac_bits,
    )
    unit_dir = _unit_dir("mxfpmac", output_root)
    return {
        "rtl": _write_text(unit_dir / "mxfpmac.sv", _render("mxfpmac.sv.j2", context)),
        "tb": _write_text(unit_dir / "mxfpmac_tb.sv", _render("mxfpmac_tb.sv.j2", context)),
    }


def gen_regfile(
    *,
    width: int = 32,
    depth: int = 64,
    num_read_ports: int = 1,
    num_write_ports: int = 1,
    output_root: Path | None = None,
) -> dict[str, Path]:
    if num_read_ports < 0 or num_write_ports < 0:
        raise ValueError("port counts must be >= 0")
    if num_read_ports < 1:
        raise ValueError("regfile needs at least one read port")
    if num_write_ports < 1:
        raise ValueError("regfile needs at least one write port")
    context = _storage_context("regfile", width, depth)
    context.update(
        {
            "num_read_ports": int(num_read_ports),
            "num_write_ports": int(num_write_ports),
            "w_port_width": max(1, int(num_write_ports)),
            "w_addr_bits": max(1, int(num_write_ports) * context["addr_width"]),
            "w_data_bits": max(1, int(num_write_ports) * int(width)),
            "r_addr_bits": max(1, int(num_read_ports) * context["addr_width"]),
            "r_data_bits": max(1, int(num_read_ports) * int(width)),
            "test_vectors": emit_regfile_vectors(width, depth, num_read_ports, num_write_ports),
        }
    )
    unit_dir = _unit_dir("regfile", output_root)
    return {
        "rtl": _write_text(unit_dir / "regfile.sv", _render("regfile.sv.j2", context)),
        "tb": _write_text(unit_dir / "regfile_tb.sv", _render("regfile_tb.sv.j2", context)),
    }


def gen_fifo(
    *,
    width: int = 32,
    depth: int = 16,
    output_root: Path | None = None,
) -> dict[str, Path]:
    context = _storage_context("fifo", width, depth)
    context["ptr_width"] = max(1, depth.bit_length())
    context["mem_addr_width"] = max(1, (depth - 1).bit_length())
    context["test_vectors"] = emit_fifo_vectors(width, depth)
    unit_dir = _unit_dir("fifo", output_root)
    return {
        "rtl": _write_text(unit_dir / "fifo.sv", _render("fifo.sv.j2", context)),
        "tb": _write_text(unit_dir / "fifo_tb.sv", _render("fifo_tb.sv.j2", context)),
    }
