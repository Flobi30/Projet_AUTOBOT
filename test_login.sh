#!/bin/bash

CSRF=$(curl -s http://127.0.0.1:8000/login \
  | grep -oP 'name="csrf_token" value="\K[^"]+')

echo "Token CSRF récupéré: $CSRF"

curl -v -X POST http://127.0.0.1:8000/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=MON_USER" \
  --data-urlencode "password=MON_PASS" \
  --data-urlencode "license_key=MA_CLE" \
  --data-urlencode "csrf_token=$CSRF"
