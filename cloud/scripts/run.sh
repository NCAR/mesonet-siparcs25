#!/bin/bash

if [ "$1" == "-s" ]; then
    echo "Starting services..."

    chmod +x ./scripts/before_init.sh
    chmod +x ./scripts/init.sh
    chmod +x ./scripts/after_init.sh
    chmod +x ./scripts/boot.sh

    ./scripts/before_init.sh
    ./scripts/init.sh
    ./scripts/after_init.sh
    ./scripts/boot.sh
elif [ "$1" == "-r" ]; then
    echo "Restarting services..."

    chmod +x ./scripts/after_init.sh
    chmod +x ./scripts/boot.sh

    ./scripts/after_init.sh
    ./scripts/boot.sh
else
    echo "Usage: $0 {start|stop}"
    exit 1

fi