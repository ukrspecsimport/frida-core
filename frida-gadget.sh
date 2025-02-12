#!/bin/bash

set -e

# Function to display usage information
usage() {
    echo "Usage: $0 <command> [<args>]"
    echo "Build the Frida gadget using Docker."
    echo ""
    echo "Commands:"
    echo "  init                Initialize and build the Docker image if needed"
    echo "  build <agent.c> <output_file>"
    echo "                      Build the Frida gadget"
    echo ""
    echo "Arguments for 'build' command:"
    echo "  <agent.c>           Path to the agent.c file"
    echo "  <output_file>       Full path for the output file (e.g., /path/to/frida-gadget.so)"
}

# Function to handle errors
handle_error() {
    echo "Error: $1" >&2
    usage
    exit 1
}

# Function to check and build Docker image
check_and_build_docker_image() {
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
}

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    handle_error "Docker is not installed. Please install Docker and try again."
fi

# Check the command
if [ $# -lt 1 ]; then
    handle_error "No command specified."
fi

command="$1"
shift

case "$command" in
    init)
        check_and_build_docker_image
        ;;
    build)
        if [ $# -ne 2 ]; then
            handle_error "Incorrect number of arguments for 'build' command."
        fi

        agent_file="$1"
        output_file="$2"

        # Check if the provided agent.c file exists
        if [ ! -f "$agent_file" ]; then
            handle_error "The specified agent.c file does not exist: $agent_file"
        fi

        # Check if the output directory exists
        output_dir=$(dirname "$output_file")
        if [ ! -d "$output_dir" ]; then
            handle_error "The output directory does not exist: $output_dir"
        fi

        # Ensure Docker image is built
        check_and_build_docker_image

        # Run the Docker command
        echo "Building Frida gadget..."
        if docker run -v "$output_file:/frida-core/build/lib/gadget/frida-gadget.so" -v "$agent_file:/frida-core/lib/gadget/agent.c" "frida-core-builder"; then
            echo "Build completed successfully."
            echo "Output file: $output_file"
        else
            handle_error "Docker build failed."
        fi
        ;;
    *)
        handle_error "Unknown command: $command"
        ;;
esac