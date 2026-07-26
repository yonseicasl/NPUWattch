"""BookSim2 NoC topology → NPUWattch NoC symbols + flit traffic stats.

PyTorchSim delegates its interconnect wholesale to BookSim2 (``icnt_type:
booksim2``): the ``.icnt`` config names a topology, cores' injection ports and
DRAM channels are the network endpoints, and the log reports only one
network-wide stats block (averages — no per-router counters). Interpreting that
one monolithic object as physical components is this reader's job:

* ``fly`` with ``n = 1`` — a single-stage butterfly, i.e. **one k×k crossbar**.
  The log's embedded ``[config]`` echo carries everything (k, flit_size, buffer
  depths), so no extra input is needed.
* ``anynet`` — the ``.net`` graph file (only its *path* is echoed) enumerates
  routers explicitly. Routers with attached ``node`` endpoints are real
  switches; routers with **no** nodes and exactly two router links are
  pass-through hops — the **die-to-die channels** themselves (the author
  chiplet config: 2 chiplet routers + 8 latency-5 channels between them).

Traffic: every BookSim packet in these runs is a single flit of ``flit_size``
bytes (= ``dram_req_size_byte``), and each DRAM request contributes one request
and one response packet — so total flits = ``2 × (dram_reads + dram_writes)``,
verified exactly against the log's injected-rate × nodes × cycles on the author
samples. Multi-router traversal splits (anynet) use a **uniform-traffic
assumption** (warned): with R real routers, ``(R−1)/R`` of flits cross a
die-to-die channel and traverse two routers.

The output feeds the generic compound mechanism: ``symbols`` become integer
run-config expression symbols (``icnt_ports``/``icnt_routers``/``icnt_channels``
plus the raw ``booksim_*`` config ints), ``stats`` become window activity stats
(``icnt_xbar_flits``/``icnt_d2d_flits``) that the pytorchsim projection's
``noc`` actions consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

__all__ = ["NetGraph", "NetRouter", "NocDerivation", "parse_net_file", "derive_noc"]

#: Topologies this harness can decompose. Everything else (mesh, torus,
#: multi-stage fly, …) is rejected with a warning — never silently mis-modeled.
_SUPPORTED = "fly (n = 1) and anynet"


@dataclass(frozen=True)
class NetRouter:
    """One ``router`` entry of a BookSim anynet ``.net`` file (lines merged)."""

    nodes: Tuple[int, ...] = ()                      # attached endpoint ids
    links: Tuple[Tuple[int, Optional[int]], ...] = ()  # (peer router, latency)

    @property
    def radix(self) -> int:
        return len(self.nodes) + len(self.links)


@dataclass(frozen=True)
class NetGraph:
    routers: Dict[int, NetRouter]

    def real_routers(self) -> Dict[int, NetRouter]:
        """Routers with attached endpoints — the actual switches."""
        return {i: r for i, r in self.routers.items() if r.nodes}

    def channels(self) -> Dict[int, NetRouter]:
        """Node-less two-link pass-through routers — die-to-die channels."""
        return {i: r for i, r in self.routers.items()
                if not r.nodes and len(r.links) == 2}


@dataclass(frozen=True)
class NocDerivation:
    """What the NoC contributes to a window: expression symbols + activity."""

    symbols: Dict[str, int] = field(default_factory=dict)
    stats: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


class NetFileError(ValueError):
    """The anynet ``.net`` file is missing or malformed."""


def parse_net_file(text: str) -> NetGraph:
    """Parse BookSim's anynet grammar: each line ``router <id>`` followed by any
    mix of ``node <id>`` and ``router <id> [<latency>]`` tokens; multiple lines
    for the same router id merge."""
    nodes: Dict[int, List[int]] = {}
    links: Dict[int, List[Tuple[int, Optional[int]]]] = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        toks = line.split()
        if not toks:
            continue
        if toks[0] != "router" or len(toks) < 2:
            raise NetFileError(f".net line {lineno}: expected 'router <id> ...', got {line!r}")
        try:
            rid = int(toks[1])
        except ValueError:
            raise NetFileError(f".net line {lineno}: non-integer router id {toks[1]!r}")
        nodes.setdefault(rid, [])
        links.setdefault(rid, [])
        i = 2
        while i < len(toks):
            kind = toks[i]
            if kind == "node" and i + 1 < len(toks):
                nodes[rid].append(int(toks[i + 1]))
                i += 2
            elif kind == "router" and i + 1 < len(toks):
                peer = int(toks[i + 1])
                latency: Optional[int] = None
                if i + 2 < len(toks) and toks[i + 2].isdigit():
                    latency = int(toks[i + 2])
                    i += 3
                else:
                    i += 2
                links[rid].append((peer, latency))
            else:
                raise NetFileError(
                    f".net line {lineno}: unexpected token {kind!r} (want 'node'/'router')"
                )
    return NetGraph(routers={
        rid: NetRouter(nodes=tuple(nodes[rid]), links=tuple(links[rid]))
        for rid in nodes
    })


def _find_net_file(icnt: Dict[str, object], booksim_dir: Path) -> Path:
    """The ``.net`` file for an anynet config: the echoed ``network_file`` path is
    the author's absolute path, so match by basename inside ``booksim_dir``; a
    lone ``*.net`` in the directory is accepted as a fallback."""
    name = Path(str(icnt.get("network_file", ""))).name
    if name:
        cand = booksim_dir / name
        if cand.is_file():
            return cand
    found = sorted(booksim_dir.glob("*.net"))
    if len(found) == 1:
        return found[0]
    if not found:
        raise NetFileError(
            f"anynet network file {name or '<unnamed>'} not found in {booksim_dir} "
            f"(no *.net present)"
        )
    raise NetFileError(
        f"anynet network file {name!r} not found in {booksim_dir} and the directory "
        f"holds {len(found)} *.net files — cannot pick one"
    )


def _flit_totals(act) -> Tuple[Optional[float], List[str]]:
    """Total network flits for a window: 2 × (DRAM reads + writes).

    Every packet in PyTorchSim's BookSim runs is one flit (packet length average
    = 1) of ``flit_size`` = ``dram_req_size_byte`` bytes, and each memory request
    crosses the network twice (request + response)."""
    if act.dram_reads is None or act.dram_writes is None:
        return None, [
            "log has no DRAM request totals; NoC structure is emitted but its "
            "dynamic energy cannot be charged"
        ]
    return 2.0 * (act.dram_reads + act.dram_writes), []


def derive_noc(act, booksim_dir: Optional[Path] = None) -> NocDerivation:
    """Derive the NoC symbols + stats for one parsed TOGSim log.

    Returns empty symbols (→ the ``noc`` compound's elements resolve to nothing
    and are skipped) with a single explanatory warning whenever the NoC cannot
    be modeled: no embedded BookSim config, an unsupported topology, or an
    ``anynet`` run without the ``.net`` file.
    """
    icnt = act.icnt_config
    if not icnt:
        icnt_type = (act.config or {}).get("icnt_type")
        if icnt_type == "booksim2":
            why = "log has no embedded BookSim [config] echo (older build?)"
        else:
            why = f"icnt_type {icnt_type!r} is not modeled (booksim2 only)"
        return NocDerivation(warnings=[f"NoC not emitted: {why}"])

    warnings: List[str] = []
    symbols = {f"booksim_{k}": v for k, v in icnt.items()
               if isinstance(v, int) and not isinstance(v, bool)}
    flit_size = icnt.get("flit_size")
    if not isinstance(flit_size, int) or flit_size <= 0:
        return NocDerivation(warnings=[
            "NoC not emitted: BookSim config has no integer flit_size"
        ])

    topology = str(icnt.get("topology", ""))
    if topology == "fly":
        if icnt.get("n") != 1:
            return NocDerivation(warnings=[
                f"NoC not emitted: unsupported topology 'fly' with n={icnt.get('n')!r} "
                f"(supported: {_SUPPORTED})"
            ])
        k = icnt.get("k")
        if not isinstance(k, int) or k <= 0:
            return NocDerivation(warnings=[
                "NoC not emitted: fly topology without an integer 'k'"
            ])
        ports, routers, channels, inter_fraction = k, 1, 0, 0.0

    elif topology == "anynet":
        if booksim_dir is None:
            return NocDerivation(warnings=[
                "NoC not emitted: anynet topology needs the BookSim config "
                "directory (--booksim-dir, e.g. the run's booksim2_config/) "
                "for its .net network file"
            ])
        try:
            net_path = _find_net_file(icnt, Path(booksim_dir))
            graph = parse_net_file(net_path.read_text(encoding="utf-8"))
        except (OSError, NetFileError) as e:
            return NocDerivation(warnings=[f"NoC not emitted: {e}"])
        real = graph.real_routers()
        chans = graph.channels()
        stray = set(graph.routers) - set(real) - set(chans)
        if not real:
            return NocDerivation(warnings=[
                f"NoC not emitted: {net_path.name} has no router with attached nodes"
            ])
        for rid in sorted(stray):
            warnings.append(
                f"{net_path.name}: router {rid} has no nodes and "
                f"{len(graph.routers[rid].links)} links — treated as a switch "
                f"(expected 2-link pass-through channels only)"
            )
        radices = sorted({r.radix for r in real.values()} |
                         {graph.routers[i].radix for i in stray})
        if len(radices) > 1:
            warnings.append(
                f"{net_path.name}: router radix varies ({radices}); using the "
                f"largest for all switches"
            )
        ports = radices[-1]
        routers = len(real) + len(stray)
        channels = len(chans)
        # Uniform-traffic split: aggregate BookSim stats cannot separate
        # intra- from inter-router flits, so assume each flit's endpoints are
        # uniformly distributed over the R switches.
        inter_fraction = (routers - 1) / routers if routers > 1 else 0.0
        if routers > 1:
            warnings.append(
                f"NoC traffic split is a uniform-traffic assumption: "
                f"{inter_fraction:.2f} of flits are charged one die-to-die "
                f"channel crossing and a second switch traversal (BookSim "
                f"reports only network-wide aggregates)"
            )
    else:
        return NocDerivation(warnings=[
            f"NoC not emitted: unsupported BookSim topology {topology!r} "
            f"(supported: {_SUPPORTED})"
        ])

    symbols.update(icnt_ports=ports, icnt_routers=routers, icnt_channels=channels)

    stats: Dict[str, float] = {}
    flits, fw = _flit_totals(act)
    warnings.extend(fw)
    if flits is not None and flits > 0:
        stats["icnt_xbar_flits"] = flits * (1.0 + inter_fraction)
        if channels:
            stats["icnt_d2d_flits"] = flits * inter_fraction
    return NocDerivation(symbols=symbols, stats=stats, warnings=warnings)
