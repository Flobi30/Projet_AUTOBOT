#!/bin/bash

RESPONSE=$(curl -s -c /tmp/cookies.txt http://127.0.0.1:8000/login)
CSRF=$(echo "$RESPONSE" | grep -oP 'name="csrf_token" value="\K[^"]+')

echo "Token CSRF récupéré: $CSRF"

curl -v -X POST http://127.0.0.1:8000/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -b /tmp/cookies.txt \
  --data-urlencode "username=AUTOBOT" \
  --data-urlencode "password=333333Aesnpr54&" \
  --data-urlencode "license_key=AUTOBOT-eyJ0eXAi-OiJKV1Qi-LCJhbGci-OiJIUzUx" \
  --data-urlencode "csrf_token=$CSRF"
