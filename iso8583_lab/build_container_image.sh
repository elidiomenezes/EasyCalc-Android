#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"

image_name="${IMAGE_NAME:-iso8583-lab:local}"
output_file="${OUTPUT_IMAGE:-$project_dir/iso8583-lab-image.tar}"

case "$output_file" in
    /*) ;;
    *) output_file="$project_dir/$output_file" ;;
esac

echo "Building Docker image: $image_name"
docker build --tag "$image_name" .

echo "Exporting image to: $output_file"
mkdir -p "$(dirname "$output_file")"
docker save --output "$output_file" "$image_name"

echo
docker image inspect "$image_name" \
    --format 'Image ID: {{.Id}} | Created: {{.Created}} | Size: {{.Size}} bytes'

if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$output_file"
fi

echo
echo "IMAGE READY"
echo "Local tag : $image_name"
echo "Tar file  : $output_file"
echo "Load elsewhere with: docker load -i $output_file"
