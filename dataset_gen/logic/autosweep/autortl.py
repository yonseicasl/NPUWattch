from __future__ import annotations

from pathlib import Path
from typing import Callable

from autocommon import (
    JOB_LIST,
    STAGE_RTL_GEN,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_RUNNING,
    STATUS_SKIP,
    STATUS_START,
    log_event,
    parse_arch_params,
    read_jobs,
    rtl_variant_key,
)
from rtl_gen import generator


GeneratorFn = Callable[..., dict[str, Path]]


def _generator_map() -> dict[str, GeneratorFn]:
    gens: dict[str, GeneratorFn] = {}
    for name in dir(generator):
        if not name.startswith("gen_"):
            continue
        candidate = getattr(generator, name)
        if not callable(candidate):
            continue
        rtl_name = name.removeprefix("gen_")
        gens[rtl_name] = candidate
    return gens


def generate_rtl_from_manifest(path: Path = JOB_LIST) -> list[dict[str, Path]]:
    gens = _generator_map()
    outputs: list[dict[str, Path]] = []
    generated_keys: set[tuple[str, str]] = set()

    log_event(stage=STAGE_RTL_GEN, status=STATUS_START, message=f"reading manifest {path}")

    for index, job in enumerate(read_jobs(path), start=1):
        key = rtl_variant_key(job)
        if key in generated_keys:
            rtl_name, _ = key
            print(f"[{index}] skipped duplicate RTL variant: {rtl_name}")
            log_event(
                stage=STAGE_RTL_GEN,
                status=STATUS_SKIP,
                message="duplicate node-independent RTL variant",
                job=job,
                details={"job_index": index},
            )
            continue
        generated_keys.add(key)

        rtl_name = job["rtl_name"].strip()
        if rtl_name not in gens:
            valid = ", ".join(sorted(gens))
            raise ValueError(f"job {index}: unsupported rtl_name {rtl_name!r}; valid names: {valid}")

        params = parse_arch_params(job.get("arch_params", ""))
        log_event(
            stage=STAGE_RTL_GEN,
            status=STATUS_RUNNING,
            message="generating RTL",
            job=job,
            details={"job_index": index, "params": params},
        )
        try:
            generated = gens[rtl_name](**params)
        except Exception as exc:
            log_event(
                stage=STAGE_RTL_GEN,
                status=STATUS_ERROR,
                message=f"RTL generation failed: {exc}",
                job=job,
                details={"job_index": index, "error_type": type(exc).__name__},
            )
            raise
        outputs.append(generated)

        produced = ", ".join(f"{kind}={file_path}" for kind, file_path in sorted(generated.items()))
        print(f"[{index}] generated {rtl_name}: {produced}")
        log_event(
            stage=STAGE_RTL_GEN,
            status=STATUS_DONE,
            message="RTL generated",
            job=job,
            details={"job_index": index, "outputs": {kind: str(file_path) for kind, file_path in generated.items()}},
        )

    log_event(
        stage=STAGE_RTL_GEN,
        status=STATUS_DONE,
        message="RTL generation stage complete",
        details={"generated_variant_count": len(outputs)},
    )
    return outputs
