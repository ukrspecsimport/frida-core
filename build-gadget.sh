#!/bin/bash

set -e

# Function to display usage information
usage() {
    echo "Usage: $0 <path_to_agent.c> <output_file_path>"
    echo "Build the Frida gadget using Docker."
    echo ""
    echo "Arguments:"
    echo "  <path_to_agent.c>   Path to the agent.c file"
    echo "  <output_file_path>  Full path for the output file (e.g., /path/to/my-frida-gadget.so)"
}

# Function to handle errors
handle_error() {
    echo "Error: $1" >&2
    usage
    exit 1
}

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    handle_error "Docker is not installed. Please install Docker and try again."
fi

# Check if the correct number of arguments is provided
if [ $# -ne 2 ]; then
    handle_error "Incorrect number of arguments."
fi

# Check if the provided agent.c file exists
if [ ! -f "$1" ]; then
    handle_error "The specified agent.c file does not exist: $1"
fi

# Check if the output directory exists
output_dir=$(dirname "$2")
if [ ! -d "$output_dir" ]; then
    handle_error "The output directory does not exist: $output_dir"
fi

# Define Docker image name and Dockerfile path
DOCKER_IMAGE="frida-core-builder"
DOCKERFILE_PATH="./Dockerfile"  # Adjust this path if your Dockerfile is located elsewhere

# Check if the Docker image exists, build it if it doesn't
if ! docker image inspect "$DOCKER_IMAGE" &> /dev/null; then
    echo "Docker image '$DOCKER_IMAGE' does not exist. Building it now..."
    
    # Check if Dockerfile exists
    if [ ! -f "$DOCKERFILE_PATH" ]; then
        handle_error "Dockerfile not found at $DOCKERFILE_PATH. Please ensure it exists and try again."
    fi
    
    # Build the Docker image
    if docker build --platform linux/amd64 -t "$DOCKER_IMAGE" -f "$DOCKERFILE_PATH" .; then
        echo "Docker image '$DOCKER_IMAGE' built successfully."
    else
        handle_error "Failed to build Docker image '$DOCKER_IMAGE'."
    fi
else
    echo "Docker image '$DOCKER_IMAGE' found."
fi

# Run the Docker command
echo "Building Frida gadget..."
if docker run -v "$2:/frida-core/build/lib/gadget/frida-gadget.so" -v "$1:/frida-core/lib/gadget/agent.c" "$DOCKER_IMAGE"; then
    echo "Build completed successfully."
    echo "Output file: $2"
else
    handle_error "Docker build failed."
fi