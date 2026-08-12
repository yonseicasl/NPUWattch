# NPUWattch
![Version: 0.9](https://img.shields.io/badge/Version-0.9-blue.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

NPUWattch is an ML-based power, area, and timing (PAT) modeling tool. Given an accelerator
description — and, optionally, activity recorded by a simulator — it produces per-component
estimates of energy, area, and timing, collected into a self-contained HTML report. The models
are trained on measurements collected through our holistic modeling approach.

## Install
```bash
pip install -e .
```

## Run
There are three ways to run NPUWattch, depending on what you have.

**1. From a PyTorchSim run (recommended).** NPUWattch reads the simulator's own output
folders, figures out what hardware was modeled, and charges each part with the activity the
simulator recorded:

```bash
npuwattch --harness pytorchsim \
          --togsim-dir togsim_results/ \
          --gem5-dir   gem5_outputs/ \
          --node 7nm --report report_dir/
```

When both folders live under one run root, `./run.sh <run_root> [flags...]` locates them for you.

**2. From an Accelergy/Timeloop architecture YAML.** No activity data is involved yet, so the
result is an activity-free estimate and is labeled VECTORLESS:

```bash
npuwattch --harness timeloop --arch-yaml architecture.yaml --node 7nm
```

**3. From NPUWattch's own files.** A native description, plus an optional activity CSV:

```bash
npuwattch -d description.yaml -l activity.csv
```

Useful flags:
- `--report DIR` writes `report.html` + `report.json`; `--tree` shows how the run was interpreted.
- Technology and operating point (harness modes only — a native description carries its own):
  `--node`, `--transistor`, `--corner`, `--voltage-offset`, `--temperature`, `--clock-mhz`.
- PyTorchSim extras: `--config-yml`, `--booksim-dir` (anynet NoC runs), `--energy-table`
  (DRAM cost table, e.g. `hbm2.yml`).
- Any run without activity data falls back to a vectorless estimate (25% of random switching,
  tunable with `--vectorless-activity`) and is labeled accordingly.

## Citation
NPUWattch :
```
@inproceedings{kim_hpca2026,
    title       = {NPUWattch: ML-based Power, Area, and Timing Modeling for Neural Accelerators},
    author      = {Kim, Sehyeon and Kim, Minkwan and Park, Chanho and Park, Hanmok and Kim, Seonghoon and Song, Taigon and Song, William J.},
    booktitle   = {IEEE International Symposium on High-Performance Computer Architecture},
    month       = {Jan.},
    year        = {2026},
    pages       = {1-14},
}
```
Related technology libraries :
```
@inproceedings{shin_iscas2024,
    title       = {FS2K: A Forksheet FET Technology Library and a Study of VLSI Prediction for 2nm and Beyond}, 
    author      = {Shin, Yunjeong and Park, Daehyeok and Koh, Dohun and Heo, Dongryul and Park, Jieun and Lee, Hyundong and Kim, Jongbeom and Lee, Hyunsoo and Song, Taigon},
    booktitle   = {IEEE International Symposium on Circuits and Systems}, 
    month       = {May},
    year        = {2024},
    pages       = {1-5},
}

@article{kim_tvlsi2023,
    title       = {NS3K: A 3nm Nanosheet FET Standard Cell Library Development and Its Impact},
    author      = {Kim, Taehak and Jeong, Jaehoon and Woo, Seungmin and Yang, Jeonggyu and Kim, Hyunwoo and Nam, Ahyeon and Lee, Changdong and Seo, Jinmin and Kim, Minji and Ryu, Siwon and Oh, Yoonju and Song, Taigon},
    journal     = {IEEE Transactions on Very Large Scale Integration Systems},
    volume      = {31},
    number      = {2},
    month       = {Feb.},
    year        = {2023},
    pages       = {163-176},
}
```

## Related Links
[Technology Libraries](https://i3dvlsi.wordpress.com/i3d-predictive-pdks/) from 20nm to 2nm

## License
NPUWattch is released under the MIT license. See [LICENSE](LICENSE) for additional details.
Thanks to the [I3D VLSI Laboratory](https://i3dvlsi.wordpress.com/).   

## Questions
Leave github issues or please contact ikamusume@yonsei.ac.kr
