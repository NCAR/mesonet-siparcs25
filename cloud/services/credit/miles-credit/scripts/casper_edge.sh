#!/bin/bash -l
#PBS -N edge_credit
#PBS -l select=1:ncpus=36:ngpus=0:mem=200GB
#PBS -l walltime=06:00:00
#PBS -A NAML0001
#PBS -q casper
#PBS -j oe
#PBS -k eod
module load conda
conda activate credit
cd ..
python -u applications/graph_edges.py -c /glade/u/home/wchapman/MLWPS/DataLoader/static_variables_ERA5_zhght.nc \
       -p 36 \
       -d 720 \
       -o /glade/derecho/scratch/dgagne/credit_scalers/
