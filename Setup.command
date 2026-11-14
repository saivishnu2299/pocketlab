#!/bin/sh
cd "$(dirname "$0")" || exit 1
./pocketlab setup
result=$?
printf '\nPress Enter to close.\n'
read -r ignored
exit "$result"
