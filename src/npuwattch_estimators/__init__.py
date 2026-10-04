# This file is only for the package build. Do not import estimator modules
# from the main program, because they can import torch. There is one exception:
# npuwattch_estimators.sram.sram uses only the standard library. The emitter
# imports its SRAM template table (resolve_capacity). The estimator is the
# only source of this table.
