#!/bin/bash
# Quick script to test email endpoint
# Usage: ./test_email.sh your-email@example.com

EMAIL=${1:-"your-email@example.com"}
URL="https://squid-app-6avsy.ondigitalocean.app/api/auth/test-email/"

echo "Testing email endpoint..."
echo "Sending test email to: $EMAIL"
echo ""

curl -X POST "$URL" \
  -H "Content-Type: application/json" \
  -d "{\"to_email\": \"$EMAIL\"}" \
  | python3 -m json.tool

