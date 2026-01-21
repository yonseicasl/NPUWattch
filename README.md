# NPUWattch
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

NPUWattch is an ML-based power, area, and timing (PAT) modeling tool.

## Install
```bash
pip install -e .
```

## Run
```bash
npuwattch -d description_file.yaml -l activity_log.txt -v 1
```

## TODO

**v0.0** - This is a growing project, and more features will be added gradually.
- Add more NN modules
- Add scripts for dataset batch generation
- Add sample datasets and training support tools
- Add Timeloop and gem5 harnesses

## Citation
NPUWattch :
```
@inproceedings{kim_hpca2026,
    title       = {NPUWattch: ML-based Power, Area, and Timing Modeling for Neural Accelerators},
    author      = {Kim, Sehyeon and Kim, Minkwan and Park, Chanho and Park, Hanmok and Kim, Seonghoon and Song, Taigon and Song, William J.},
    booktitle   = {IEEE International Symposium on High-Performance Computer Architecture},
    year        = {2026},
    pages       = {1--14},
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
[Technology Libraries](about:blank) from 20nm to 2nm



## License
NPUWattch is released under the MIT license. See [LICENSE](LICENSE) for additional details.
Thanks to the [I3D VLSI Laboratory](https://i3dvlsi.wordpress.com/).   

## Questions
Leave github issues or please contact ikamusume@yonsei.ac.kr
