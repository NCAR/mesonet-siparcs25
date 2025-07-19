#!/usr/bin/env python
"""Converts a directory of netcdf files into a single zarr store.

On Casper, zarrifying 1 year of hourly conus404 data (1 variable,
1015x1367 = 1.39e6 gridpoints, 8760 timesteps, total data volume
~25GB) takes ~10 minutes wallclock and requires about 300MB of memory.

Author: Seth McGinnis
Contact: mcginnis@ucar.edu

# Dependencies:
# - xarray
# - os.path
# - glob
# - argparse

"""

import xarray
import os.path
import glob
from argparse import ArgumentParser


parser = ArgumentParser(
    description="converts a directory of netcdf files into a zarr store"
)
parser.add_argument("indir", help="directory containing one or more .nc files")
parser.add_argument("zarrfile", help="zarr store to create (must not already exist)")

## locals().update creates these, but declare them to pacify flake
indir, zarrfile = None, None
locals().update(vars(parser.parse_args()))  ## convert args into vars

inglob = indir + "/*.nc"

## check output first since glob could be slow if large
if os.path.exists(os.path.expanduser(zarrfile)):
    print("error: zarrfile must not already exist")
    quit()

if len(glob.glob(os.path.expanduser(inglob))) < 1:
    print("error: input directory contains no .nc files")
    quit()


ds = xarray.open_mfdataset(inglob)

## delete all global attributes (WRF has *many* superfluous & obfuscatory atts)
ds.attrs = {}

## manual dataset.chunk()-ing goes here if needed
## Default for conus404 is 1 day, all space, which seems like a good start

ds.to_zarr(zarrfile)
