#!/bin/bash

set -e  # Exit on first error

echo "Downloading data from GFS in environment: ${ENV_NAME}"

# Run your script inside the conda environment
conda run -n "${ENV_NAME}" python miles-credit/applications/rollout_realtime.py -c model.yml
