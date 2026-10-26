#!/opt/conda/bin/python
"""mlir-translate wrapper for bf16 GEMM kernels (PyTorchSim v1.1.0 image).

The VCIX lowering accumulates the systolic pops with a bf16 vector fadd. LLVM has no bf16 vector add and scalarizes it
through Zfbfmin converts that gem5 cannot decode. After the real mlir-translate, this wrapper rewrites every
`fadd <N x bfloat>` in the LLVM IR into an f32 add on bit-extended operands (bf16 is the upper half of f32), rounded
back to bf16 with round-to-nearest-even. A TPU does the same thing in its MXU accumulators, in f32 for the whole K.
"""
import os, re, subprocess, sys

REAL = "/riscv-llvm/bin/mlir-translate"
args = sys.argv[1:]
rc = subprocess.call([REAL] + args)
if rc != 0 or "-o" not in args:
    sys.exit(rc)
out = args[args.index("-o") + 1]
text = open(out).read()
if "bfloat" not in text:
    sys.exit(0)

FLAGS = r"(?:(?:fast|nnan|ninf|nsz|arcp|contract|afn|reassoc) )*"
PAT = re.compile(r"^(\s*)(%[\w.$]+) = fadd " + FLAGS + r"<(\d+) x bfloat> (.+?), (.+?)\s*$")
lines, new, n = text.split("\n"), [], 0
for line in lines:
    m = PAT.match(line)
    if not m:
        new.append(line)
        continue
    n += 1
    ind, res, N, a, b = m.groups()
    N = int(N)
    p = f"%bfacc{n}."
    i16, i32, f32, bf = f"<{N} x i16>", f"<{N} x i32>", f"<{N} x float>", f"<{N} x bfloat>"
    c16 = "<" + ", ".join(["i32 16"] * N) + ">"
    c1 = "<" + ", ".join(["i32 1"] * N) + ">"
    cr = "<" + ", ".join(["i32 32767"] * N) + ">"
    seq = [
        f"{p}a1 = bitcast {bf} {a} to {i16}",
        f"{p}a2 = zext {i16} {p}a1 to {i32}",
        f"{p}a3 = shl {i32} {p}a2, {c16}",
        f"{p}a4 = bitcast {i32} {p}a3 to {f32}",
        f"{p}b1 = bitcast {bf} {b} to {i16}",
        f"{p}b2 = zext {i16} {p}b1 to {i32}",
        f"{p}b3 = shl {i32} {p}b2, {c16}",
        f"{p}b4 = bitcast {i32} {p}b3 to {f32}",
        f"{p}s = fadd {f32} {p}a4, {p}b4",
        f"{p}i = bitcast {f32} {p}s to {i32}",
        f"{p}l = lshr {i32} {p}i, {c16}",
        f"{p}m = and {i32} {p}l, {c1}",
        f"{p}n = add {i32} {p}m, {cr}",
        f"{p}o = add {i32} {p}i, {p}n",
        f"{p}j = lshr {i32} {p}o, {c16}",
        f"{p}k = trunc {i32} {p}j to {i16}",
        f"{res} = bitcast {i16} {p}k to {bf}",
    ]
    new.extend(ind + s for s in seq)
# Masked loads/stores of bf16 vectors: this LLVM scalarizes them into a per-lane branch ladder (flh/fsh), which makes
# the tile 3x slower than fp32. Do them as i16 vectors (vle16.v/vse16.v with a mask) and bitcast.
LD = re.compile(r"^(\s*)(%[\w.$]+) = (tail )?call <(\d+) x bfloat> @llvm\.masked\.load\.v(\d+)bf16\.(p\d+)\((.*), <\d+ x bfloat> ([^,()]+)\)(.*)$")
ST = re.compile(r"^(\s*)(tail )?call void @llvm\.masked\.store\.v(\d+)bf16\.(p\d+)\(<\d+ x bfloat> ([^,]+), (.*)\)(.*)$")
lines, new2, nl, ns, decl = new, [], 0, 0, set()
for line in lines:
    m = LD.match(line)
    if m:
        nl += 1
        ind, res, tail, N, _, ps, args, passthru, attrs = m.groups()
        q = f"%bfld{nl}."
        pt = passthru if passthru in ("zeroinitializer", "poison", "undef") else f"{q}pt"
        if pt == f"{q}pt":
            new2.append(f"{ind}{q}pt = bitcast <{N} x bfloat> {passthru} to <{N} x i16>")
        new2.append(f"{ind}{q}v = {tail or ''}call <{N} x i16> @llvm.masked.load.v{N}i16.{ps}({args}, <{N} x i16> {pt}){attrs}")
        new2.append(f"{ind}{res} = bitcast <{N} x i16> {q}v to <{N} x bfloat>")
        decl.add(("load", N, ps))
        continue
    m = ST.match(line)
    if m:
        ns += 1
        ind, tail, N, ps, val, rest, attrs = m.groups()
        q = f"%bfst{ns}."
        new2.append(f"{ind}{q}v = bitcast <{N} x bfloat> {val} to <{N} x i16>")
        new2.append(f"{ind}{tail or ''}call void @llvm.masked.store.v{N}i16.{ps}(<{N} x i16> {q}v, {rest}){attrs}")
        decl.add(("store", N, ps))
        continue
    new2.append(line)
# declarations for the i16 twins, copied from the bf16 ones
extra = []
for line in new2:
    if line.startswith("declare") and ("masked.load.v" in line or "masked.store.v" in line) and "bf16" in line:
        extra.append(line.replace("bfloat", "i16").replace("bf16.", "i16."))
new2 = [l for l in new2] + [l for l in extra if l not in new2]
open(out, "w").write("\n".join(new2))
sys.stderr.write(f"[mlir_translate_bf16] {out}: rewrote {n} bf16 vector fadd, {nl} masked loads, {ns} masked stores\n")
