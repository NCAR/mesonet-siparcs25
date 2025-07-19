#!/bin/bash

case "$1" in
  -s)
    echo "Starting services..."

    chmod +x ./scripts/before_init.sh \
             ./scripts/init.sh \
             ./scripts/after_init.sh \
             ./scripts/boot.sh

    ./scripts/before_init.sh
    ./scripts/init.sh
    ./scripts/after_init.sh
    ./scripts/boot.sh
    ;;

  -r)
    echo "Restarting services..."

    chmod +x ./scripts/after_init.sh \
             ./scripts/boot.sh

    ./scripts/after_init.sh
    ./scripts/boot.sh
    ;;

  *)
    echo "Usage: $0 {-s|-r}"
    exit 1
    ;;
esac
