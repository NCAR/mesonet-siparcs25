#!/bin/bash
conda create -n credit-demo python=3.11
conda activate credit-demo
pip install miles-credit

conda install conda-forge::mamba
mamba install -c conda-forge esmf esmpy
pip install xesmf
pip install "numpy==2.2"
pip install h5netcdf
