"""BookSim2 NoC topology → NPUWattch NoC symbols + flit traffic stats.

PyTorchSim uses BookSim2 for its full interconnect (``icnt_type: booksim2``).
The ``.icnt`` config names a topology. The network endpoints are the injection
ports of the cores and the DRAM channels. The log gives only one stats block
for the full network: averages, and no counters for each router. This reader
divides that network into physical components:

* ``fly`` with ``n = 1``: a single-stage butterfly, which is **one k×k
  crossbar**. The ``[config]`` block in the log gives k, flit_size, and the
  buffer depths. No other input is necessary.
* ``anynet``: the ``.net`` graph file lists the routers. The log gives only
  the *path* of this file. A router with attached ``node`` endpoints is a real
  switch. A router with **no** nodes and exactly two router links is a
  pass-through hop, which is a **die-to-die channel**. Example: a chiplet
  configuration with 2 chiplet routers and 8 channels of latency 5 between
  them.

Traffic: the model assumes that each BookSim packet is one flit of
``flit_size`` bytes (= ``dram_req_size_byte``). Each DRAM request gives one
request packet and one response packet. Thus total flits =
``2 × (dram_reads + dram_writes)``. The reader compares the assumption with the
"Injected packet length average" of the log. If the average is not
1 flit/packet, the reader scales the flit totals and gives a warning.

For a network with more than one router (anynet), the traversal split is
**exact** if the log has the ``NUMA local/remote`` request counters of each
core. A remote request goes through a die-to-die channel and a second switch.
Without these counters, the reader uses the **uniform-traffic assumption** and
gives a warning: with R real routers, ``(R−1)/R`` of the flits go through a
die-to-die channel and two routers.

The output goes to the compound mechanism. ``symbols`` become integer symbols
for the expressions of the run configuration: ``icnt_ports``, ``icnt_routers``,
``icnt_channels``, and the ``booksim_*`` config integers. ``stats`` become the
window activity stats ``icnt_xbar_flits`` and ``icnt_d2d_flits``. The ``noc``
actions of the pytorchsim projection use them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

__all__ = ["NetGraph", "NetRouter", "NocDerivation", "parse_net_file", "derive_noc"]

#: The topologies that this harness can divide into components. The harness
#: rejects all other topologies (mesh, torus, multi-stage fly) with a warning.
_SUPPORTED = "fly (n = 1) and anynet"


@dataclass(frozen=True)
class NetRouter:
    """One ``router`` entry of a BookSim anynet ``.net`` file, with its lines merged."""

    nodes: Tuple[int, ...] = ()                      # attached endpoint ids
    links: Tuple[Tuple[int, Optional[int]], ...] = ()  # (peer router, latency)

    @property
    def radix(self) -> int:
        return len(self.nodes) + len(self.links)


@dataclass(frozen=True)
class NetGraph:
    routers: Dict[int, NetRouter]

    def real_routers(self) -> Dict[int, NetRouter]:
        """Routers with attached endpoints. These are the real switches."""
        return {i: r for i, r in self.routers.items() if r.nodes}

    def channels(self) -> Dict[int, NetRouter]:
        """Pass-through routers with no nodes and two links. These are the die-to-die channels."""
        return {i: r for i, r in self.routers.items()
                if not r.nodes and len(r.links) == 2}


@dataclass(frozen=True)
class NocDerivation:
    """The NoC data of a window: expression symbols and activity stats."""

    symbols: Dict[str, int] = field(default_factory=dict)
    stats: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


class NetFileError(ValueError):
    """The anynet ``.net`` file is absent or has an incorrect format."""


def parse_net_file(text: str) -> NetGraph:
    """Parse the anynet grammar of BookSim.

    Each line is ``router <id>``, then a mix of ``node <id>`` and
    ``router <id> [<latency>]`` tokens. Lines with the same router id merge.
    """
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
    """Find the ``.net`` file of an anynet config.

    The ``network_file`` path in the log is an absolute path from a different
    machine. Thus the function uses only the file name and looks in
    ``booksim_dir``. As a fallback, the function accepts a directory that has
    exactly one ``*.net`` file.
    """
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
    """Total network flits of a window: 2 × (DRAM reads + writes) × flits/packet.

    Each memory request goes through the network two times (request and
    response). The model assumes that a packet is one flit of ``flit_size`` =
    ``dram_req_size_byte`` bytes. The "Injected packet length average" in the
    log is the check of this assumption. If the log gives a different average,
    the function scales the flit totals by it and gives a warning.
    """
    if act.dram_reads is None or act.dram_writes is None:
        return None, [
            "log has no DRAM request totals; NoC structure is emitted but its "
            "dynamic energy cannot be charged"
        ]
    flits = 2.0 * (act.dram_reads + act.dram_writes)
    warnings: List[str] = []
    apl = getattr(act, "booksim_avg_packet_length", None)
    if apl is not None and apl > 0 and abs(apl - 1.0) > 1e-6:
        flits *= apl
        warnings.append(
            f"BookSim reports packet length average {apl:g} (the model assumes "
            f"1 flit/packet): flit totals scaled by {apl:g}"
        )
    return flits, warnings


def derive_noc(act, booksim_dir: Optional[Path] = None) -> NocDerivation:
    """Derive the NoC symbols and stats for one parsed TOGSim log.

    If the function cannot model the NoC, it returns empty symbols and one
    warning that gives the cause. The elements of the ``noc`` compound then
    resolve to nothing, and the harness skips them. The possible causes are:

    * the log has no BookSim config,
    * the topology is not supported,
    * an ``anynet`` run has no ``.net`` file.
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
        # Split of the traffic into intra-die and inter-die. The split is
        # EXACT if the log has the NUMA request counters of each core. Local
        # requests stay on the die. Remote requests go through a die-to-die
        # channel and a second switch. The two packets of a request use the
        # same path. Without the NUMA line, use the uniform-traffic assumption.
        numa_local = getattr(act, "numa_local", None)
        numa_remote = getattr(act, "numa_remote", None)
        if (routers > 1 and numa_local is not None and numa_remote is not None
                and numa_local + numa_remote > 0):
            inter_fraction = numa_remote / (numa_local + numa_remote)
            if (act.dram_reads is not None and act.dram_writes is not None
                    and numa_local + numa_remote
                    != act.dram_reads + act.dram_writes):
                warnings.append(
                    f"NUMA request total {numa_local + numa_remote} != [DRAM] "
                    f"request total {act.dram_reads + act.dram_writes}; the "
                    f"d2d split still uses the NUMA local/remote ratio"
                )
        else:
            inter_fraction = (routers - 1) / routers if routers > 1 else 0.0
            if routers > 1:
                warnings.append(
                    f"NoC traffic split is a uniform-traffic assumption: "
                    f"{inter_fraction:.2f} of flits are charged one die-to-die "
                    f"channel crossing and a second switch traversal (the log "
                    f"has no NUMA local/remote counters)"
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
        if channels and inter_fraction > 0:
            stats["icnt_d2d_flits"] = flits * inter_fraction
    return NocDerivation(symbols=symbols, stats=stats, warnings=warnings)
