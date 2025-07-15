#!/bin/bash
conda activate credit-demo
python miles-credit/applications/rollout_realtime.py -c test/model.yml
